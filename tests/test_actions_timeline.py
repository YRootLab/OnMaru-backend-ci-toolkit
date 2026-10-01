import pytest
import copy
import hashlib
import json
from pathlib import Path

from pipeline_toolkit.github import responses
from pipeline_toolkit.telemetry.timeline import normalize_actions_timeline


def run(attempt=1, conclusion="success"):
    return {"id": 42, "run_attempt": attempt, "conclusion": conclusion,
            "html_url": "https://github.com/YRootLab/OnMaru-backend/actions/runs/42"}


def job(job_id=7, conclusion="success", started="2026-10-01T00:00:01Z", ended="2026-10-01T00:00:07Z"):
    return {"id": job_id, "name": "verify", "conclusion": conclusion,
            "started_at": started, "completed_at": ended,
            "steps": [{"number": 1, "name": "test", "conclusion": conclusion,
                       "started_at": "2026-10-01T00:00:02Z", "completed_at": "2026-10-01T00:00:06Z"}]}


def test_complete_timeline_keeps_attempt_and_separates_job_window_from_unknown_workflow_time():
    timeline = normalize_actions_timeline(run(attempt=2), {"total_count": 1, "jobs": [job()]})
    assert timeline["schema_version"] == 1
    assert timeline["run"]["attempt"] == 2
    assert timeline["quality"] == {"status": "complete", "issues": []}
    assert timeline["jobs"][0]["steps"][0]["duration_seconds"] == 4
    assert timeline["metrics"]["observed_job_window_seconds"] == 6
    assert timeline["metrics"]["sum_job_work_seconds"] == 6
    assert timeline["metrics"]["workflow_wall_clock_seconds"] is None
    assert timeline["metrics"]["dag_critical_path_seconds"] is None


def test_failure_cancellation_and_missing_timestamps_are_preserved_without_false_durations():
    failed = job(conclusion="failure", ended=None)
    failed["steps"][0]["completed_at"] = "2026-09-30T23:59:59Z"
    timeline = normalize_actions_timeline(run(conclusion="cancelled"), {"total_count": 1, "jobs": [failed]})
    assert timeline["run"]["conclusion"] == "cancelled"
    assert timeline["jobs"][0]["conclusion"] == "failure"
    assert timeline["jobs"][0]["duration_quality"] == "unavailable"
    assert timeline["jobs"][0]["steps"][0]["duration_quality"] == "invalid"
    assert timeline["quality"]["issues"] == ["job_timestamp_unavailable", "step_timestamp_invalid"]
    assert timeline["metrics"]["sum_job_work_quality"] == "partial"


def test_incomplete_pagination_and_duplicate_job_ids_are_not_silently_accepted():
    timeline = normalize_actions_timeline(run(), {"total_count": 2, "jobs": [job()]})
    assert timeline["quality"]["issues"] == ["partial_jobs"]
    assert timeline["metrics"]["observed_job_window_quality"] == "partial"
    with pytest.raises(ValueError, match="unique"):
        normalize_actions_timeline(run(), {"total_count": 2, "jobs": [job(), job()]})


def test_missing_attempt_and_unbounded_collection_fail_closed():
    with pytest.raises(ValueError, match="attempt"):
        normalize_actions_timeline({"id": 42}, {"total_count": 0, "jobs": []})
    with pytest.raises(ValueError, match="bound"):
        normalize_actions_timeline(run(), {"total_count": 257, "jobs": []})


FIXTURE = Path(__file__).parent / "fixtures/github-actions/attempt-failure.json"
TOOLKIT_REF = "b" * 40


def failure_fixture():
    return json.loads(FIXTURE.read_text())


def artifact(payload=None, artifact_id=91):
    content = json.dumps(payload or failure_fixture()["module"], sort_keys=True).encode()
    return {"id": artifact_id, "name": "module-evidence-api", "data": content,
            "digest": "sha256:" + hashlib.sha256(content).hexdigest()}


def evidence(artifacts=None, expected=None, fixture=None):
    fixture = fixture or failure_fixture()
    return normalize_actions_timeline(
        fixture["run"], fixture["jobs"], toolkit_ref=TOOLKIT_REF,
        module_artifacts=[] if artifacts is None else artifacts,
        expected_modules={"api": 701, "worker": 702} if expected is None else expected,
    )


def test_attempt_specific_pagination_collects_205_jobs_without_latest_attempt_leakage():
    collect = getattr(responses, "collect_attempt_jobs", None)
    assert callable(collect), "attempt-specific jobs pagination is missing"
    template = failure_fixture()["jobs"]["jobs"][0]
    def fetch(path):
        assert path.startswith("/repos/example/backend/actions/runs/42/attempts/2/jobs?")
        assert "per_page=100" in path
        page = int(path.rsplit("page=", 1)[1])
        assert page in (1, 2, 3)
        start, stop = (page - 1) * 100, min(page * 100, 205)
        return {"total_count": 205, "jobs": [dict(template, id=1000 + i) for i in range(start, stop)]}
    collected = collect("example/backend", 42, 2, fetch)
    result = normalize_actions_timeline(failure_fixture()["run"], collected)
    assert len(result["jobs"]) == 205
    assert result["jobs"][-1]["id"] == 1204
    assert result["quality"]["status"] == "complete"


def test_collector_marks_empty_later_page_partial_and_rejects_foreign_attempt_or_duplicates():
    collect = getattr(responses, "collect_attempt_jobs", None)
    assert callable(collect), "attempt-specific jobs pagination is missing"
    template = failure_fixture()["jobs"]["jobs"][0]
    result = collect("example/backend", 42, 2, lambda path: {
        "total_count": 2, "jobs": [template] if path.endswith("page=1") else []})
    assert normalize_actions_timeline(failure_fixture()["run"], result)["quality"]["issues"] == ["partial_jobs"]
    with pytest.raises(ValueError, match="attempt"):
        collect("example/backend", 42, 2, lambda path: {"total_count": 1, "jobs": [dict(template, run_attempt=1)]})
    with pytest.raises(ValueError, match="unique"):
        collect("example/backend", 42, 2, lambda path: {"total_count": 2, "jobs": [template, template]})


def test_artifact_join_keeps_failures_and_missing_modules_and_distinct_dag_metric():
    result = evidence([artifact()])
    assert result["modules"][0]["job_id"] == 701
    assert result["modules"][0]["exit_code"] == 1
    assert result["modules"][0]["status"] == "failed"
    assert result["artifact_quality"]["status"] == "partial"
    assert "missing_module:worker" in result["quality"]["issues"]
    assert result["metrics"]["longest_module_duration_seconds"] == 6
    assert result["metrics"]["dag_critical_path_seconds"] is None
    assert result["metrics"]["dag_critical_path_quality"] == "unavailable"


def test_missing_invalid_and_incomplete_artifacts_have_explicit_quality():
    assert evidence()["artifact_quality"]["status"] == "missing"
    bad = artifact()
    bad["digest"] = "sha256:" + "0" * 64
    result = evidence([bad])
    assert result["artifact_quality"]["status"] == "invalid"
    assert "artifact_digest_mismatch:91" in result["quality"]["issues"]
    assert result["modules"] == []
    incomplete = dict(failure_fixture()["module"], complete=False, wall_clock_seconds=None)
    result = evidence([artifact(incomplete)], {"api": 701})
    assert result["artifact_quality"]["status"] == "partial"
    assert result["metrics"]["longest_module_duration_seconds"] is None


@pytest.mark.parametrize("updates", [
    {"schema_version": 2}, {"run_attempt": 1}, {"job_id": 999},
    {"toolkit_ref": "c" * 40}, {"module_id": "../outside"},
    {"wall_clock_seconds": -1}, {"wall_clock_seconds": float("nan")},
    {"wall_clock_seconds": True}, {"complete": "yes"}, {"exit_code": "0"},
    {"wall_clock_seconds": 10 ** 1000},
])
def test_untrusted_module_schema_or_identity_is_never_joined(updates):
    result = evidence([artifact(dict(failure_fixture()["module"], **updates))])
    assert result["modules"] == []
    assert result["artifact_quality"]["status"] == "invalid"


def test_artifact_bounds_and_invalid_json_are_diagnostics_not_execution(tmp_path):
    for content in (b"x" * (1024 * 1024 + 1), b'{"schema_version":1', b'{"schema_version":1,"schema_version":1}', b'[' * 2000):
        result = evidence([{"id": 91, "name": "../../outside", "data": content}])
        assert result["artifact_quality"]["status"] == "invalid"
        assert not result["modules"]
    assert list(tmp_path.iterdir()) == []


def test_digest_identity_is_deterministic_and_changes_with_attempt_or_content():
    f = failure_fixture()
    second = dict(f["module"], module_id="worker", job_id=702, exit_code=0, wall_clock_seconds=3)
    first, other = artifact(), artifact(second, 92)
    result = evidence([first, other])
    shuffled = copy.deepcopy(f)
    shuffled["jobs"]["jobs"].reverse()
    assert result["evidence_digest"] == evidence([other, first], fixture=shuffled)["evidence_digest"]
    assert result["identity"]["run_attempt"] == 2
    assert result["identity"]["toolkit_ref"] == TOOLKIT_REF
    assert result["evidence_digest"].startswith("sha256:")
    f["run"]["run_attempt"] = 3
    f["jobs"]["jobs"] = [dict(j, run_attempt=3) for j in f["jobs"]["jobs"]]
    assert result["evidence_digest"] != evidence([first, other], fixture=f)["evidence_digest"]
    assert result["evidence_digest"] != evidence([artifact(dict(failure_fixture()["module"], wall_clock_seconds=7)), other])["evidence_digest"]


def test_duplicate_artifacts_are_not_counted_twice_or_resolved_by_input_order():
    first = artifact()
    result = evidence([first, first], {"api": 701})
    assert result["artifact_quality"]["status"] == "invalid"
    assert result["modules"] == []
    conflict = artifact(dict(failure_fixture()["module"], wall_clock_seconds=12), 92)
    assert evidence([first, conflict])["evidence_digest"] == evidence([conflict, first])["evidence_digest"]
    assert evidence([first, conflict])["modules"] == []


def test_timestamp_window_compares_instants_instead_of_offset_strings():
    result = normalize_actions_timeline(run(), {"total_count": 2, "jobs": [
        job(1, started="2026-10-01T01:00:00+01:00", ended="2026-10-01T01:00:10+01:00"),
        job(2, started="2026-10-01T00:00:05Z", ended="2026-10-01T00:00:15Z")]})
    assert result["metrics"]["observed_job_window_seconds"] == 15


def test_boolean_identity_and_foreign_attempts_are_rejected():
    with pytest.raises(ValueError):
        normalize_actions_timeline(dict(run(), id=True), {"total_count": 0, "jobs": []})
    with pytest.raises(ValueError, match="attempt"):
        normalize_actions_timeline(run(attempt=2), {"total_count": 1, "jobs": [dict(job(), run_attempt=1)]})


def test_diagnostics_show_failure_step_quality_ref_and_safe_source_url():
    from pipeline_toolkit.reports import diagnostics
    result = evidence([artifact()])
    report = diagnostics.render_actions_diagnostics(result)
    for value in ("module-test (api)", "Run API tests", "cancelled", "missing_module:worker", TOOLKIT_REF,
                  "https://github.com/example/backend/actions/runs/42", result["evidence_digest"],
                  "DAG critical path: unavailable", "Longest module duration: 6"):
        assert value in report
    result["jobs"][0]["name"] = "<script>alert(1)</script>\n[bad](javascript:alert(1))"
    result["run"]["html_url"] = "javascript:alert(1)"
    report = diagnostics.render_actions_diagnostics(result)
    assert "<script>" not in report
    assert "[bad](javascript:" not in report
    assert "Source run: unavailable" in report


@pytest.mark.parametrize("mutation", ["name_object", "name_oversize", "duplicate_step", "bool_attempt", "non_string_time"])
def test_malformed_api_job_fields_fail_closed(mutation):
    raw = job()
    if mutation == "name_object":
        raw["name"] = {"secret": "do not echo"}
    elif mutation == "name_oversize":
        raw["name"] = "x" * 4097
    elif mutation == "duplicate_step":
        raw["steps"].append(dict(raw["steps"][0]))
    elif mutation == "bool_attempt":
        raw["run_attempt"] = True
    else:
        raw["started_at"] = ["2026-10-01T00:00:00Z"]
    with pytest.raises(ValueError):
        normalize_actions_timeline(run(), {"total_count": 1, "jobs": [raw]})


@pytest.mark.parametrize("page", [None, {"total_count": 257, "jobs": []},
    {"total_count": True, "jobs": []}, {"total_count": 1, "jobs": "no"},
    {"total_count": 1, "jobs": [{}]}])
def test_bad_pagination_payloads_fail_closed(page):
    collect = getattr(responses, "collect_attempt_jobs", None)
    assert callable(collect)
    with pytest.raises(ValueError):
        collect("example/backend", 42, 2, lambda path: page)


def test_changed_pagination_total_and_invalid_request_fail_closed():
    collect = getattr(responses, "collect_attempt_jobs", None)
    assert callable(collect)
    raw = failure_fixture()["jobs"]["jobs"][0]
    with pytest.raises(ValueError, match="total changed"):
        collect("example/backend", 42, 2, lambda path: {"total_count": 2 if path.endswith("page=1") else 3, "jobs": [raw]})
    for repository, run_id, attempt in [("../evil/repo", 42, 2), ("example/backend", True, 2), ("example/backend", 42, 0)]:
        with pytest.raises(ValueError):
            collect(repository, run_id, attempt, lambda path: {})


def test_artifact_collection_and_expected_mapping_bounds():
    with pytest.raises(ValueError, match="artifacts"):
        evidence({})
    with pytest.raises(ValueError, match="bound"):
        evidence([artifact()] * 257)
    with pytest.raises(ValueError, match="bound"):
        evidence([{"id": n + 1, "data": b"x" * (1024 * 1024)} for n in range(17)])
    with pytest.raises(ValueError, match="mapping"):
        evidence([], {"../outside": 701})
    with pytest.raises(ValueError, match="expected"):
        evidence([], ["api"])
    for raw in [None, {"id": True, "data": b"{}"}, {"id": 1, "data": "{}"}]:
        assert evidence([raw])["artifact_quality"]["status"] == "invalid"


def test_complete_artifact_join_and_empty_success_diagnostics():
    from pipeline_toolkit.reports.diagnostics import render_actions_diagnostics
    f = failure_fixture()
    f["jobs"] = {"total_count": 1, "jobs": [dict(f["jobs"]["jobs"][0], conclusion="success", steps=[])]}
    data = dict(f["module"], exit_code=0)
    result = evidence([artifact(data)], {"api": 701}, f)
    assert result["artifact_quality"] == {"status": "complete", "issues": []}
    assert result["metrics"]["longest_module_duration_quality"] == "available"
    assert "No observed failed" in render_actions_diagnostics(result)
    assert "None." in render_actions_diagnostics(result)
    bad = dict(result, run=dict(result["run"], html_url="https://[malformed"))
    assert "Source run: unavailable" in render_actions_diagnostics(bad)


def test_artifact_join_requires_immutable_toolkit_ref_and_valid_inputs():
    with pytest.raises(ValueError, match="toolkit_ref"):
        normalize_actions_timeline(run(), {"total_count": 0, "jobs": []}, module_artifacts=[])
    with pytest.raises(ValueError, match="toolkit_ref"):
        normalize_actions_timeline(run(), {"total_count": 0, "jobs": []}, toolkit_ref="main")
    with pytest.raises(ValueError):
        normalize_actions_timeline(None, {"total_count": 0, "jobs": []})
    with pytest.raises(ValueError):
        normalize_actions_timeline(run(), {"total_count": True, "jobs": []})
    with pytest.raises(ValueError):
        normalize_actions_timeline(run(), {"total_count": 1, "jobs": [dict(job(), steps=[None])]})
