"""Render a deterministic consumer-local diagnostic artifact without executing input."""

from __future__ import annotations

import html
from urllib.parse import urlsplit

from pipeline_toolkit.security import redact


def _text(value):
    value = redact(str(value if value is not None else "unavailable"))
    value = " ".join(value.split())
    for char in "\\`[]|":
        value = value.replace(char, "\\" + char)
    return html.escape(value, quote=True)


def render_actions_diagnostics(evidence):
    """Return Markdown suitable for a local artifact or GitHub job summary.

    Callers own writing/uploading it. Failure and cancellation are independent of
    evidence quality: a failed job can have complete, valid evidence.
    """
    run, quality = evidence["run"], evidence["quality"]
    url = run.get("html_url")
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        safe = parsed is not None and parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not any(c.isspace() or c in "<>\\[]()" for c in url)
    except ValueError:
        safe = False
    lines = ["# Actions run diagnostics", "",
             f"Run: {_text(run['id'])}; attempt: {_text(run['attempt'])}; conclusion: {_text(run.get('conclusion'))}",
             f"Source run: {url if safe else 'unavailable'}",
             f"Toolkit ref: {_text(evidence.get('toolkit_ref'))}",
             f"Evidence digest: {_text(evidence.get('evidence_digest'))}",
             f"Evidence quality: {_text(quality['status'])}",
             f"Artifact quality: {_text(evidence.get('artifact_quality', {}).get('status'))}", "",
             "## Failed or cancelled jobs and steps", ""]
    found = False
    for job in evidence["jobs"]:
        failed_steps = [step for step in job["steps"] if step.get("conclusion") in {"failure", "cancelled", "timed_out", "action_required"}]
        if job.get("conclusion") in {"failure", "cancelled", "timed_out", "action_required"} or failed_steps:
            found = True
            lines.append(f"- Job {_text(job['id'])}: {_text(job.get('name'))} ({_text(job.get('conclusion'))}); duration quality: {_text(job['duration_quality'])}")
            for step in failed_steps:
                lines.append(f"  - Step {_text(step['number'])}: {_text(step.get('name'))} ({_text(step.get('conclusion'))}); duration quality: {_text(step['duration_quality'])}")
    if not found:
        lines.append("No observed failed or cancelled jobs or steps.")
    lines.extend(["", "## Quality issues", ""])
    lines.extend("- " + _text(issue) for issue in quality["issues"])
    if not quality["issues"]:
        lines.append("None.")
    metrics = evidence["metrics"]
    lines.extend(["", "## Timing", "",
                  f"Longest module duration: {_text(metrics.get('longest_module_duration_seconds'))} seconds ({_text(metrics.get('longest_module_duration_quality'))})",
                  "DAG critical path: unavailable (verified dependency graph is unavailable)",
                  "Workflow wall-clock: unavailable", "Runner queue: unavailable"])
    return "\n".join(lines) + "\n"
