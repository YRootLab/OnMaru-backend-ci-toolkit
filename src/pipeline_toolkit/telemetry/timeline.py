"""Normalize completed GitHub Actions API responses without guessing missing timing data."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

from pipeline_toolkit.github.artifacts import TOOLKIT_REF, join_module_artifacts


MAX_JOBS = 256
MAX_STEPS_PER_JOB = 256


def _bounded_fields(value, fields):
    for field in fields:
        item = value.get(field)
        if item is not None and (not isinstance(item, str) or len(item) > 4096):
            raise ValueError(f"{field} must be bounded text or null")


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


def normalize_actions_timeline(run: dict[str, Any], jobs_response: dict[str, Any], *,
                               toolkit_ref: str | None = None,
                               module_artifacts: list[dict[str, Any]] | None = None,
                               expected_modules: dict[str, int] | None = None) -> dict[str, Any]:
    """Produce versioned consumer-local evidence from one run attempt and all job pages.

    ``jobs_response`` must contain the GitHub API ``total_count``. A short page is
    marked partial; callers must fetch every page before exporting telemetry.
    """
    if not isinstance(run, dict) or not isinstance(jobs_response, dict):
        raise ValueError("run and jobs response must be objects")
    run_id, attempt = run.get("id"), run.get("run_attempt")
    if type(run_id) is not int or run_id <= 0 or type(attempt) is not int or attempt <= 0:
        raise ValueError("run id and attempt must be positive integers")
    if toolkit_ref is not None and (not isinstance(toolkit_ref, str) or not TOOLKIT_REF.fullmatch(toolkit_ref)):
        raise ValueError("toolkit_ref must be an immutable lowercase 40-character SHA")
    if (module_artifacts is not None or expected_modules is not None) and toolkit_ref is None:
        raise ValueError("toolkit_ref is required for module artifacts")
    _bounded_fields(run, ("conclusion", "html_url", "head_sha"))
    if isinstance(run.get("repository"), dict):
        _bounded_fields(run["repository"], ("full_name",))
    raw_jobs = jobs_response.get("jobs")
    total_count = jobs_response.get("total_count")
    if not isinstance(raw_jobs, list) or type(total_count) is not int or total_count < len(raw_jobs):
        raise ValueError("jobs and total_count must describe a valid Actions API response")
    if len(raw_jobs) > MAX_JOBS or total_count > MAX_JOBS:
        raise ValueError("job count exceeds collection bound")

    jobs: list[dict[str, Any]] = []
    issues: list[str] = []
    seen_ids: set[int] = set()
    if len(raw_jobs) != total_count:
        issues.append("partial_jobs")
    for raw in raw_jobs:
        if not isinstance(raw, dict) or type(raw.get("id")) is not int or raw["id"] <= 0 or raw["id"] in seen_ids:
            raise ValueError("job ids must be unique integers")
        if any(type(raw.get(key, value)) is not int or raw.get(key, value) != value for key, value in (("run_id", run_id), ("run_attempt", attempt))):
            raise ValueError("job run or attempt does not match requested attempt")
        _bounded_fields(raw, ("name", "conclusion", "started_at", "completed_at"))
        seen_ids.add(raw["id"])
        raw_steps = raw.get("steps", [])
        if not isinstance(raw_steps, list) or len(raw_steps) > MAX_STEPS_PER_JOB:
            raise ValueError("steps exceed collection bound or are invalid")
        duration, quality = _seconds(raw.get("started_at"), raw.get("completed_at"))
        if quality != "available":
            issues.append("job_timestamp_" + quality)
        steps = []
        step_numbers = set()
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                raise ValueError("steps must be objects")
            _bounded_fields(raw_step, ("name", "conclusion", "started_at", "completed_at"))
            number = raw_step.get("number")
            if type(number) is not int or number <= 0 or number in step_numbers:
                raise ValueError("step numbers must be unique positive integers")
            step_numbers.add(number)
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

    jobs.sort(key=lambda job: job["id"])
    for normalized_job in jobs:
        normalized_job["steps"].sort(key=lambda step: step["number"])

    complete_jobs = [job for job in jobs if job["duration_quality"] == "available"]
    observed_window, window_quality = (None, "unavailable")
    if complete_jobs:
        observed_window, window_quality = _seconds(
            min((job["started_at"] for job in complete_jobs), key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))),
            max((job["completed_at"] for job in complete_jobs), key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))),
        )
    if len(complete_jobs) != total_count:
        window_quality = "partial" if observed_window is not None else "unavailable"
    # GitHub's run.updated_at is not a guaranteed workflow completion timestamp.
    # Do not convert it into a precise workflow duration or DAG critical path.
    modules, artifacts, artifact_quality = [], [], {"status": "unavailable", "issues": []}
    if module_artifacts is not None or expected_modules is not None:
        modules, artifacts, artifact_quality = join_module_artifacts(
            module_artifacts if module_artifacts is not None else [], run_id=run_id, attempt=attempt,
            toolkit_ref=toolkit_ref, job_ids=seen_ids, expected=expected_modules)
        issues.extend(artifact_quality["issues"])
    complete_modules = [module for module in modules if module["complete"]]
    result = {
        "schema_version": 1,
        "run": {"id": run_id, "attempt": attempt, "conclusion": run.get("conclusion"),
                "html_url": run.get("html_url"), "head_sha": run.get("head_sha")},
        "jobs": jobs,
        "toolkit_ref": toolkit_ref,
        "modules": modules,
        "artifacts": artifacts,
        "artifact_quality": artifact_quality,
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
            "longest_module_duration_seconds": max((m["wall_clock_seconds"] for m in complete_modules), default=None),
            "longest_module_duration_quality": "available" if complete_modules and artifact_quality["status"] == "complete" else "partial" if complete_modules else "unavailable",
        },
    }
    repository = run.get("repository")
    result["identity"] = {"repository": repository.get("full_name") if isinstance(repository, dict) else None,
                          "head_sha": run.get("head_sha"), "run_id": run_id, "run_attempt": attempt,
                          "toolkit_ref": toolkit_ref}
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    result["evidence_digest"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return result
