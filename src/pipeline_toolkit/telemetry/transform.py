"""Reconstruct CI observations from evidence v1; never infer unobserved timing."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlsplit

from pipeline_toolkit.contracts.performance_evidence import LAYER_NAMES, parse_envelope_text
from pipeline_toolkit.normalize.performance import LOGICAL_JOB_IDS, MANIFEST_SCHEMA, OTHER_JOB
from pipeline_toolkit.security import redact
from .model import (CACHE_RESULTS, EMITTED_LAYER_METRICS, EVENTS, ONMARU_BOUNDS, OUTCOMES, QUALITIES, TEST_TYPES,
                    BudgetExceeded, EvidenceIdentity, MetricPoint, MetricPolicy, SpanRecord, TelemetryBudget, TelemetryBundle)

LANES = frozenset(LOGICAL_JOB_IDS | {OTHER_JOB})

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


# ---------------------------------------------------------------------------
# Layer telemetry from normalized-execution/1 manifests (onmaru_ci_* metrics).
# ---------------------------------------------------------------------------

LAYER_CACHE_RESULT = {"warm": "hit", "cold": "miss", "partial": "partial", "invalidated": "invalidated",
                      "disabled": "disabled", "unknown": "unknown"}
NESTED_TIMINGS = ("context_init", "container_prepare", "flyway")
_NS_PER_MS = 1_000_000


def _manifest_digest_ok(manifest):
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return manifest.get("manifest_digest") == "sha256:" + hashlib.sha256(canonical).hexdigest()


def _check_label(name, value, allowed):
    if value not in allowed:
        raise ValueError(f"label value outside its finite catalog: {name}")
    return value


def transform_layer_evidence(manifest: dict, policy: MetricPolicy, *, event: str, lane: str,
                             test_type: str = "unknown", performance_bytes: bytes | None = None,
                             observed_at_ns: int, budget: TelemetryBudget | None = None) -> TelemetryBundle:
    """Project one normalized execution onto bounded onmaru_ci metrics and nested spans.

    * Metric labels are finite catalogs only. SHA, PR, run URL and test names are
      trace/manifest attributes.
    * Performance numbers come only from the envelope whose digest the manifest
      records. Missing measurements are omitted, never reported as zero.
    * Context/container/Flyway spans are placed at the start of the ``tests``
      span and clipped to its duration. Their placement is marked unverified
      because the envelope has no causal graph. No sum of nested time is emitted.
    * The workflow span result is the source verdict. Export status is not part
      of this bundle and cannot change it.
    """
    budget = budget or TelemetryBudget()
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA or not _manifest_digest_ok(manifest):
        raise ValueError("normalized execution manifest is missing or was modified")
    _check_label("event", event, EVENTS)
    _check_label("lane", lane, LANES)
    _check_label("test_type", test_type, TEST_TYPES)
    if type(observed_at_ns) is not int or not 0 < observed_at_ns < 2 ** 64:
        raise ValueError("observed_at_ns must be a positive OTLP timestamp")

    identity_source = manifest["identity"]
    performance = manifest["performance"]
    envelope = None
    if performance["status"] == "joined":
        if not isinstance(performance_bytes, bytes):
            raise ValueError("joined performance evidence requires its artifact bytes")
        if "sha256:" + hashlib.sha256(performance_bytes).hexdigest() != performance["artifact"]["digest"]:
            raise ValueError("performance artifact digest does not match the manifest")
        envelope = parse_envelope_text(performance_bytes.decode("utf-8"))
        source = envelope["source"]
        if (source["repository"] != identity_source["repository"] or source["workflow_run_id"] != str(identity_source["run_id"])
                or source["run_attempt"] != identity_source["run_attempt"] or source["commit_sha"] != identity_source["commit_sha"]
                or envelope["quality"] != performance["quality"]):
            raise ValueError("performance envelope does not match the manifest identity")
    elif performance_bytes is not None:
        raise ValueError("performance bytes were supplied without a joined manifest")

    identity = EvidenceIdentity(identity_source["repository"], identity_source["run_id"],
                                identity_source["run_attempt"], manifest["manifest_digest"])
    clock = manifest["clock"]
    window_start = _ns(clock["job_window_start"]) if clock["job_window_start"] else None
    window_end = _ns(clock["job_window_end"]) if clock["job_window_end"] else None
    if (window_start is None) != (window_end is None) or (window_start is not None and window_end < window_start):
        raise ValueError("manifest job window is inconsistent")
    metric_time = window_end if window_end is not None else observed_at_ns
    metric_start = window_start
    verdict = _outcome(manifest["source"]["verdict"])
    workflow = policy.workflow

    grouped = {}

    def add(name, value, **labels):
        instrument, unit, allowed = EMITTED_LAYER_METRICS[name]
        if set(labels) != set(allowed) - {"workflow"}:
            raise ValueError("onmaru metric labels do not match its registry")
        for key, item in labels.items():
            if len(item) > budget.max_label_value_length:
                raise BudgetExceeded("label value exceeds budget")
            if key == "lane":
                _check_label(key, item, LANES)
            elif key == "event":
                _check_label(key, item, EVENTS)
            elif key == "test_type":
                _check_label(key, item, TEST_TYPES)
            elif key == "cache_result":
                _check_label(key, item, CACHE_RESULTS)
            elif key == "result":
                _check_label(key, item, OUTCOMES)
        labels = {"workflow": workflow, **labels}
        grouped.setdefault((name, tuple(sorted(labels.items()))), []).append(float(value))
        if len(grouped) > budget.max_series:
            raise BudgetExceeded("metric series budget exceeded")

    if window_start is not None:
        add("onmaru_ci_workflow_duration_seconds", manifest["metrics"]["observed_job_window_seconds"], event=event, result=verdict)
    for job in manifest["jobs"]:
        if job["duration_seconds"] is None:
            continue
        job_lane = job["logical_id"] if job["logical_id"] in LANES else OTHER_JOB
        add("onmaru_ci_job_duration_seconds", job["duration_seconds"], lane=job_lane, result=_outcome(job["conclusion"]))

    timings = {}
    if envelope is not None:
        timings = {name: value for name, value in (envelope.get("timings_ms") or {}).items() if value is not None}
        if "gradle_task" in timings:
            add("onmaru_ci_gradle_task_duration_seconds", timings["gradle_task"] / 1000, lane=lane)
        if "container_prepare" in timings:
            add("onmaru_ci_testcontainers_startup_seconds", timings["container_prepare"] / 1000, lane=lane)
        if envelope["selected"]["count"] is not None:
            add("onmaru_ci_tests_selected_total", envelope["selected"]["count"], lane=lane, test_type=test_type)
        if envelope["execution"]["executed_now"] is not None:
            add("onmaru_ci_tests_executed_total", envelope["execution"]["executed_now"], lane=lane, test_type=test_type)
        # Only complete or partial envelopes carry layer states; unavailable and legacy do not.
        if envelope["quality"] in ("complete", "partial"):
            layers = envelope["cache"]["cacheIdentity"]["layers"]
            tally = defaultdict(int)
            for name in LAYER_NAMES:
                state = layers[name]["state"] if name in layers else "unknown"
                tally[LAYER_CACHE_RESULT.get(state, "unknown")] += 1
            for cache_result in sorted(tally):
                add("onmaru_ci_build_cache_operations_total", tally[cache_result], lane=lane, cache_result=cache_result)

    points = []
    for (name, labels), values in sorted(grouped.items()):
        instrument, unit, _ = EMITTED_LAYER_METRICS[name]
        if instrument == "gauge":
            values = (sum(values),)
        points.append(MetricPoint(name, unit, tuple(values), dict(labels), metric_time,
                                  instrument, None if instrument == "gauge" else metric_start,
                                  ONMARU_BOUNDS if instrument == "histogram" else ()))

    spans = []
    if window_start is not None:
        trace_id = hashlib.sha256(("toolkit-ci-layer-v1:" + identity.key).encode()).hexdigest()[:32]
        window_len = window_end - window_start
        url = manifest["source"]["run_url"]
        common = {"toolkit.ci.reconstructed": True, "vcs.repository.name": identity.repository,
                  "vcs.ref.head.revision": identity_source["commit_sha"], "cicd.pipeline.name": workflow,
                  "cicd.pipeline.run.id": str(identity.run_id), "toolkit.ci.run.attempt": identity.attempt,
                  "toolkit.ci.manifest.digest": identity.manifest_digest, "toolkit.ci.event": event,
                  "toolkit.ci.clock_alignment": clock["alignment"]}
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            if parsed and parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment:
                common["cicd.pipeline.run.url.full"] = url
        except ValueError:
            pass

        def span_id(key):
            return hashlib.sha256((trace_id + ":" + key).encode()).hexdigest()[:16]

        def emit(name, key, parent, start, end, attributes, status):
            if len(spans) >= budget.max_spans:
                raise BudgetExceeded("span budget exceeded")
            attributes = dict(common, **attributes)
            if len(attributes) > budget.max_span_attributes:
                raise BudgetExceeded("span attribute budget exceeded")
            spans.append(SpanRecord(name, trace_id, span_id(key), parent, start, end, attributes, status, 1))
            return span_id(key)

        workflow_span = emit("RUN " + workflow, "run", None, window_start, window_end,
                             {"toolkit.ci.scope": "layer-run", "toolkit.ci.source_conclusion": manifest["source"]["conclusion"] or "unknown",
                              "toolkit.ci.source_verdict": manifest["source"]["verdict"], "cicd.pipeline.result": verdict,
                              "cicd.pipeline.action.name": "RUN", "toolkit.ci.timing": "observed_job_window"},
                             2 if verdict in {"failure", "error", "timeout"} else 1 if verdict == "success" else 0)
        if "tests" in timings:
            tests_raw = int(round(timings["tests"] * _NS_PER_MS))
            tests_len = min(tests_raw, window_len)
            tests_span = emit("tests", "tests", workflow_span, window_start, window_start + tests_len,
                              {"toolkit.ci.scope": "layer", "toolkit.ci.placement": "unverified", "toolkit.ci.clipped": tests_raw > window_len,
                               "toolkit.ci.lane": lane, "toolkit.ci.source_duration_ms": timings["tests"]}, 0)
            for name in NESTED_TIMINGS:
                if name not in timings:
                    continue
                raw = int(round(timings[name] * _NS_PER_MS))
                nested_len = min(raw, tests_len)
                emit(name, name, tests_span, window_start, window_start + nested_len,
                     {"toolkit.ci.scope": "layer", "toolkit.ci.nested_in": "tests", "toolkit.ci.placement": "unverified",
                      "toolkit.ci.clipped": raw > tests_len, "toolkit.ci.lane": lane, "toolkit.ci.source_duration_ms": timings[name]}, 0)
        if "gradle_task" in timings:
            raw = int(round(timings["gradle_task"] * _NS_PER_MS))
            emit("gradle_task", "gradle_task", workflow_span, window_start, window_start + min(raw, window_len),
                 {"toolkit.ci.scope": "layer", "toolkit.ci.placement": "unverified", "toolkit.ci.clipped": raw > window_len,
                  "toolkit.ci.lane": lane, "toolkit.ci.source_duration_ms": timings["gradle_task"]}, 0)

    return TelemetryBundle(identity, tuple(points), tuple(spans), tuple(sorted(set(manifest["quality"]["issues"]))),
                           manifest["source"]["conclusion"])
