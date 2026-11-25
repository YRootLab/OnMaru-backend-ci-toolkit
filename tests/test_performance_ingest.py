import copy
import hashlib
import json
from pathlib import Path

import pytest

from pipeline_toolkit.normalize.performance import (
    MAX_ARCHIVE_BYTES,
    map_job_name,
    normalize_execution,
    select_run_attempt,
)
from pipeline_toolkit.telemetry.timeline import normalize_actions_timeline

FIXTURES = Path(__file__).parent / "fixtures"
RUN_JOBS = json.loads((FIXTURES / "github-actions/performance-run.json").read_text())
ENVELOPE = json.loads((FIXTURES / "performance-evidence/valid.json").read_text())
SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def timeline(run_overrides=None, jobs=None, total=None):
    run = dict(RUN_JOBS["run"], **(run_overrides or {}))
    payload = {"total_count": total if total is not None else len(jobs or RUN_JOBS["jobs"]["jobs"]),
               "jobs": copy.deepcopy(jobs if jobs is not None else RUN_JOBS["jobs"]["jobs"])}
    return normalize_actions_timeline(run, payload)


def artifact(envelope=None, artifact_id=5, name="ci-performance-evidence", **extra):
    raw = json.dumps(envelope if envelope is not None else ENVELOPE, sort_keys=True).encode("utf-8")
    return dict({"id": artifact_id, "name": name, "size_in_bytes": len(raw), "data": raw}, **extra)


def envelope_with(**changes):
    document = copy.deepcopy(ENVELOPE)
    for path, value in changes.items():
        if "__" in path:
            section, key = path.split("__")
            document[section][key] = value
        else:
            document[path] = value
    return document


def test_same_run_actions_and_performance_identity_is_preserved_in_manifest():
    raw = json.dumps(ENVELOPE, sort_keys=True).encode("utf-8")
    manifest = normalize_execution(timeline(), [artifact()])
    identity = manifest["identity"]
    assert identity["repository"] == "YRootLab/OnMaru-backend"
    assert identity["commit_sha"] == SHA
    assert identity["run_id"] == 24712345678
    assert identity["run_attempt"] == 1
    assert identity["workflow"] == "verify"
    assert identity["same_run"] is True
    assert identity["performance_artifact_digest"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert manifest["performance"]["status"] == "joined"
    assert manifest["performance"]["quality"] == "complete"
    assert manifest["quality"] == {"status": "complete", "issues": []}
    assert manifest["source"]["verdict"] == "success"
    assert manifest["clock"]["alignment"] == "aligned"
    assert manifest["clock"]["overlap"] == "consistent"


@pytest.mark.parametrize("changes, reason", [
    ({"source__commit_sha": "b" * 40}, "foreign_sha"),
    ({"source__run_attempt": 2}, "foreign_attempt"),
    ({"source__workflow_run_id": "999"}, "foreign_run"),
    ({"source__repository": "Other/repo"}, "foreign_repository"),
])
def test_foreign_identity_is_rejected_and_actions_evidence_is_kept(changes, reason):
    manifest = normalize_execution(timeline(), [artifact(envelope_with(**changes))])
    assert manifest["performance"]["status"] == "rejected"
    assert manifest["identity"]["same_run"] is False
    assert manifest["identity"]["performance_artifact_digest"] is None
    assert manifest["performance"].get("timings_ms") == {name: None for name in
                                                        ("container_prepare", "context_init", "flyway",
                                                         "gradle_task", "tests")}
    assert manifest["performance_artifacts"][0]["reason"] == reason
    assert f"performance_artifact_{reason}:5" in manifest["quality"]["issues"]
    assert manifest["quality"]["status"] == "partial"
    assert manifest["jobs"][0]["logical_id"] == "spring-full"


def test_unverifiable_head_sha_and_legacy_attempt_are_never_joined():
    manifest = normalize_execution(timeline(run_overrides={"head_sha": None}), [artifact()])
    assert manifest["performance_artifacts"][0]["reason"] == "unverified_sha"
    legacy = json.loads((FIXTURES / "performance-evidence/legacy.json").read_text())
    manifest = normalize_execution(timeline(), [artifact(legacy)])
    assert manifest["performance_artifacts"][0]["reason"] == "foreign_attempt"


def test_oversized_archive_is_rejected_before_any_parsing():
    huge_metadata = artifact(size_in_bytes=MAX_ARCHIVE_BYTES + 1, data=None)
    assert normalize_execution(timeline(), [huge_metadata])["performance_artifacts"][0]["reason"] == "oversized_archive"
    huge_bytes = {"id": 6, "name": "ci-performance-evidence", "data": b"x" * (MAX_ARCHIVE_BYTES + 1)}
    result = normalize_execution(timeline(), [huge_bytes])
    assert result["performance_artifacts"][0]["reason"] == "oversized_archive"
    assert result["performance"]["status"] == "rejected"


def test_duplicate_fixture_is_quarantined_not_resolved_by_input_order():
    first = artifact(artifact_id=5)
    second = artifact(artifact_id=6)
    for ordering in ([first, second], [second, first]):
        manifest = normalize_execution(timeline(), ordering)
        assert manifest["performance"]["status"] == "rejected"
        assert manifest["identity"]["same_run"] is False
        assert {r["reason"] for r in manifest["performance_artifacts"]} == {"duplicate_artifact"}
    same_id = normalize_execution(timeline(), [artifact(artifact_id=5), artifact(artifact_id=5)])
    assert same_id["performance"]["status"] == "rejected"


@pytest.mark.parametrize("extra, reason", [
    ({"expired": True}, "expired"),
    ({"data": None}, "not_downloaded"),
    ({"id": True}, "invalid_metadata"),
    ({"name": "../../escape"}, "invalid_metadata"),
    ({"data": b'{"schema":"ci-performance-evidence/1.0","schema":"x"}'}, "invalid_envelope"),
    ({"data": b"\xff\xfe"}, "invalid_envelope"),
    ({"data": b'{"schema": "module-evidence/1.0"}'}, "invalid_envelope"),
])
def test_invalid_or_unavailable_artifacts_have_explicit_reasons(extra, reason):
    manifest = normalize_execution(timeline(), [artifact(**extra)])
    assert manifest["performance_artifacts"][0]["reason"] == reason
    assert manifest["performance"]["status"] == "rejected"


def test_korean_display_name_change_keeps_logical_id_and_unmapped_jobs_are_other():
    renamed = copy.deepcopy(RUN_JOBS["jobs"]["jobs"])
    renamed[0]["name"] = "[spring-full] 전체 스프링 회귀 검증 (표시명 변경)"
    before = normalize_execution(timeline(), [])["jobs"]
    after = normalize_execution(timeline(jobs=renamed), [])["jobs"]
    assert before[0]["display_name"] != after[0]["display_name"]
    assert before[0]["logical_id"] == after[0]["logical_id"] == "spring-full"
    assert before[0]["mapping_quality"] == after[0]["mapping_quality"] == "marker"
    by_id = {job["id"]: job for job in before}
    assert by_id[802]["logical_id"] == "spring-affected"
    assert by_id[803]["logical_id"] == "other"
    assert by_id[803]["mapping_quality"] == "unmapped"
    catalog = normalize_execution(timeline(), [])["job_catalog"]
    assert catalog == {"quality": "partial", "unmapped_jobs": 1}


def test_unknown_or_bare_marker_names_map_to_other():
    for name in ("[spring-everything] 전체", "[Spring-Full] 대문자", "스프링 전체 테스트", None, 3):
        assert map_job_name(name) == ("other", "unmapped")
    assert map_job_name("[spring-full]") == ("spring-full", "marker")


def test_nested_spans_produce_no_sum_and_critical_path_stays_unavailable():
    manifest = normalize_execution(timeline(), [artifact()])
    performance = manifest["performance"]
    assert performance["timings_ms"]["tests"] == 91000.0
    assert performance["timing_nesting"] == "unknown"
    assert performance["nested_sum_ms"] is None
    assert performance["longest_span_ms"] == 91000.0
    assert manifest["metrics"]["critical_path_seconds"] is None
    assert manifest["metrics"]["critical_path_quality"] == "unavailable"
    assert manifest["metrics"]["critical_path_reason"] == "no_causal_graph"


def test_span_longer_than_job_window_marks_overlap_inconsistent():
    stretched = envelope_with(timings_ms={"tests": 9_000_000.0})
    manifest = normalize_execution(timeline(), [artifact(stretched)])
    assert manifest["clock"]["overlap"] == "inconsistent"
    assert "span_exceeds_job_window" in manifest["quality"]["issues"]


def test_clock_anchor_outside_window_and_unknown_uncertainty_are_visible():
    late = envelope_with(clock__utc_anchor="2026-11-21T00:00:00.000Z")
    manifest = normalize_execution(timeline(), [artifact(late)])
    assert manifest["clock"]["alignment"] == "outside"
    assert "clock_outside_job_window" in manifest["quality"]["issues"]
    unknown = envelope_with(clock__uncertainty_ms=None)
    manifest = normalize_execution(timeline(), [artifact(unknown)])
    assert "clock_uncertainty_unknown" in manifest["quality"]["issues"]


def test_unavailable_performance_never_estimates_configuration_or_bytes_from_steps():
    jobs = copy.deepcopy(RUN_JOBS["jobs"]["jobs"])
    jobs[0]["steps"] = [{"number": 1, "name": "Configure Gradle", "conclusion": "success",
                         "started_at": "2026-11-20T02:59:10Z", "completed_at": "2026-11-20T02:59:20Z"}]
    unavailable = json.loads((FIXTURES / "performance-evidence/unavailable.json").read_text())
    manifest = normalize_execution(timeline(jobs=jobs), [artifact(unavailable)])
    assert manifest["performance"]["status"] == "joined"
    assert manifest["performance"]["quality"] == "unavailable"
    assert all(value is None for value in manifest["performance"]["timings_ms"].values())
    assert manifest["performance"]["longest_span_ms"] is None
    declared = {name: layer["state"] for name, layer in unavailable["cache"]["cacheIdentity"]["layers"].items()}
    layers = manifest["performance"]["cache"]["layers"]
    for name, state in layers.items():
        assert state == declared.get(name, "unknown")
    assert layers["configuration"] == declared.get("configuration", "unknown")
    assert "performance_quality_unavailable" in manifest["quality"]["issues"]


def test_partial_performance_quality_propagates_but_does_not_upgrade_source():
    partial = json.loads((FIXTURES / "performance-evidence/partial.json").read_text())
    manifest = normalize_execution(timeline(), [artifact(partial)])
    assert manifest["performance"]["status"] == "joined"
    assert manifest["performance"]["quality"] == "partial"
    assert manifest["quality"]["status"] == "partial"


@pytest.mark.parametrize("run_conclusion", ["cancelled", "failure", "timed_out", "skipped", None])
def test_failed_or_cancelled_source_never_becomes_success_even_with_complete_performance(run_conclusion):
    manifest = normalize_execution(timeline(run_overrides={"conclusion": run_conclusion}), [artifact()])
    assert manifest["source"]["verdict"] != "success"
    assert manifest["source"]["verdict"] == (run_conclusion or "unknown")
    assert manifest["performance"]["quality"] == "complete"


def test_failed_job_or_partial_job_list_is_unverified_not_success():
    failed = copy.deepcopy(RUN_JOBS["jobs"]["jobs"])
    failed[1]["conclusion"] = "failure"
    assert normalize_execution(timeline(jobs=failed), [artifact()])["source"]["verdict"] == "unverified"
    partial = normalize_execution(timeline(total=4), [artifact()])
    assert partial["source"]["verdict"] == "unverified"
    assert "timeline:partial_jobs" in partial["quality"]["issues"]


def test_source_conclusion_and_export_status_are_separate_fields():
    manifest = normalize_execution(timeline(), [artifact()])
    assert manifest["export"] == {"status": "not-exported"}
    assert set(manifest["source"]) == {"conclusion", "verdict", "run_url"}
    assert manifest["source"]["conclusion"] == "success"


def test_manifest_digest_is_deterministic():
    first = normalize_execution(timeline(), [artifact()])
    second = normalize_execution(timeline(), [artifact()])
    assert first == second
    assert first["manifest_digest"].startswith("sha256:")


def test_collection_bounds_and_timeline_shape_fail_closed():
    with pytest.raises(ValueError, match="bound"):
        normalize_execution(timeline(), [artifact()] * 17)
    with pytest.raises(ValueError, match="timeline"):
        normalize_execution({"run": {}}, [])


def test_duplicate_run_attempts_are_selected_explicitly_and_conflicts_fail():
    first = timeline()
    attempt_two_jobs = [dict(job, run_attempt=2) for job in RUN_JOBS["jobs"]["jobs"]]
    second = timeline(run_overrides={"run_attempt": 2}, jobs=attempt_two_jobs)
    selected, issues = select_run_attempt([first, second], 24712345678)
    assert selected["identity"]["run_attempt"] == 2
    assert "superseded_attempt:1" in issues
    selected, issues = select_run_attempt([first, second], 24712345678, attempt=1)
    assert selected["identity"]["run_attempt"] == 1
    assert "superseded_attempt:2" in issues
    selected, issues = select_run_attempt([first, first], 24712345678)
    assert "duplicate_attempt_collapsed:1" in issues
    conflicting = copy.deepcopy(first)
    conflicting["evidence_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="conflicting"):
        select_run_attempt([first, conflicting], 24712345678)
    with pytest.raises(ValueError, match="not present"):
        select_run_attempt([first], 24712345678, attempt=3)
    with pytest.raises(ValueError, match="no timeline"):
        select_run_attempt([first], 999)
