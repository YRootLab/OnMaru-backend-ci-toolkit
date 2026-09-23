from datetime import datetime, timedelta, timezone
from pipeline_toolkit.pipeline import Job, critical_path

def test_dag_distinguishes_queue_execution_work_wall_and_idle_time():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    jobs = [
        Job("a", (), t, t + timedelta(seconds=5), "success", t - timedelta(seconds=2)),
        Job("b", ("a",), t + timedelta(seconds=7), t + timedelta(seconds=10), "success", t + timedelta(seconds=6)),
    ]
    metrics = critical_path(jobs)
    assert metrics.work_seconds == 8
    assert metrics.wall_clock_seconds == 10
    assert metrics.queue_seconds == 3
    assert metrics.idle_seconds == 2
    assert metrics.critical_path == ("a", "b")
