from pipeline_toolkit.github.dag_payload import jobs_from_payload
from pipeline_toolkit.pipeline import critical_path

def test_actions_payload_preserves_matrix_retry_and_skipped_jobs():
    jobs = jobs_from_payload({
        "jobs": [
            {"id": 1, "name": "build (py3.11)", "needs": [], "status": "completed", "conclusion": "success", "started_at": "2026-01-01T00:00:00Z", "completed_at": "2026-01-01T00:00:05Z", "run_attempt": 1},
            {"id": 2, "name": "test (py3.11)", "needs": ["build (py3.11)"], "status": "completed", "conclusion": "failure", "started_at": "2026-01-01T00:00:05Z", "completed_at": "2026-01-01T00:00:08Z", "run_attempt": 1},
            {"id": 3, "name": "deploy", "needs": ["test (py3.11)"], "status": "completed", "conclusion": "skipped", "started_at": None, "completed_at": None, "run_attempt": 1}
        ]
    })
    assert jobs[1].status == "failed"
    assert jobs[2].status == "skipped"
    assert critical_path(jobs).critical_path == ("1", "2")
