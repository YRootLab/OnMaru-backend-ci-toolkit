"""Merge one Actions attempt with ``ci-performance-evidence/1.0`` into a normalized execution.

Pure functions only: no archive extraction, no artifact command execution, no
network access. Performance artifacts are treated as untrusted JSON bytes.

Decisions recorded here:

* Performance evidence joins only when repository, run id, attempt and commit
  SHA all match the Actions attempt. Any mismatch rejects the artifact with an
  explicit reason; the Actions evidence is still kept.
* Performance evidence never changes the source verdict. The source verdict is
  derived from run and job conclusions only, and export status is a separate field.
* Logical job IDs come from an explicit ``[logical-id]`` marker at the start of
  the job display name. Display text after the marker is cosmetic. Anything else
  maps to ``other`` with ``mapping_quality = "unmapped"``.
* Timing spans are reported as individual lower bounds. No sum is produced
  because the envelope carries no causal graph, so nesting is unknown. The
  critical path is ``unavailable``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from pipeline_toolkit.contracts.performance_evidence import (
    LAYER_NAMES,
    SCHEMA_ID,
    TIMING_NAMES,
    PerformanceEvidenceError,
    parse_envelope_text,
)

MANIFEST_SCHEMA = "normalized-execution/1"
MAX_ARCHIVE_BYTES = 1024 * 1024
MAX_PERFORMANCE_ARTIFACTS = 16
OTHER_JOB = "other"
LOGICAL_JOB_IDS = frozenset({
    "change-plan",
    "repository-hygiene",
    "spring-affected",
    "spring-full",
    "contract-validation",
    "ai-quality",
    "required-verdict",
})
_MARKER = re.compile(r"\[([a-z][a-z0-9-]{0,63})\]")
_ARTIFACT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def map_job_name(name: Any) -> tuple[str, str]:
    """Return ``(logical_id, mapping_quality)`` for an Actions job display name."""
    if isinstance(name, str):
        marker = _MARKER.match(name.strip())
        if marker and marker.group(1) in LOGICAL_JOB_IDS:
            return marker.group(1), "marker"
    return OTHER_JOB, "unmapped"


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _check_timeline(timeline: Any) -> None:
    if (not isinstance(timeline, Mapping) or not isinstance(timeline.get("run"), Mapping)
            or not isinstance(timeline.get("identity"), Mapping)
            or not isinstance(timeline.get("jobs"), list)
            or not isinstance(timeline.get("quality"), Mapping)):
        raise ValueError("timeline must be a normalize_actions_timeline result")


def select_run_attempt(timelines: Sequence[Mapping[str, Any]], run_id: int,
                       attempt: int | None = None) -> tuple[dict[str, Any], list[str]]:
    """Pick one attempt of ``run_id`` and report superseded or collapsed records.

    Identical duplicate records for the same attempt collapse to one. Conflicting
    duplicates for the same attempt are rejected. Without an explicit attempt the
    highest attempt wins and the rest are marked superseded.
    """
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("run_id must be a positive integer")
    if attempt is not None and (type(attempt) is not int or attempt <= 0):
        raise ValueError("attempt must be a positive integer")
    by_attempt: dict[int, list[dict[str, Any]]] = {}
    for timeline in timelines:
        _check_timeline(timeline)
        identity = timeline["identity"]
        if identity.get("run_id") != run_id:
            continue
        by_attempt.setdefault(identity.get("run_attempt"), []).append(dict(timeline))
    issues: list[str] = []
    unique: dict[int, dict[str, Any]] = {}
    for number, records in by_attempt.items():
        digests = {record.get("evidence_digest") for record in records}
        if len(digests) > 1:
            raise ValueError(f"conflicting duplicate attempt records for attempt {number}")
        if len(records) > 1:
            issues.append(f"duplicate_attempt_collapsed:{number}")
        unique[number] = records[0]
    if not unique:
        raise ValueError("no timeline for requested run")
    if attempt is not None:
        if attempt not in unique:
            raise ValueError("requested attempt is not present")
        selected_number = attempt
    else:
        selected_number = max(unique)
    for number in sorted(unique):
        if number != selected_number:
            issues.append(f"superseded_attempt:{number}")
    return unique[selected_number], sorted(set(issues))


def _artifact_record(artifact: Mapping[str, Any]) -> dict[str, Any]:
    raw_id = artifact.get("id")
    return {
        "id": raw_id if type(raw_id) is int and raw_id > 0 else None,
        "name": artifact.get("name") if isinstance(artifact.get("name"), str) else None,
        "archive_bytes": artifact.get("size_in_bytes")
        if type(artifact.get("size_in_bytes")) is int else None,
        "digest": None,
        "status": "rejected",
        "reason": None,
    }


def _identity_reason(envelope: Mapping[str, Any], identity: Mapping[str, Any]) -> str | None:
    source = envelope["source"]
    if source["repository"] != identity.get("repository"):
        return "foreign_repository"
    if source["workflow_run_id"] != str(identity.get("run_id")):
        return "foreign_run"
    if source["run_attempt"] != identity.get("run_attempt"):
        return "foreign_attempt"
    if identity.get("head_sha") is None:
        return "unverified_sha"
    if source["commit_sha"] != identity.get("head_sha"):
        return "foreign_sha"
    return None


def _evaluate_artifact(artifact: Any, identity: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not isinstance(artifact, Mapping):
        return {"id": None, "name": None, "archive_bytes": None, "digest": None,
                "status": "rejected", "reason": "invalid_metadata"}, None
    record = _artifact_record(artifact)

    def reject(reason: str) -> tuple[dict[str, Any], None]:
        record["reason"] = reason
        return record, None

    if record["id"] is None or not (record["name"] and _ARTIFACT_NAME.fullmatch(record["name"])):
        return reject("invalid_metadata")
    if artifact.get("expired") is True:
        return reject("expired")
    size = artifact.get("size_in_bytes")
    if size is not None and (type(size) is not int or size < 0):
        return reject("invalid_metadata")
    if type(size) is int and size > MAX_ARCHIVE_BYTES:
        return reject("oversized_archive")
    data = artifact.get("data")
    if data is None:
        return reject("not_downloaded")
    if not isinstance(data, bytes):
        return reject("invalid_metadata")
    if len(data) > MAX_ARCHIVE_BYTES:
        return reject("oversized_archive")
    record["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
    try:
        envelope = parse_envelope_text(data.decode("utf-8"))
    except (PerformanceEvidenceError, UnicodeDecodeError):
        return reject("invalid_envelope")
    reason = _identity_reason(envelope, identity)
    if reason is not None:
        return reject(reason)
    record["status"] = "accepted"
    return record, envelope


def _cache_block(envelope: Mapping[str, Any]) -> dict[str, Any]:
    if envelope["quality"] == "legacy-limited":
        return {"legacy_cache_state": envelope["legacy"]["cache_state"]}
    cache = envelope["cache"]
    layers = cache["cacheIdentity"]["layers"]
    return {
        "experiment_class": cache["experiment_class"],
        "policy_digest": cache["policy_digest"],
        "layers": {name: (layers[name]["state"] if name in layers else "unknown")
                   for name in LAYER_NAMES},
        "seed": cache["cacheIdentity"]["seedProvenance"],
    }


def _window(jobs: Iterable[Mapping[str, Any]]) -> tuple[datetime | None, datetime | None]:
    starts, ends = [], []
    for job in jobs:
        if job.get("duration_quality") != "available":
            continue
        start, end = _instant(job.get("started_at")), _instant(job.get("completed_at"))
        if start is not None and end is not None:
            starts.append(start)
            ends.append(end)
    if not starts:
        return None, None
    return min(starts), max(ends)


def _source_verdict(timeline: Mapping[str, Any]) -> str:
    conclusion = timeline["run"].get("conclusion")
    conclusion = conclusion if isinstance(conclusion, str) and conclusion else "unknown"
    jobs = timeline["jobs"]
    if conclusion == "success":
        all_jobs_ok = bool(jobs) and all(job.get("conclusion") == "success" for job in jobs)
        if timeline["quality"].get("status") == "complete" and all_jobs_ok:
            return "success"
        return "unverified"
    return conclusion


def normalize_execution(timeline: Mapping[str, Any],
                        performance_artifacts: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Merge one Actions attempt with zero or more performance artifacts.

    ``timeline`` must be a ``normalize_actions_timeline`` result. Each performance
    artifact is a mapping with ``id``, ``name``, optional ``size_in_bytes``,
    optional ``expired`` and ``data`` (the raw JSON member bytes, or ``None`` if
    not downloaded).
    """
    _check_timeline(timeline)
    artifacts = list(performance_artifacts or [])
    if len(artifacts) > MAX_PERFORMANCE_ARTIFACTS:
        raise ValueError("performance artifacts exceed collection bound")
    identity = timeline["identity"]
    issues = [f"timeline:{issue}" for issue in timeline["quality"].get("issues", [])]
    if timeline["quality"].get("status") != "complete":
        issues.append("timeline:status_" + str(timeline["quality"].get("status")))

    records, accepted = [], []
    for artifact in artifacts:
        record, envelope = _evaluate_artifact(artifact, identity)
        records.append(record)
        if envelope is not None:
            accepted.append((record, envelope))
    perf_status, envelope_used, perf_record = "absent", None, None
    if records:
        perf_status = "rejected"
        for record in records:
            if record["reason"]:
                issues.append(f"performance_artifact_{record['reason']}:{record['id']}")
    if len(accepted) > 1:
        # Two same-run candidates are a duplicate fixture; neither may be picked by input order.
        for record, _ in accepted:
            record["status"], record["reason"] = "rejected", "duplicate_artifact"
            issues.append(f"performance_artifact_duplicate_artifact:{record['id']}")
    elif accepted:
        perf_record, envelope_used = accepted[0]
        perf_status = "joined"
    if perf_status == "rejected":
        issues.append("performance_rejected")

    jobs = []
    for job in timeline["jobs"]:
        logical_id, mapping_quality = map_job_name(job.get("name"))
        jobs.append({
            "id": job.get("id"),
            "display_name": job.get("name"),
            "logical_id": logical_id,
            "mapping_quality": mapping_quality,
            "conclusion": job.get("conclusion"),
            "duration_seconds": job.get("duration_seconds"),
        })
    unmapped = sum(1 for job in jobs if job["mapping_quality"] == "unmapped")
    window_start, window_end = _window(timeline["jobs"])
    window_seconds = (window_end - window_start).total_seconds() if window_start else None

    performance: dict[str, Any] = {"status": perf_status}
    clock: dict[str, Any] = {"anchor": None, "uncertainty_ms": None, "alignment": "unavailable",
                             "overlap": "unknown", "job_window_start": window_start.isoformat() if window_start else None,
                             "job_window_end": window_end.isoformat() if window_end else None}
    cache = None
    timings: dict[str, Any] = {name: None for name in TIMING_NAMES}
    if envelope_used is not None:
        quality = envelope_used["quality"]
        performance.update({
            "schema": SCHEMA_ID,
            "quality": quality,
            "artifact": {"id": perf_record["id"], "digest": perf_record["digest"],
                         "archive_bytes": perf_record["archive_bytes"]},
        })
        if quality != "complete":
            issues.append(f"performance_quality_{quality}")
        clock_info = envelope_used["clock"]
        uncertainty = clock_info["uncertainty_ms"]
        clock["uncertainty_ms"] = uncertainty
        if uncertainty is None:
            issues.append("clock_uncertainty_unknown")
        anchor = _instant(clock_info["utc_anchor"]) if clock_info["utc_anchor"] else None
        if anchor is not None:
            clock["anchor"] = clock_info["utc_anchor"]
        if anchor is not None and window_start is not None:
            tolerance = (uncertainty or 0) / 1000.0
            inside = (window_start.timestamp() - tolerance) <= anchor.timestamp() <= (window_end.timestamp() + tolerance)
            clock["alignment"] = "aligned" if inside else "outside"
            if not inside:
                issues.append("clock_outside_job_window")
        for name, value in (envelope_used.get("timings_ms") or {}).items():
            timings[name] = value
        spans = [value for value in timings.values() if value is not None]
        longest = max(spans) if spans else None
        if longest is not None and window_seconds is not None:
            tolerance_ms = uncertainty or 0
            if longest > window_seconds * 1000 + tolerance_ms:
                clock["overlap"] = "inconsistent"
                issues.append("span_exceeds_job_window")
            else:
                clock["overlap"] = "consistent"
        cache = _cache_block(envelope_used)
    performance["cache"] = cache
    performance["timings_ms"] = timings
    performance["timing_nesting"] = "unknown"
    performance["nested_sum_ms"] = None
    performance["longest_span_ms"] = max(
        (v for v in timings.values() if v is not None), default=None)

    source_verdict = _source_verdict(timeline)
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "identity": {
            "repository": identity.get("repository"),
            "commit_sha": identity.get("head_sha"),
            "run_id": identity.get("run_id"),
            "run_attempt": identity.get("run_attempt"),
            "toolkit_ref": identity.get("toolkit_ref"),
            "workflow": envelope_used["source"]["workflow"] if envelope_used else None,
            "performance_artifact_digest": perf_record["digest"] if perf_record else None,
            "same_run": perf_status == "joined",
            "actions_evidence_digest": timeline.get("evidence_digest"),
        },
        "source": {
            "conclusion": timeline["run"].get("conclusion"),
            "verdict": source_verdict,
            "run_url": timeline["run"].get("html_url"),
        },
        "export": {"status": "not-exported"},
        "jobs": jobs,
        "job_catalog": {
            "quality": "partial" if unmapped else "complete",
            "unmapped_jobs": unmapped,
        },
        "clock": clock,
        "performance": performance,
        "performance_artifacts": [r for r in records],
        "metrics": {
            "critical_path_seconds": None,
            "critical_path_quality": "unavailable",
            "critical_path_reason": "no_causal_graph",
            "observed_job_window_seconds": timeline["metrics"].get("observed_job_window_seconds"),
        },
        "quality": {"status": "partial" if issues else "complete", "issues": sorted(set(issues))},
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    manifest["manifest_digest"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return manifest
