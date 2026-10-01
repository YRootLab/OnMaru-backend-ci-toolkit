"""Normalize completed GitHub Actions API responses without guessing missing timing data."""

from __future__ import annotations

from datetime import datetime
from typing import Any


MAX_JOBS = 256
MAX_STEPS_PER_JOB = 256


def _seconds(start: Any, end: Any) -> tuple[float | None, str]:
    if not start or not end:
        return None, "unavailable"
    try:
        first = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        last = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        if first.tzinfo is None or last.tzinfo is None or last < first:
            return None, "invalid"
        return round((last - first).total_seconds(), 3), "available"
    except (TypeError, ValueError):
        return None, "invalid"


def normalize_actions_timeline(run: dict[str, Any], jobs_response: dict[str, Any]) -> dict[str, Any]:
    """Produce versioned consumer-local evidence from one run attempt and all job pages.

    ``jobs_response`` must contain the GitHub API ``total_count``. A short page is
    marked partial; callers must fetch every page before exporting telemetry.
    """
    if not isinstance(run, dict) or not isinstance(jobs_response, dict):
        raise ValueError("run and jobs response must be objects")
    run_id, attempt = run.get("id"), run.get("run_attempt")
    if not isinstance(run_id, int) or run_id <= 0 or not isinstance(attempt, int) or attempt <= 0:
        raise ValueError("run id and attempt must be positive integers")
    raw_jobs = jobs_response.get("jobs")
    total_count = jobs_response.get("total_count")
    if not isinstance(raw_jobs, list) or not isinstance(total_count, int) or total_count < len(raw_jobs):
        raise ValueError("jobs and total_count must describe a valid Actions API response")
    if len(raw_jobs) > MAX_JOBS or total_count > MAX_JOBS:
        raise ValueError("job count exceeds collection bound")

    jobs: list[dict[str, Any]] = []
    issues: list[str] = []
    seen_ids: set[int] = set()
    if len(raw_jobs) != total_count:
        issues.append("partial_jobs")
    for raw in raw_jobs:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), int) or raw["id"] in seen_ids:
            raise ValueError("job ids must be unique integers")
        seen_ids.add(raw["id"])
        raw_steps = raw.get("steps") or []
        if not isinstance(raw_steps, list) or len(raw_steps) > MAX_STEPS_PER_JOB:
            raise ValueError("steps exceed collection bound or are invalid")
        duration, quality = _seconds(raw.get("started_at"), raw.get("completed_at"))
        if quality != "available":
            issues.append("job_timestamp_" + quality)
        steps = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                raise ValueError("steps must be objects")
            step_duration, step_quality = _seconds(raw_step.get("started_at"), raw_step.get("completed_at"))
            if step_quality != "available":
                issues.append("step_timestamp_" + step_quality)
            steps.append({
                "number": raw_step.get("number"), "name": raw_step.get("name"),
                "conclusion": raw_step.get("conclusion"), "started_at": raw_step.get("started_at"),
                "completed_at": raw_step.get("completed_at"), "duration_seconds": step_duration,
                "duration_quality": step_quality,
            })
        jobs.append({
            "id": raw["id"], "name": raw.get("name"), "conclusion": raw.get("conclusion"),
            "started_at": raw.get("started_at"), "completed_at": raw.get("completed_at"),
            "duration_seconds": duration, "duration_quality": quality, "steps": steps,
        })

    complete_jobs = [job for job in jobs if job["duration_quality"] == "available"]
    observed_window, window_quality = (None, "unavailable")
    if complete_jobs:
        observed_window, window_quality = _seconds(
            min(job["started_at"] for job in complete_jobs),
            max(job["completed_at"] for job in complete_jobs),
        )
    if len(complete_jobs) != total_count:
        window_quality = "partial" if observed_window is not None else "unavailable"
    # GitHub's run.updated_at is not a guaranteed workflow completion timestamp.
    # Do not convert it into a precise workflow duration or DAG critical path.
    return {
        "schema_version": 1,
        "run": {"id": run_id, "attempt": attempt, "conclusion": run.get("conclusion"),
                "html_url": run.get("html_url"), "head_sha": run.get("head_sha")},
        "jobs": jobs,
        "quality": {"status": "partial" if issues else "complete", "issues": sorted(set(issues))},
        "metrics": {
            "observed_job_window_seconds": observed_window,
            "observed_job_window_quality": window_quality,
            "sum_job_work_seconds": round(sum(job["duration_seconds"] for job in complete_jobs), 3),
            "sum_job_work_quality": "complete" if len(complete_jobs) == total_count else "partial",
            "workflow_wall_clock_seconds": None,
            "workflow_wall_clock_quality": "unavailable",
            "dag_critical_path_seconds": None,
            "dag_critical_path_quality": "unavailable",
            "runner_queue_seconds": None,
            "runner_queue_quality": "unavailable",
        },
    }
