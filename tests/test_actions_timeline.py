import pytest

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
