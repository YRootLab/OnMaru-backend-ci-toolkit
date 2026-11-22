import json
from copy import deepcopy
from pathlib import Path

import pytest

from pipeline_toolkit.compare.performance import (
    P95_MIN_VALID_RUNS,
    P95_POLICY_VERSION,
    ExperimentDeclaration,
    PerformanceCompareError,
    RunObservation,
    build_plan,
    compare_experiment,
    histogram_quantile_estimate,
    p95_for_cohort,
)
from pipeline_toolkit.reports.performance import render_json, render_markdown

FIXTURES = Path(__file__).parent / "fixtures" / "performance-evidence"
BASE = json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8"))
LEGACY = json.loads((FIXTURES / "legacy.json").read_text(encoding="utf-8"))
ANCHOR = "2026-11-20T03:00:00.000Z"
AS_OF = "2026-11-22T00:00:00.000Z"
SELECTED_DIGEST = "sha256:" + "1" * 64
POLICY_DIGEST = "sha256:" + "2" * 64
LAYERS_WARM = {"dependency": "warm", "build": "cold", "configuration": "disabled"}
LAYERS_DISABLED = {"dependency": "disabled", "build": "disabled", "configuration": "disabled"}


def make_envelope(
    *,
    anchor=ANCHOR,
    experiment_class="realistic-pr",
    layers=None,
    policy_digest=None,
    selected_digest=None,
    selected_count=500,
    toolchain=None,
    writer_version="0.1.0",
    seeded=False,
    seed_digest=None,
    tests_ms=91000.0,
):
    env = deepcopy(BASE)
    env["clock"]["utc_anchor"] = anchor
    env["cache"]["experiment_class"] = experiment_class
    if policy_digest is not None:
        env["cache"]["policy_digest"] = policy_digest
    layer_states = LAYERS_WARM if layers is None else layers
    for name, state in layer_states.items():
        env["cache"]["cacheIdentity"]["layers"][name] = {"state": state}
    env["cache"]["cacheIdentity"]["seedProvenance"] = {"seeded": seeded, "seed_input_digest": seed_digest}
    if selected_digest is not None:
        env["selected"]["digest"] = selected_digest
    env["selected"]["count"] = selected_count
    env["execution"] = {"executed_now": 120, "verified_from_cache": selected_count - 120}
    if toolchain:
        env["toolchain"].update(toolchain)
    env["producer"]["version"] = writer_version
    env["timings_ms"]["tests"] = tests_ms
    return env


def declaration(profile="realistic-pr", planned=3, allowed=(), metric="wall_clock_ms", plan_kind="AB-BA"):
    return ExperimentDeclaration(
        experiment_id="exp-143",
        profile=profile,
        planned_runs_per_side=planned,
        allowed_variables=tuple(allowed),
        plan_kind=plan_kind,
        metric=metric,
    )


def slots_for(decl, side):
    return [entry["slot"] for entry in build_plan(decl) if entry["side"] == side]


def observations(decl, baseline=(), candidate=(), *, base_env=None, cand_env=None, restore="exact-key"):
    base_env = base_env if base_env is not None else make_envelope()
    cand_env = cand_env if cand_env is not None else make_envelope()
    base_slots = slots_for(decl, "baseline")
    cand_slots = slots_for(decl, "candidate")
    result = []
    for index, value in enumerate(baseline):
        result.append(RunObservation("baseline", base_slots[index], f"b{index + 1}", "success", restore, base_env, value))
    for index, value in enumerate(candidate):
        result.append(RunObservation("candidate", cand_slots[index], f"c{index + 1}", "success", restore, cand_env, value))
    return result


def reason_codes(result):
    return sorted({reason["code"] for reason in result["reasons"]})


def reason_fields(result):
    return sorted({reason["field"] for reason in result["reasons"]})


# ---------------------------------------------------------------- declaration and plan

def test_declaration_rejects_variables_that_are_not_declarable():
    with pytest.raises(PerformanceCompareError, match="runner_image"):
        declaration(allowed=("runner_image",))


def test_declaration_bounds_planned_runs_to_three_through_five():
    declaration(planned=3)
    declaration(planned=5)
    for bad in (2, 6):
        with pytest.raises(PerformanceCompareError):
            declaration(planned=bad)


def test_ab_ba_plan_alternates_side_order_and_ab_plan_is_blocked():
    ab_ba = [(e["side"], e["ordinal"]) for e in build_plan(declaration(planned=3))]
    assert ab_ba == [
        ("baseline", 1), ("candidate", 1),
        ("candidate", 2), ("baseline", 2),
        ("baseline", 3), ("candidate", 3),
    ]
    blocked = [e["side"] for e in build_plan(declaration(planned=3, plan_kind="AB"))]
    assert blocked == ["baseline"] * 3 + ["candidate"] * 3


# ---------------------------------------------------------------- replay determinism

def test_identical_input_gives_identical_offline_replay_output():
    decl = declaration()
    inputs = observations(decl, baseline=[100.0, 110.0, 120.0], candidate=[90.0, 95.0, 100.0])
    first = compare_experiment(decl, inputs, as_of=AS_OF)
    second = compare_experiment(decl, list(reversed(inputs)), as_of=AS_OF)
    assert first == second
    assert render_json(first) == render_json(second)
    assert render_markdown(first) == render_markdown(second)
    assert json.loads(render_json(first)) == first


# ---------------------------------------------------------------- comparable pair and descriptive values

def test_comparable_pair_reports_individual_values_median_range_and_delta():
    decl = declaration()
    result = compare_experiment(decl, observations(decl, [100.0, 110.0, 120.0], [90.0, 95.0, 100.0]), as_of=AS_OF)
    assert result["classification"] == "comparable"
    assert result["reasons"] == []
    baseline = result["sides"]["baseline"]
    candidate = result["sides"]["candidate"]
    assert [s["value"] for s in baseline["samples"]] == [100.0, 110.0, 120.0]
    assert baseline["median"] == 110.0 and baseline["range"] == [100.0, 120.0]
    assert candidate["median"] == 95.0 and candidate["range"] == [90.0, 100.0]
    comparison = result["comparison"]
    assert comparison["median_delta"] == pytest.approx(-15.0)
    assert comparison["direction"] == "candidate-lower"
    assert comparison["paired"]["pairs"] == 3
    assert comparison["paired"]["deltas"] == [-10.0, -15.0, -20.0]
    assert comparison["paired"]["median_delta"] == pytest.approx(-15.0)


def test_three_run_p95_is_insufficient_samples():
    decl = declaration()
    result = compare_experiment(decl, observations(decl, [100.0] * 3, [90.0] * 3), as_of=AS_OF)
    for side in ("baseline", "candidate"):
        p95 = result["sides"][side]["p95"]
        assert p95["status"] == "insufficient-samples"
        assert p95["p95_raw"] is None
        # Both sides share one cohort, so the window holds the six current valid runs.
        assert p95["valid_runs_in_window"] == 6


def test_too_few_valid_samples_is_insufficient_evidence_not_comparable():
    decl = declaration()
    result = compare_experiment(decl, observations(decl, [100.0, 101.0], [90.0, 91.0, 92.0]), as_of=AS_OF)
    assert result["classification"] == "insufficient-evidence"
    assert result["comparison"] is None
    assert result["insufficiency"] == [{"side": "baseline", "valid_samples": 2, "required": 3}]


# ---------------------------------------------------------------- declared vs undeclared differences

def _affected_candidate():
    return make_envelope(selected_digest=SELECTED_DIGEST, selected_count=320)


def test_declared_affected_selection_difference_is_allowed():
    decl = declaration(allowed=("affected_selection",))
    result = compare_experiment(
        decl,
        observations(decl, [100.0] * 3, [80.0] * 3, cand_env=_affected_candidate()),
        as_of=AS_OF,
    )
    assert result["classification"] == "comparable"
    fields = {item["field"] for item in result["allowed_differences"]}
    assert {"selected_digest", "selected_count"} <= fields
    assert {item["variable"] for item in result["allowed_differences"]} == {"affected_selection"}
    assert result["sides"]["baseline"]["identity"]["universe_digest"] == result["sides"]["candidate"]["identity"]["universe_digest"]


def test_undeclared_selected_plan_difference_is_incomparable():
    decl = declaration()
    result = compare_experiment(
        decl,
        observations(decl, [100.0] * 3, [80.0] * 3, cand_env=_affected_candidate()),
        as_of=AS_OF,
    )
    assert result["classification"] == "incomparable"
    assert "selected_plan_mismatch" in reason_codes(result)
    assert result["comparison"] is None


def test_universe_difference_is_never_allowed_even_when_affected_selection_is_declared():
    decl = declaration(allowed=("affected_selection",))
    changed = make_envelope()
    changed["test_universe"]["digest"] = "sha256:" + "3" * 64
    result = compare_experiment(decl, observations(decl, [100.0] * 3, [80.0] * 3, cand_env=changed), as_of=AS_OF)
    assert result["classification"] == "incomparable"
    assert "input_digest_mismatch" in reason_codes(result)


def _cache_enabled_candidate():
    return make_envelope(layers=LAYERS_WARM, policy_digest=POLICY_DIGEST)


def _cache_baseline():
    return make_envelope(layers=LAYERS_DISABLED)


def test_declared_cache_enablement_difference_is_allowed():
    decl = declaration(allowed=("cache_enablement",))
    result = compare_experiment(
        decl,
        observations(decl, [120.0] * 3, [60.0] * 3, base_env=_cache_baseline(), cand_env=_cache_enabled_candidate()),
        as_of=AS_OF,
    )
    assert result["classification"] == "comparable"
    fields = {item["field"] for item in result["allowed_differences"]}
    assert {"layer.dependency", "layer.build", "policy_digest"} <= fields
    assert {item["variable"] for item in result["allowed_differences"]} == {"cache_enablement"}


def test_undeclared_cache_enablement_difference_is_incomparable_and_explained():
    decl = declaration()
    result = compare_experiment(
        decl,
        observations(decl, [120.0] * 3, [60.0] * 3, base_env=_cache_baseline(), cand_env=_cache_enabled_candidate()),
        as_of=AS_OF,
    )
    assert result["classification"] == "incomparable"
    assert {"layer_state_mismatch", "namespace_mismatch"} <= set(reason_codes(result))
    assert "layer.dependency" in reason_fields(result)


def test_undeclared_runner_difference_is_incomparable_even_with_cache_declared():
    decl = declaration(allowed=("cache_enablement", "affected_selection"))
    changed = make_envelope(toolchain={"runner_image": "ubuntu-22.04@sha256:other"})
    result = compare_experiment(decl, observations(decl, [100.0] * 3, [90.0] * 3, cand_env=changed), as_of=AS_OF)
    assert result["classification"] == "incomparable"
    assert result["reasons"][0]["code"] == "runner_mismatch"
    assert result["reasons"][0]["field"] == "toolchain.runner_image"
    assert result["comparison"] is None


def test_undeclared_toolchain_schema_and_profile_differences_are_incomparable():
    decl = declaration()
    toolchain_changed = make_envelope(toolchain={"java_version": "21.0.9"})
    result = compare_experiment(decl, observations(decl, [100.0] * 3, [90.0] * 3, cand_env=toolchain_changed), as_of=AS_OF)
    assert "toolchain_mismatch" in reason_codes(result)

    writer_changed = make_envelope(writer_version="0.2.0")
    result = compare_experiment(decl, observations(decl, [100.0] * 3, [90.0] * 3, cand_env=writer_changed), as_of=AS_OF)
    assert "schema_mismatch" in reason_codes(result)
    assert result["classification"] == "incomparable"


def test_profiles_are_never_compared_and_no_delta_is_reported():
    decl = declaration(profile="realistic-pr")
    other_profile = make_envelope(experiment_class="controlled-cold")
    result = compare_experiment(decl, observations(decl, [100.0] * 3, [50.0] * 3, cand_env=other_profile), as_of=AS_OF)
    assert result["classification"] == "incomparable"
    assert "profile_mismatch" in reason_codes(result)
    assert result["comparison"] is None
    # The candidate envelope is a different profile, so its sample is excluded explicitly.
    assert result["sides"]["candidate"]["exclusions"] == {"profile_mismatch": 3}


def test_within_side_identity_drift_is_incomparable():
    decl = declaration()
    drifted = [
        RunObservation("baseline", slots_for(decl, "baseline")[0], "b1", "success", "exact-key", make_envelope(), 100.0),
        RunObservation("baseline", slots_for(decl, "baseline")[1], "b2", "success", "exact-key",
                       make_envelope(toolchain={"java_version": "21.0.9"}), 101.0),
    ]
    result = compare_experiment(decl, drifted, as_of=AS_OF)
    assert result["classification"] == "incomparable"
    assert any(r["side"] == "baseline" and r["code"] == "toolchain_mismatch" for r in result["reasons"])


def test_legacy_limited_records_are_incomparable_with_explanation():
    decl = declaration()
    legacy = {**LEGACY}
    obs = [
        RunObservation("baseline", slots_for(decl, "baseline")[i], f"b{i}", "success", "exact-key", legacy, 100.0)
        for i in range(3)
    ] + [
        RunObservation("candidate", slots_for(decl, "candidate")[i], f"c{i}", "success", "exact-key", legacy, 90.0)
        for i in range(3)
    ]
    result = compare_experiment(decl, obs, as_of=AS_OF)
    assert result["classification"] == "incomparable"
    assert "legacy_limited" in reason_codes(result)
    assert result["sides"]["baseline"]["exclusions"] == {"quality_legacy-limited": 3}


# ---------------------------------------------------------------- seeds and denominators

def test_seed_runs_are_excluded_from_warm_samples_and_denominators_are_kept():
    decl = declaration(profile="controlled-warm", planned=5)
    warm = make_envelope(experiment_class="controlled-warm", layers=LAYERS_WARM)
    seed = make_envelope(
        experiment_class="controlled-warm", layers=LAYERS_WARM, seeded=True, seed_digest="sha256:" + "4" * 64
    )
    cand_slots = slots_for(decl, "candidate")
    obs = observations(decl, [100.0] * 5, [], base_env=warm)
    obs += [
        RunObservation("candidate", cand_slots[0], "c1", "success", "exact-key", warm, 90.0),
        RunObservation("candidate", cand_slots[1], "c2", "success", "exact-key", warm, 91.0),
        RunObservation("candidate", cand_slots[2], "c3", "success", "exact-key", warm, 92.0),
        RunObservation("candidate", cand_slots[3], "seed", "success", "exact-key", seed, 300.0),
        RunObservation("candidate", cand_slots[4], "c5", "cancelled", "exact-key", None, None),
    ]
    result = compare_experiment(decl, obs, as_of=AS_OF)
    candidate = result["sides"]["candidate"]
    assert candidate["attempts"] == 5
    assert candidate["valid_samples"] == 3
    assert [s["value"] for s in candidate["samples"]] == [90.0, 91.0, 92.0]
    assert candidate["exclusions"] == {"outcome:cancelled": 1, "seed_run": 1}
    assert candidate["cancelled"] == 1
    assert candidate["rates"]["cancelled"] == pytest.approx(0.2)
    assert candidate["rates"]["excluded"] == pytest.approx(0.4)
    assert result["classification"] == "comparable"


def test_failure_and_cancel_denominators_are_preserved_per_side():
    decl = declaration(planned=5)
    base_slots = slots_for(decl, "baseline")
    cand_env = make_envelope()
    obs = observations(decl, [100.0] * 3, [90.0] * 4, cand_env=cand_env)
    obs += [
        RunObservation("baseline", base_slots[3], "bf", "failure", "exact-key", None, None),
        RunObservation("baseline", base_slots[4], "bc", "cancelled", "exact-key", None, None),
    ]
    result = compare_experiment(decl, obs, as_of=AS_OF)
    baseline = result["sides"]["baseline"]
    assert baseline["attempts"] == 5
    assert baseline["valid_samples"] == 3
    assert baseline["failed"] == 1 and baseline["cancelled"] == 1 and baseline["excluded"] == 2
    assert baseline["rates"]["failed"] == pytest.approx(0.2)
    assert baseline["exclusions"] == {"outcome:cancelled": 1, "outcome:failure": 1}
    assert result["sides"]["candidate"]["rates"]["failed"] == 0.0
    assert result["classification"] == "comparable"


def test_metric_unavailable_is_excluded_and_never_coerced_to_zero():
    decl = declaration(metric="tests", planned=3)
    base = make_envelope(tests_ms=90000.0)
    missing = make_envelope(tests_ms=None)
    cand = make_envelope(tests_ms=80000.0)
    obs = observations(decl, [], [], base_env=base)
    base_slots = slots_for(decl, "baseline")
    cand_slots = slots_for(decl, "candidate")
    obs = [
        RunObservation("baseline", base_slots[0], "b1", "success", "exact-key", base, None),
        RunObservation("baseline", base_slots[1], "b2", "success", "exact-key", base, None),
        RunObservation("baseline", base_slots[2], "b3", "success", "exact-key", missing, None),
        RunObservation("candidate", cand_slots[0], "c1", "success", "exact-key", cand, None),
        RunObservation("candidate", cand_slots[1], "c2", "success", "exact-key", cand, None),
        RunObservation("candidate", cand_slots[2], "c3", "success", "exact-key", cand, None),
    ]
    result = compare_experiment(decl, obs, as_of=AS_OF)
    baseline = result["sides"]["baseline"]
    assert baseline["exclusions"] == {"metric_unavailable": 1}
    assert baseline["valid_samples"] == 2
    assert baseline["median"] == 90000.0
    assert result["sides"]["baseline"]["timings_ms"]["tests"]["available"] == 2


def test_plan_deviation_is_excluded_with_denominator():
    decl = declaration()
    obs = observations(decl, [100.0] * 3, [90.0] * 2)
    obs.append(RunObservation("candidate", slots_for(decl, "baseline")[0], "wrong", "success", "exact-key", make_envelope(), 1.0))
    result = compare_experiment(decl, obs, as_of=AS_OF)
    assert result["sides"]["candidate"]["exclusions"] == {"plan_deviation": 1}
    assert result["sides"]["candidate"]["valid_samples"] == 2
    assert result["classification"] == "insufficient-evidence"


# ---------------------------------------------------------------- p95 policy and window boundary

def _pool(count, *, start_minutes_before_end=1, cohort="c", end=AS_OF):
    from datetime import timedelta
    from pipeline_toolkit.compare.performance import parse_utc_anchor

    end_dt = parse_utc_anchor(end)
    records = []
    for index in range(count):
        instant = end_dt - timedelta(minutes=start_minutes_before_end + index)
        records.append({
            "run_id": f"h{index}",
            "valid": True,
            "cohort": cohort,
            "anchor": instant.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "value": float(index + 1),
        })
    return records


def test_p95_policy_version_and_threshold_are_constants():
    assert P95_POLICY_VERSION == "p95-rolling-cohort-14d-100/1"
    assert P95_MIN_VALID_RUNS == 100


def test_p95_is_insufficient_at_99_and_computed_at_100_valid_runs_in_window():
    assert p95_for_cohort(_pool(99), "c", AS_OF)["status"] == "insufficient-samples"
    result = p95_for_cohort(_pool(100), "c", AS_OF)
    assert result["status"] == "computed"
    assert result["valid_runs_in_window"] == 100
    assert result["p95_raw"] == 95.0  # nearest rank: ceil(0.95 * 100) = 95th of values 1..100


def test_p95_rolling_window_boundaries_are_start_exclusive_and_end_inclusive():
    start = "2026-11-08T00:00:00.000Z"  # as_of minus 14 days
    just_inside = "2026-11-08T00:00:00.000001Z"
    pool = [
        {"run_id": "at-start", "valid": True, "cohort": "c", "anchor": start, "value": 1.0},
        {"run_id": "after-end", "valid": True, "cohort": "c", "anchor": "2026-11-22T00:00:01.000Z", "value": 1.0},
    ]
    pool += [
        {"run_id": f"in-{i}", "valid": True, "cohort": "c", "anchor": just_inside, "value": float(i)}
        for i in range(98)
    ]
    # 98 inside + at-start (excluded) + after-end (excluded) = 98 valid runs in window.
    assert p95_for_cohort(pool, "c", AS_OF)["valid_runs_in_window"] == 98
    pool.append({"run_id": "at-end", "valid": True, "cohort": "c", "anchor": AS_OF, "value": 2.0})
    result = p95_for_cohort(pool, "c", AS_OF)
    assert result["valid_runs_in_window"] == 99
    assert result["status"] == "insufficient-samples"
    pool.append({"run_id": "one-more", "valid": True, "cohort": "c", "anchor": just_inside, "value": 3.0})
    assert p95_for_cohort(pool, "c", AS_OF)["status"] == "computed"


def test_p95_uses_only_the_same_cohort():
    pool = _pool(100, cohort="other")
    result = p95_for_cohort(pool, "c", AS_OF)
    assert result["status"] == "insufficient-samples"
    assert result["valid_runs_in_window"] == 0


def test_history_fills_the_cohort_window_in_compare_experiment():
    decl = declaration()
    # Both sides share one cohort here (identical conditions), so the pool is 3 + 3 + history.
    def history_of(count):
        return [
            RunObservation("baseline", 1, f"h{i}", "success", "exact-key",
                           make_envelope(anchor="2026-11-19T00:00:00.000Z"), float(i + 1))
            for i in range(count)
        ]

    obs = observations(decl, [100.0] * 3, [90.0] * 3)
    result = compare_experiment(decl, obs, as_of=AS_OF, history=history_of(93))
    assert result["sides"]["baseline"]["p95"]["valid_runs_in_window"] == 99
    assert result["sides"]["baseline"]["p95"]["status"] == "insufficient-samples"
    result = compare_experiment(decl, obs, as_of=AS_OF, history=history_of(94))
    assert result["sides"]["baseline"]["p95"]["valid_runs_in_window"] == 100
    assert result["sides"]["candidate"]["p95"]["status"] == "computed"
    assert result["sides"]["baseline"]["p95"]["p95_raw"] is not None


# ---------------------------------------------------------------- histogram estimate is separate

def test_histogram_estimate_is_labelled_and_separate_from_raw_quantiles():
    estimate = histogram_quantile_estimate([10, 20, 30], [0, 50, 50, 0], 0.95)
    assert estimate["kind"] == "histogram-estimate"
    assert estimate["estimate"] == pytest.approx(29.0)
    assert "p95_raw" not in estimate
    raw = p95_for_cohort([], None, AS_OF)
    assert "estimate" not in raw


# ---------------------------------------------------------------- overhead and release threshold guard

def test_overhead_budget_is_three_percent_or_fifteen_seconds_whichever_is_smaller():
    decl = declaration()
    fast = compare_experiment(decl, observations(decl, [100000.0] * 3, [101000.0] * 3), as_of=AS_OF)
    assert fast["comparison"]["overhead"]["budget_ms"] == pytest.approx(3000.0)
    slow = compare_experiment(decl, observations(decl, [1000000.0] * 3, [1001000.0] * 3), as_of=AS_OF)
    assert slow["comparison"]["overhead"]["budget_ms"] == 15000.0


def test_release_threshold_module_is_unchanged_by_this_engine():
    from pipeline_toolkit.compare.statistics import compare_releases

    result = compare_releases([100.0, 101.0, 99.0], [100.5, 100.2, 99.9], {"env": "a"}, {"env": "a"})
    assert result["status"] in {"unchanged", "improved", "regressed", "inconclusive"}


def test_render_markdown_lists_reasons_and_no_comparison_when_incomparable():
    decl = declaration()
    result = compare_experiment(decl, observations(decl, [100.0] * 3, [90.0] * 3, cand_env=make_envelope(toolchain={"runner_image": "other"})), as_of=AS_OF)
    text = render_markdown(result)
    assert "runner_mismatch" in text
    assert "Median delta" not in text
