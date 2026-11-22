"""Deterministic comparison of CI performance experiments (``ci-performance-evidence/1.0``).

The engine separates three outcomes:

- ``incomparable``: an undeclared difference in profile, namespace, input digest,
  layer state, toolchain, writer, restore policy or selected plan exists. The
  reasons are listed and no improvement or delta is computed.
- ``insufficient-evidence``: the pair is comparable but a side has too few valid
  samples for a median or range to mean anything.
- ``comparable``: descriptive medians, ranges and paired deltas are reported.

Only declared variables (``ALLOWED_VARIABLES``) may differ between baseline and
candidate. Everything is pure and deterministic: no clock is read, observations
are sorted before processing, and ``as_of`` must be supplied by the caller.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from pipeline_toolkit.contracts.performance_evidence import (
    LAYER_NAMES,
    TIMING_NAMES,
    PerformanceEvidenceError,
    validate_envelope,
)

POLICY_VERSION = "performance-compare/1"
# Initial p95 policy. Versioned so that a change is an explicit, reviewable constant bump.
P95_POLICY_VERSION = "p95-rolling-cohort-14d-100/1"
P95_MIN_VALID_RUNS = 100
P95_WINDOW_DAYS = 14
MIN_DESCRIPTIVE_SAMPLES = 3
MIN_PLANNED_RUNS_PER_SIDE = 3
MAX_PLANNED_RUNS_PER_SIDE = 5
PROFILES = ("controlled-cold", "controlled-warm", "realistic-pr")
ALLOWED_VARIABLES = ("affected_selection", "cache_enablement")
PLAN_KINDS = ("AB-BA", "AB")
PRIMARY_METRICS = ("wall_clock_ms", *TIMING_NAMES)
SIDES = ("baseline", "candidate")
OUTCOMES = ("success", "failure", "timed_out", "cancelled", "skipped")
FAILED_OUTCOMES = ("failure", "timed_out")
SEED_EXCLUSIONS = ("seed_run", "seed_provenance_unknown")
TRUSTED_WRITERS = frozenset({"onmaru-ci-performance-writer"})
OVERHEAD_BUDGET_RATIO = 0.03
OVERHEAD_BUDGET_CAP_MS = 15000.0

_ANCHOR = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]+))?Z")

_FIXED_RULE_CODES = {
    "profile": "profile_mismatch",
    "repository": "namespace_mismatch",
    "workflow": "namespace_mismatch",
    "policy_digest": "namespace_mismatch",
    "universe_digest": "input_digest_mismatch",
    "universe_size": "input_digest_mismatch",
    "seed_input_digest": "input_digest_mismatch",
    "selected_digest": "selected_plan_mismatch",
    "selected_count": "selected_plan_mismatch",
    "writer.name": "schema_mismatch",
    "writer.version": "schema_mismatch",
    "restore_policy": "restore_policy_mismatch",
}


class PerformanceCompareError(ValueError):
    """Malformed declaration or observation supplied by the caller (not an evidence finding)."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_utc_anchor(text: Any) -> datetime:
    """Parse a contract UTC anchor into a naive UTC datetime with microsecond precision."""
    if not isinstance(text, str):
        raise PerformanceCompareError("as_of must be a UTC anchor string")
    match = _ANCHOR.fullmatch(text)
    if match is None:
        raise PerformanceCompareError(f"invalid UTC anchor: {text!r}")
    base = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S")
    fraction = (match.group(2) or "")[:6].ljust(6, "0")
    return base.replace(microsecond=int(fraction))


@dataclass(frozen=True)
class ExperimentDeclaration:
    """Pre-registered experiment: profile, allowed variables and the run plan."""

    experiment_id: str
    profile: str
    planned_runs_per_side: int
    allowed_variables: Tuple[str, ...] = ()
    plan_kind: str = "AB-BA"
    metric: str = "wall_clock_ms"

    def __post_init__(self) -> None:
        if not isinstance(self.experiment_id, str) or not self.experiment_id.strip():
            raise PerformanceCompareError("experiment_id must be a non-empty string")
        if self.profile not in PROFILES:
            raise PerformanceCompareError(f"profile must be one of: {', '.join(PROFILES)}")
        if not _is_int(self.planned_runs_per_side) or not (
            MIN_PLANNED_RUNS_PER_SIDE <= self.planned_runs_per_side <= MAX_PLANNED_RUNS_PER_SIDE
        ):
            raise PerformanceCompareError(
                f"planned_runs_per_side must be an integer in "
                f"{MIN_PLANNED_RUNS_PER_SIDE}..{MAX_PLANNED_RUNS_PER_SIDE}"
            )
        variables = tuple(self.allowed_variables)
        undeclarable = sorted(set(variables) - set(ALLOWED_VARIABLES))
        if undeclarable:
            raise PerformanceCompareError(
                f"variables cannot be declared as allowed: {', '.join(undeclarable)}"
            )
        if self.plan_kind not in PLAN_KINDS:
            raise PerformanceCompareError(f"plan_kind must be one of: {', '.join(PLAN_KINDS)}")
        if self.metric not in PRIMARY_METRICS:
            raise PerformanceCompareError(f"metric must be one of: {', '.join(PRIMARY_METRICS)}")
        object.__setattr__(self, "allowed_variables", tuple(sorted(set(variables))))


def build_plan(declaration: ExperimentDeclaration) -> List[Dict[str, Any]]:
    """Deterministic run order. ``AB-BA`` alternates the side order per ordinal pair."""
    count = declaration.planned_runs_per_side
    order: List[Tuple[str, int]] = []
    if declaration.plan_kind == "AB-BA":
        for ordinal in range(1, count + 1):
            sides = SIDES if ordinal % 2 == 1 else tuple(reversed(SIDES))
            order.extend((side, ordinal) for side in sides)
    else:
        for side in SIDES:
            order.extend((side, ordinal) for ordinal in range(1, count + 1))
    return [
        {"slot": slot, "side": side, "ordinal": ordinal}
        for slot, (side, ordinal) in enumerate(order, start=1)
    ]


@dataclass(frozen=True)
class RunObservation:
    """One attempted run. ``envelope`` is a ci-performance-evidence/1.0 mapping or None."""

    side: str
    slot: int
    run_id: str
    outcome: str
    restore_policy: Optional[str]
    envelope: Optional[Mapping[str, Any]] = None
    wall_clock_ms: Optional[float] = None


def _check_shape(obs: RunObservation) -> None:
    if obs.side not in SIDES:
        raise PerformanceCompareError(f"side must be one of: {', '.join(SIDES)}")
    if not _is_int(obs.slot) or obs.slot < 1:
        raise PerformanceCompareError("slot must be an integer >= 1")
    if not isinstance(obs.run_id, str) or not obs.run_id.strip():
        raise PerformanceCompareError("run_id must be a non-empty string")
    if obs.outcome not in OUTCOMES:
        raise PerformanceCompareError(f"outcome must be one of: {', '.join(OUTCOMES)}")


def _identity_of(envelope: Mapping[str, Any], restore_policy: Optional[str]) -> Dict[str, Any]:
    cache = envelope["cache"]
    identity: Dict[str, Any] = {
        "profile": cache["experiment_class"],
        "repository": envelope["source"]["repository"],
        "workflow": envelope["source"]["workflow"],
        "writer.name": envelope["producer"]["name"],
        "writer.version": envelope["producer"]["version"],
        "policy_digest": cache["policy_digest"],
        "universe_digest": envelope["test_universe"]["digest"],
        "universe_size": envelope["test_universe"]["size"],
        "selected_digest": envelope["selected"]["digest"],
        "selected_count": envelope["selected"]["count"],
        "seed_input_digest": cache["cacheIdentity"]["seedProvenance"]["seed_input_digest"],
        "restore_policy": restore_policy,
    }
    layers = cache["cacheIdentity"]["layers"]
    for name in LAYER_NAMES:
        identity["layer." + name] = layers[name]["state"] if name in layers else None
    for key, value in envelope["toolchain"].items():
        identity["toolchain." + key] = value
    return identity


def _cohort_key(identity: Mapping[str, Any]) -> str:
    """Cohort for the p95 policy: everything except per-run plan digests and seed input."""
    stable = {
        key: value
        for key, value in identity.items()
        if not key.startswith("selected_") and key != "seed_input_digest"
    }
    return json.dumps(stable, sort_keys=True, ensure_ascii=False)


def _exclude(record: Dict[str, Any], reason: str) -> None:
    if record["exclusion"] is None:
        record["exclusion"] = reason


def _normalize(obs: RunObservation, declaration: ExperimentDeclaration) -> Dict[str, Any]:
    _check_shape(obs)
    record: Dict[str, Any] = {
        "run_id": obs.run_id,
        "side": obs.side,
        "slot": obs.slot,
        "ordinal": None,
        "outcome": obs.outcome,
        "exclusion": None,
        "valid": False,
        "identity": None,
        "cohort": None,
        "anchor": None,
        "value": None,
        "execution": None,
        "timings_ms": None,
        "envelope_error": None,
    }
    if obs.outcome != "success":
        _exclude(record, f"outcome:{obs.outcome}")

    envelope: Optional[Dict[str, Any]] = None
    if not isinstance(obs.envelope, Mapping):
        _exclude(record, "envelope_missing")
    else:
        try:
            envelope = validate_envelope(deepcopy(dict(obs.envelope)))
        except PerformanceEvidenceError as exc:
            record["envelope_error"] = str(exc)
            _exclude(record, "invalid_envelope")

    if envelope is not None:
        quality = envelope["quality"]
        record["anchor"] = envelope["clock"]["utc_anchor"]
        if quality in ("complete", "partial"):
            record["identity"] = _identity_of(envelope, obs.restore_policy)
            record["cohort"] = _cohort_key(record["identity"])
            if envelope["cache"]["experiment_class"] != declaration.profile:
                _exclude(record, "profile_mismatch")
            seeded = envelope["cache"]["cacheIdentity"]["seedProvenance"]["seeded"]
            if declaration.profile == "controlled-warm" and seeded is not False:
                _exclude(record, "seed_run" if seeded else "seed_provenance_unknown")
        if quality != "complete":
            _exclude(record, f"quality_{quality}")
        record["execution"] = dict(envelope["execution"])
        timings = envelope.get("timings_ms") or {}
        record["timings_ms"] = {name: timings.get(name) for name in TIMING_NAMES}

    if not isinstance(obs.restore_policy, str) or not obs.restore_policy.strip():
        _exclude(record, "restore_policy_missing")

    if declaration.metric == "wall_clock_ms":
        value = obs.wall_clock_ms
        if value is not None and not (_is_number(value) and value >= 0):
            _exclude(record, "metric_invalid")
            value = None
    else:
        value = None
        if envelope is not None:
            value = (envelope.get("timings_ms") or {}).get(declaration.metric)
    if value is None:
        _exclude(record, "metric_unavailable")
    else:
        record["value"] = float(value)
    record["valid"] = record["exclusion"] is None
    return record


def _rule_code(field: str) -> str:
    if field == "toolchain.runner_image":
        return "runner_mismatch"
    if field.startswith("toolchain."):
        return "toolchain_mismatch"
    if field.startswith("layer."):
        return "layer_state_mismatch"
    return _FIXED_RULE_CODES.get(field, "identity_mismatch")


def _relaxing_variable(field: str, left: Any, right: Any, declared: Sequence[str]) -> Optional[str]:
    if field == "policy_digest" and "cache_enablement" in declared:
        return "cache_enablement"
    if field.startswith("layer.") and "cache_enablement" in declared:
        # Enablement change only: one side disabled, the other enabled in some state.
        if left is not None and right is not None and "disabled" in (left, right):
            return "cache_enablement"
    if field.startswith("selected_") and "affected_selection" in declared:
        return "affected_selection"
    return None


def _cross_reason(code: str, field: str, baseline: Any, candidate: Any) -> Dict[str, Any]:
    return {"code": code, "field": field, "side": None, "baseline": baseline, "candidate": candidate}


def _within_reason(code: str, field: str, side: str, expected: Any, observed: Any) -> Dict[str, Any]:
    return {"code": code, "field": field, "side": side, "expected": expected, "observed": observed}


def _diff_cross(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any], declared: Sequence[str]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    reasons: List[Dict[str, Any]] = []
    allowed: List[Dict[str, Any]] = []
    for field in sorted(set(baseline) | set(candidate)):
        left, right = baseline.get(field), candidate.get(field)
        if left == right:
            continue
        if field.startswith("layer.") and "unknown" in (left, right):
            reasons.append(_cross_reason("layer_state_unknown", field, left, right))
            continue
        variable = _relaxing_variable(field, left, right, declared)
        if variable is not None:
            allowed.append({"field": field, "variable": variable, "baseline": left, "candidate": right})
            continue
        reasons.append(_cross_reason(_rule_code(field), field, left, right))
    return reasons, allowed


def _diff_within(side: str, expected: Mapping[str, Any], observed: Mapping[str, Any]) -> List[Dict[str, Any]]:
    reasons: List[Dict[str, Any]] = []
    for field in sorted(set(expected) | set(observed)):
        left, right = expected.get(field), observed.get(field)
        if left != right:
            code = "layer_state_unknown" if field.startswith("layer.") and "unknown" in (left, right) else _rule_code(field)
            reasons.append(_within_reason(code, field, side, left, right))
    return reasons


def _ratio(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator else None


def p95_for_cohort(pool: Iterable[Mapping[str, Any]], cohort: Optional[str], as_of: str) -> Dict[str, Any]:
    """Raw-quantile p95 for one cohort, gated by the rolling-window run count.

    Window is ``(as_of - 14 days, as_of]``: the start is exclusive and the end inclusive.
    Histogram estimates are never returned here (see ``histogram_quantile_estimate``).
    """
    end = parse_utc_anchor(as_of)
    start = end - timedelta(days=P95_WINDOW_DAYS)
    runs: Dict[str, float] = {}
    for record in pool:
        if not record.get("valid") or cohort is None or record.get("cohort") != cohort:
            continue
        anchor = record.get("anchor")
        if anchor is None:
            continue
        instant = parse_utc_anchor(anchor)
        if start < instant <= end:
            runs.setdefault(str(record["run_id"]), float(record["value"]))
    values = sorted(runs.values())
    count = len(values)
    result: Dict[str, Any] = {
        "policy_version": P95_POLICY_VERSION,
        "window_days": P95_WINDOW_DAYS,
        "window_end_inclusive": as_of,
        "valid_runs_in_window": count,
        "required_valid_runs": P95_MIN_VALID_RUNS,
        "method": "nearest-rank",
    }
    if cohort is None or count < P95_MIN_VALID_RUNS:
        result.update(status="insufficient-samples", p95_raw=None)
    else:
        rank = (95 * count + 99) // 100  # ceil(0.95 * count), 1-based
        result.update(status="computed", p95_raw=values[rank - 1])
    return result


def histogram_quantile_estimate(bounds: Sequence[float], counts: Sequence[int], quantile: float = 0.95) -> Dict[str, Any]:
    """Estimate a quantile from explicit (non-cumulative) histogram buckets.

    ``bounds`` are ascending finite upper bounds; ``counts`` has one extra trailing
    entry for the +Inf bucket. The estimate is labelled as such and is never a raw quantile.
    """
    if len(counts) != len(bounds) + 1 or any(not _is_int(c) or c < 0 for c in counts):
        raise PerformanceCompareError("counts must be non-negative integers, one per bound plus +Inf")
    if any(not _is_number(b) for b in bounds) or list(bounds) != sorted(bounds):
        raise PerformanceCompareError("bounds must be finite and ascending")
    if not 0 < quantile < 1:
        raise PerformanceCompareError("quantile must be in (0, 1)")
    total = sum(counts)
    base = {"kind": "histogram-estimate", "method": "linear-interpolation", "quantile": quantile, "total": total}
    if total == 0:
        return {**base, "estimate": None}
    target = quantile * total
    cumulative = 0
    lower = 0.0
    for index, count in enumerate(counts):
        upper = bounds[index] if index < len(bounds) else None
        if cumulative + count >= target and count > 0:
            if upper is None:
                return {**base, "estimate": float(bounds[-1]) if bounds else None, "clamped": True}
            fraction = (target - cumulative) / count
            return {**base, "estimate": lower + (upper - lower) * fraction, "clamped": False}
        cumulative += count
        if upper is not None:
            lower = float(upper)
    return {**base, "estimate": None}


def _side_report(
    side: str,
    records: List[Dict[str, Any]],
    identity: Optional[Dict[str, Any]],
    cohort: Optional[str],
    pool: List[Dict[str, Any]],
    as_of: str,
) -> Dict[str, Any]:
    outcomes = Counter(record["outcome"] for record in records)
    exclusions = Counter(record["exclusion"] for record in records if record["exclusion"])
    valid = sorted((r for r in records if r["exclusion"] is None), key=lambda r: r["slot"])
    values = [r["value"] for r in valid]
    attempts = len(records)
    failed = sum(outcomes.get(name, 0) for name in FAILED_OUTCOMES)
    cancelled = outcomes.get("cancelled", 0)
    excluded = sum(1 for r in records if r["exclusion"] is not None)

    def available(key: str, names: Sequence[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name in names:
            present = [r[key][name] for r in valid if r[key] and r[key].get(name) is not None]
            out[name] = {
                "available": len(present),
                "valid_samples": len(valid),
                "median": median(present) if present else None,
            }
        return out

    return {
        "side": side,
        "attempts": attempts,
        "outcomes": {name: outcomes.get(name, 0) for name in OUTCOMES},
        "failed": failed,
        "cancelled": cancelled,
        "excluded": excluded,
        "rates": {
            "failed": _ratio(failed, attempts),
            "cancelled": _ratio(cancelled, attempts),
            "excluded": _ratio(excluded, attempts),
        },
        "exclusions": dict(sorted(exclusions.items())),
        "excluded_runs": sorted(
            (
                {"run_id": r["run_id"], "slot": r["slot"], "reason": r["exclusion"]}
                for r in records
                if r["exclusion"] is not None
            ),
            key=lambda item: (item["slot"], item["run_id"]),
        ),
        "valid_samples": len(valid),
        "samples": [{"run_id": r["run_id"], "slot": r["slot"], "value": r["value"]} for r in valid],
        "median": median(values) if values else None,
        "range": [min(values), max(values)] if values else None,
        "sample_sufficient": len(valid) >= MIN_DESCRIPTIVE_SAMPLES,
        "execution": {
            "executed_now": available("execution", ("executed_now",))["executed_now"],
            "verified_from_cache": available("execution", ("verified_from_cache",))["verified_from_cache"],
        },
        "timings_ms": available("timings_ms", TIMING_NAMES),
        "identity": identity,
        "p95": p95_for_cohort(pool, cohort, as_of),
    }


def compare_experiment(
    declaration: ExperimentDeclaration,
    observations: Iterable[RunObservation],
    *,
    as_of: str,
    history: Iterable[RunObservation] = (),
) -> Dict[str, Any]:
    """Compare baseline and candidate observations for one declared experiment.

    ``history`` contributes only to the p95 cohort window; it is never compared directly.
    Identical inputs (in any order) produce identical output.
    """
    if not isinstance(declaration, ExperimentDeclaration):
        raise PerformanceCompareError("declaration must be an ExperimentDeclaration")
    parse_utc_anchor(as_of)
    plan = build_plan(declaration)
    plan_by_slot = {entry["slot"]: entry for entry in plan}
    declared = declaration.allowed_variables

    ordered_input = list(observations)
    for obs in ordered_input:
        _check_shape(obs)
    ordered = sorted(ordered_input, key=lambda o: (o.side, o.slot, str(o.run_id)))
    records: List[Dict[str, Any]] = []
    reasons: List[Dict[str, Any]] = []
    seen_runs: set = set()
    seen_slots: set = set()
    for obs in ordered:
        record = _normalize(obs, declaration)
        entry = plan_by_slot.get(obs.slot)
        if entry is not None and entry["side"] == obs.side:
            record["ordinal"] = entry["ordinal"]
        else:
            _exclude(record, "plan_deviation")
        if str(obs.run_id) in seen_runs or (obs.side, obs.slot) in seen_slots:
            _exclude(record, "duplicate_observation")
            reasons.append(_within_reason("duplicate_observation", "run_id", obs.side, None, str(obs.run_id)))
        seen_runs.add(str(obs.run_id))
        seen_slots.add((obs.side, obs.slot))
        records.append(record)

    by_side = {side: [r for r in records if r["side"] == side] for side in SIDES}
    representatives: Dict[str, Dict[str, Any]] = {}
    for side in SIDES:
        # Seed runs produce the warm cache and carry their own seed input digest, so they
        # are excluded from identity checks as well as from warm samples.
        with_identity = sorted(
            (
                r
                for r in by_side[side]
                if r["identity"] is not None and r["exclusion"] not in SEED_EXCLUSIONS
            ),
            key=lambda r: (r["slot"], str(r["run_id"])),
        )
        if not with_identity:
            legacy = any(r["exclusion"] == "quality_legacy-limited" for r in by_side[side])
            code = "legacy_limited" if legacy else "identity_unavailable"
            detail = sorted({r["exclusion"] or "identity_not_recorded" for r in by_side[side]})
            reasons.append(_within_reason(code, "identity", side, None, detail))
            continue
        head = with_identity[0]
        representatives[side] = head
        for other in with_identity:
            if other["identity"]["profile"] != declaration.profile:
                reasons.append(_within_reason("profile_mismatch", "profile", side, declaration.profile, other["identity"]["profile"]))
            if other is not head:
                reasons.extend(_diff_within(side, head["identity"], other["identity"]))

    allowed: List[Dict[str, Any]] = []
    if len(representatives) == 2:
        cross_reasons, allowed = _diff_cross(
            representatives["baseline"]["identity"], representatives["candidate"]["identity"], declared
        )
        reasons.extend(cross_reasons)

    cohorts = {side: representatives[side]["cohort"] if side in representatives else None for side in SIDES}
    history_records = []
    seen_history: set = set()
    for obs in history:
        _check_shape(obs)
        if str(obs.run_id) in seen_runs or str(obs.run_id) in seen_history:
            continue
        seen_history.add(str(obs.run_id))
        history_records.append(_normalize(obs, declaration))
    pool = [r for r in records + history_records if r["exclusion"] is None]

    sides = {
        side: _side_report(
            side,
            by_side[side],
            representatives[side]["identity"] if side in representatives else None,
            cohorts[side],
            pool,
            as_of,
        )
        for side in SIDES
    }
    insufficiency = [
        {"side": side, "valid_samples": sides[side]["valid_samples"], "required": MIN_DESCRIPTIVE_SAMPLES}
        for side in SIDES
        if not sides[side]["sample_sufficient"]
    ]
    reasons = sorted(reasons, key=lambda item: (item["code"], item["field"], str(item.get("side"))))
    if reasons:
        classification = "incomparable"
    elif insufficiency:
        classification = "insufficient-evidence"
    else:
        classification = "comparable"

    comparison = None
    if classification == "comparable":
        comparison = _comparison(records, sides, declaration.metric)

    return {
        "policy": {
            "version": POLICY_VERSION,
            "p95": {
                "version": P95_POLICY_VERSION,
                "min_valid_runs": P95_MIN_VALID_RUNS,
                "window_days": P95_WINDOW_DAYS,
                "window": "(as_of - window_days, as_of]",
            },
            "min_descriptive_samples": MIN_DESCRIPTIVE_SAMPLES,
            "allowed_variables_vocabulary": list(ALLOWED_VARIABLES),
        },
        "experiment": {
            "id": declaration.experiment_id,
            "profile": declaration.profile,
            "allowed_variables": list(declared),
            "planned_runs_per_side": declaration.planned_runs_per_side,
            "plan_kind": declaration.plan_kind,
            "metric": declaration.metric,
            "plan": plan,
        },
        "as_of": as_of,
        "classification": classification,
        "reasons": reasons,
        "allowed_differences": sorted(allowed, key=lambda item: item["field"]),
        "insufficiency": insufficiency,
        "sides": sides,
        "comparison": comparison,
    }


def _comparison(records: List[Dict[str, Any]], sides: Mapping[str, Any], metric: str) -> Dict[str, Any]:
    baseline_median = sides["baseline"]["median"]
    candidate_median = sides["candidate"]["median"]
    delta = candidate_median - baseline_median
    ratio = delta / baseline_median if baseline_median else None

    valid = [r for r in records if r["exclusion"] is None]
    by_key = {(r["side"], r["ordinal"]): r for r in valid if r["ordinal"] is not None}
    paired = []
    for ordinal in sorted({r["ordinal"] for r in valid if r["ordinal"] is not None}):
        base, cand = by_key.get(("baseline", ordinal)), by_key.get(("candidate", ordinal))
        if base is not None and cand is not None:
            paired.append(cand["value"] - base["value"])
    result: Dict[str, Any] = {
        "metric": metric,
        "unit": "milliseconds",
        "median_delta": delta,
        "median_delta_ratio": ratio,
        "paired": {
            "pairs": len(paired),
            "median_delta": median(paired) if paired else None,
            "deltas": paired,
        },
        "direction": "candidate-higher" if delta > 0 else "candidate-lower" if delta < 0 else "equal-median",
    }
    if metric == "wall_clock_ms":
        budget = min(OVERHEAD_BUDGET_RATIO * baseline_median, OVERHEAD_BUDGET_CAP_MS)
        result["overhead"] = {"budget_ms": budget, "delta_ms": delta}
    else:
        result["overhead"] = None
    return result
