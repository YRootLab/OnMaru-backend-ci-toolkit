"""Reconstruct CI observations from evidence v1; never infer unobserved timing."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlsplit

from pipeline_toolkit.security import redact
from .model import EvidenceIdentity, MetricPoint, MetricPolicy, SpanRecord, TelemetryBundle, OUTCOMES, QUALITIES

MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
MAX_OBSERVATIONS = 8192
RESULTS = {"failed": "failure", "cancelled": "cancellation", "timed_out": "timeout", "skipped": "skip", "neutral": "skip", "action_required": "error", "stale": "error"}
TIMESTAMP = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)\Z")


def _ns(value):
    match = TIMESTAMP.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError("timestamp is not RFC3339")
    base, fraction, offset = match.groups()
    stamp = datetime.fromisoformat(base + offset.replace("Z", "+00:00"))
    delta = stamp.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    result = (delta.days * 86400 + delta.seconds) * 1_000_000_000 + int((fraction or "").ljust(9, "0"))
    if not 0 < result < 2 ** 64:
        raise ValueError("timestamp outside OTLP range")
    return result


def _interval(record):
    if record.get("duration_quality") != "available":
        return None
    try:
        start, end = _ns(record.get("started_at")), _ns(record.get("completed_at"))
        return (start, end) if start <= end else None
    except (ValueError, OverflowError):
        return None


def _outcome(value):
    mapped = RESULTS.get(value, value)
    return mapped if mapped in OUTCOMES else "unknown"


def _consistent(evidence):
    """A digest is not authenticity: cross-check the retained timing relationships."""
    def record(value):
        if not isinstance(value, dict) or value.get("duration_quality") not in {"available", "invalid", "unavailable"}:
            raise ValueError("invalid evidence timing quality")
        for name in ("name", "conclusion", "started_at", "completed_at"):
            if value.get(name) is not None and (not isinstance(value[name], str) or len(value[name]) > 4096):
                raise ValueError("invalid evidence text")
        interval = _interval(value)
        if value["duration_quality"] == "available":
            if interval is None or type(value.get("duration_seconds")) not in (int, float) or value["duration_seconds"] != round((interval[1] - interval[0]) / 1_000_000_000, 3):
                raise ValueError("inconsistent evidence duration")
        elif value.get("duration_seconds") is not None:
            raise ValueError("unavailable evidence duration has a value")
        return interval

    ids, intervals, work = set(), [], 0
    for job in evidence["jobs"]:
        if type(job.get("id")) is not int or job["id"] <= 0 or job["id"] in ids:
            raise ValueError("duplicate or invalid evidence job")
        ids.add(job["id"])
        interval = record(job)
        if interval:
            intervals.append(interval)
            work += job["duration_seconds"]
        numbers = set()
        for step in job["steps"]:
            if not isinstance(step, dict) or type(step.get("number")) is not int or step["number"] <= 0 or step["number"] in numbers:
                raise ValueError("duplicate or invalid evidence step")
            numbers.add(step["number"])
            record(step)
    window = round((max(i[1] for i in intervals) - min(i[0] for i in intervals)) / 1_000_000_000, 3) if intervals else None
    if evidence["metrics"].get("observed_job_window_seconds") != window or evidence["metrics"].get("sum_job_work_seconds") != round(work, 3):
        raise ValueError("inconsistent evidence aggregate timing")
    module_ids = set()
    for module in evidence["modules"]:
        if not isinstance(module, dict) or not isinstance(module.get("module_id"), str) or module["module_id"] in module_ids or module.get("job_id") not in ids:
            raise ValueError("invalid evidence module identity")
        module_ids.add(module["module_id"])
        duration, complete = module.get("wall_clock_seconds"), module.get("complete")
        if type(complete) is not bool or (duration is not None and (type(duration) not in (int, float) or not 0 <= duration <= 31536000)) or (complete and duration is None):
            raise ValueError("invalid evidence module duration")
        exit_code = module.get("exit_code")
        if (exit_code is not None and (type(exit_code) is not int or not 0 <= exit_code <= 255)) or (complete and exit_code is None):
            raise ValueError("invalid evidence module result")
        expected_result = "failure" if exit_code not in (None, 0) else "success" if complete else "incomplete"
        if _outcome(module.get("status")) != expected_result:
            raise ValueError("inconsistent evidence module result")
    for field in ("quality", "artifact_quality"):
        if not isinstance(evidence.get(field), dict) or evidence[field].get("status") not in QUALITIES or not isinstance(evidence[field].get("issues"), list) or any(not isinstance(issue, str) for issue in evidence[field]["issues"]):
            raise ValueError("invalid evidence collection quality")


def _source(evidence):
    if not isinstance(evidence, dict) or type(evidence.get("schema_version")) is not int or evidence["schema_version"] != 1:
        raise ValueError("unsupported Actions evidence schema")
    jobs, modules = evidence.get("jobs"), evidence.get("modules")
    if not isinstance(jobs, list) or len(jobs) > 256 or not isinstance(modules, list) or len(modules) > 256:
        raise ValueError("evidence collection bound")
    size = 1 + len(modules)
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("steps"), list) or len(job["steps"]) > 256:
            raise ValueError("invalid job/step evidence")
        size += 1 + len(job["steps"])
    if size > MAX_OBSERVATIONS:
        raise ValueError("evidence observation bound")
    unsigned = {key: value for key, value in evidence.items() if key != "evidence_digest"}
    digest, count = hashlib.sha256(), 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).iterencode(unsigned):
            chunk = chunk.encode("utf-8")
            count += len(chunk)
            if count > MAX_EVIDENCE_BYTES:
                raise ValueError("evidence byte bound")
            digest.update(chunk)
    except (TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid evidence JSON") from exc
    if evidence.get("evidence_digest") != "sha256:" + digest.hexdigest():
        raise ValueError("evidence digest mismatch")
    identity = evidence.get("identity", {})
    result = EvidenceIdentity(identity.get("repository"), identity.get("run_id"), identity.get("run_attempt"), evidence["evidence_digest"])
    if (evidence["run"].get("id"), evidence["run"].get("attempt")) != (result.run_id, result.attempt):
        raise ValueError("evidence run identity mismatch")
    _consistent(evidence)
    return result


def transform_actions_evidence(evidence: dict, policy: MetricPolicy, *, observed_at_ns: int) -> TelemetryBundle:
    """Use a stable consumer-supplied collection timestamp for untimed metric points.

    Exact raw conclusions/identity stay on spans. Metric dimensions are bounded
    catalogs or fixed enums; names of steps and tests never become metric labels.
    """
    identity = _source(evidence)
    if type(observed_at_ns) is not int or not 0 < observed_at_ns < 2 ** 64:
        raise ValueError("observed_at_ns must be a positive OTLP timestamp")
    issues = list(evidence["quality"]["issues"])
    spans, grouped = [], defaultdict(list)
    base = {"workflow": policy.workflow, "environment": policy.environment}
    intervals = {job["id"]: _interval(job) for job in evidence["jobs"]}
    complete = [interval for interval in intervals.values() if interval is not None]
    window = (min(i[0] for i in complete), max(i[1] for i in complete)) if complete else None
    metric_time = window[1] if window else observed_at_ns
    trace_id = hashlib.sha256(("toolkit-ci-v1:" + identity.key).encode()).hexdigest()[:32]

    def span_id(key):
        return hashlib.sha256((trace_id + ":" + key).encode()).hexdigest()[:16]

    def metric(name, value, scope, *, kind="histogram", quality="available", **labels):
        labels = dict(base, scope=scope, quality=quality, **labels)
        grouped[(name, kind, tuple(sorted(labels.items())))].append(value)

    def outcome(value, scope, **labels):
        metric("toolkit_ci_outcome", 1, scope, kind="gauge", outcome=_outcome(value), **labels)

    common = {"toolkit.ci.reconstructed": True, "vcs.repository.name": identity.repository,
              "cicd.pipeline.name": policy.workflow, "cicd.pipeline.run.id": str(identity.run_id),
              "toolkit.ci.run.attempt": identity.attempt, "toolkit.ci.manifest.digest": identity.manifest_digest}
    for key, value in (("vcs.ref.head.revision", evidence["identity"].get("head_sha")), ("toolkit.ref", evidence.get("toolkit_ref"))):
        if value:
            common[key] = redact(str(value))
    url = evidence["run"].get("html_url")
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        if parsed and parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment:
            common["cicd.pipeline.run.url.full"] = url
    except ValueError:
        pass

    def span(key, parent, name, interval, conclusion, scope, extra=None):
        result = _outcome(conclusion)
        attributes = dict(common, **{"toolkit.ci.scope": scope, "toolkit.ci.source_conclusion": conclusion or "unknown"})
        attributes.update(extra or {})
        if scope == "workflow":
            attributes.update({"cicd.pipeline.result": result, "cicd.pipeline.action.name": "RUN", "toolkit.ci.timing": "observed_job_window"})
        else:
            attributes.update({"cicd.pipeline.task.name": redact(name), "cicd.pipeline.task.run.id": key, "cicd.pipeline.task.run.result": result})
            if "cicd.pipeline.run.url.full" in common:
                parts = key.split(":")
                task_url = common["cicd.pipeline.run.url.full"].rstrip("/") + "/job/" + parts[1]
                if scope == "step":
                    task_url += "#step:" + parts[2] + ":1"
                attributes["cicd.pipeline.task.run.url.full"] = task_url
        error = result in {"failure", "error", "timeout"}
        if error:
            attributes["error.type"] = result
        spans.append(SpanRecord(redact(name), trace_id, span_id(key), parent, *interval, attributes, 2 if error else 1 if result == "success" else 0, 2 if scope == "workflow" else 1))

    metrics = evidence["metrics"]
    outcome(evidence["run"].get("conclusion"), "workflow")
    if window:
        span("workflow", None, "RUN " + policy.workflow, window, evidence["run"].get("conclusion"), "workflow")
        metric("toolkit_ci_workflow_observed_window_seconds", metrics["observed_job_window_seconds"], "workflow", quality=metrics["observed_job_window_quality"])
    for name, scope in (("quality", "evidence"), ("artifact_quality", "artifact")):
        metric("toolkit_ci_collection_quality", 1, scope, kind="gauge", quality=evidence[name]["status"])
    for job in sorted(evidence["jobs"], key=lambda job: job["id"]):
        key, interval = "job:" + str(job["id"]), intervals[job["id"]]
        job_label = policy.jobs.get(job["id"], "other")
        outcome(job.get("conclusion"), "job", ci_job=job_label)
        metric("toolkit_ci_collection_quality", 1, "job", kind="gauge", quality=job["duration_quality"], ci_job=job_label)
        if interval:
            span(key, span_id("workflow") if window else None, job.get("name") or "job", interval, job.get("conclusion"), "job")
            metric("toolkit_ci_job_duration_seconds", job["duration_seconds"], "job", ci_job=job_label)
        else:
            issues.append(key + ":timestamp_" + (job["duration_quality"] if job["duration_quality"] != "available" else "invalid"))
        for step in sorted(job["steps"], key=lambda step: step["number"]):
            step_key = "step:" + str(job["id"]) + ":" + str(step["number"])
            step_interval = _interval(step)
            outcome(step.get("conclusion"), "step", ci_job=job_label)
            metric("toolkit_ci_collection_quality", 1, "step", kind="gauge", quality=step["duration_quality"], ci_job=job_label)
            if step_interval:
                # Missing parents are not invented; an observed step can be a root.
                span(step_key, span_id(key) if interval else None, step.get("name") or "step", step_interval, step.get("conclusion"), "step")
                metric("toolkit_ci_step_duration_seconds", step["duration_seconds"], "step", ci_job=job_label)
            else:
                issues.append(step_key + ":timestamp_" + (step["duration_quality"] if step["duration_quality"] != "available" else "invalid"))
    if complete:
        metric("toolkit_ci_work_seconds", metrics["sum_job_work_seconds"], "job", kind="gauge", quality=metrics["sum_job_work_quality"])
    module_work = []
    for module in evidence["modules"]:
        label = module["module_id"] if module["module_id"] in policy.modules else "other"
        outcome(module["status"], "module", module=label)
        metric("toolkit_ci_collection_quality", 1, "module", kind="gauge", quality="complete" if module["complete"] else "partial", module=label)
        if module["complete"]:
            metric("toolkit_ci_module_duration_seconds", module["wall_clock_seconds"], "module", module=label)
            module_work.append(module["wall_clock_seconds"])
    if module_work:
        metric("toolkit_ci_work_seconds", sum(module_work), "module", kind="gauge", quality=evidence["artifact_quality"]["status"])
    points = tuple(MetricPoint(name, "s" if name.endswith("_seconds") else "1", tuple(values) if kind == "histogram" else (sum(values),), dict(labels), metric_time, kind, window[0] if window else None)
                   for (name, kind, labels), values in sorted(grouped.items()))
    return TelemetryBundle(identity, points, tuple(spans), tuple(sorted(set(issues))), evidence["run"].get("conclusion"))
