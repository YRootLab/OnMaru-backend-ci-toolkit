from __future__ import annotations
import json
import hashlib
import math
import re
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Mapping
from typing import Any
from pipeline_toolkit.security import redact

ALLOWED_LABELS = frozenset({"collector", "source", "status", "reason", "environment", "format", "service"})
SENSITIVE_KEYS = frozenset({"token", "password", "secret", "api_key", "authorization"})

@dataclass(frozen=True)
class TelemetryEvent:
    name: str
    value: float
    labels: dict[str, str]
    run_id: str
    comparison_id: str | None = None
    trace_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.startswith("toolkit_"): raise ValueError("metric name must start with toolkit_")
        if not self.run_id: raise ValueError("run_id is required")
        unknown = set(self.labels) - ALLOWED_LABELS
        if unknown: raise ValueError(f"label is not allowed: {sorted(unknown)}")

def _redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower().replace("-", "_") in SENSITIVE_KEYS: return "[REDACTED]"
    if isinstance(value, str): return redact(value)
    if isinstance(value, dict): return {name: _redact(item, name) for name, item in value.items()}
    if isinstance(value, list): return [_redact(item) for item in value]
    return value

def serialize_event(event: TelemetryEvent) -> str:
    return json.dumps(_redact(asdict(event)), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


# CI metrics have their own contract; the existing structured-event API is unchanged.
# Keep data-point labels distinct from Prometheus target/resource/generated labels.
CI_LABELS = frozenset({"workflow", "environment", "ci_job", "module", "scope", "outcome", "quality"})
OUTCOMES = frozenset({"success", "failure", "cancellation", "timeout", "skip", "error", "unknown", "incomplete"})
QUALITIES = frozenset({"available", "unavailable", "complete", "partial", "invalid", "missing"})

# Layer telemetry (onmaru_ci_*) uses its own finite label set. Identity values
# (SHA, PR number, run URL, test class) are trace/manifest attributes only.
ONMARU_LABELS = frozenset({"workflow", "lane", "test_type", "cache_result", "module", "event", "result"})
TEST_TYPES = frozenset({"affected", "full", "unknown"})
CACHE_RESULTS = frozenset({"hit", "miss", "partial", "invalidated", "disabled", "unknown"})
EVENTS = frozenset({"pull_request", "push", "schedule", "workflow_dispatch", "merge_group", "other"})
# Explicit OTel bucket upper bounds (seconds) for onmaru_ci histograms.
ONMARU_BOUNDS = (1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 900.0, 1800.0, 3600.0)
# name -> (instrument, unit, allowed labels). Snapshot counts are gauges so that
# no consumer applies rate() to a per-run value.
EMITTED_LAYER_METRICS = {
    "onmaru_ci_workflow_duration_seconds": ("histogram", "s", frozenset({"workflow", "event", "result"})),
    "onmaru_ci_job_duration_seconds": ("histogram", "s", frozenset({"workflow", "lane", "result"})),
    "onmaru_ci_gradle_task_duration_seconds": ("histogram", "s", frozenset({"workflow", "lane"})),
    "onmaru_ci_testcontainers_startup_seconds": ("histogram", "s", frozenset({"workflow", "lane"})),
    "onmaru_ci_build_cache_operations_total": ("gauge", "1", frozenset({"workflow", "lane", "cache_result"})),
    "onmaru_ci_tests_selected_total": ("gauge", "1", frozenset({"workflow", "lane", "test_type"})),
    "onmaru_ci_tests_executed_total": ("gauge", "1", frozenset({"workflow", "lane", "test_type"})),
}
# Named in the issue but not derivable from ci-performance-evidence/1.0 (no count
# or byte fields). They are never emitted, so dashboards show no telemetry rather than zero.
UNAVAILABLE_LAYER_METRICS = frozenset({
    "onmaru_ci_gradle_tasks_total", "onmaru_ci_build_cache_bytes", "onmaru_ci_spring_context_loads_total",
    "onmaru_ci_affected_fallback_total", "onmaru_ci_selection_mismatch_total",
})


class BudgetExceeded(ValueError):
    """Raised instead of silently truncating a metric or trace observation."""


@dataclass(frozen=True)
class TelemetryBudget:
    max_series: int = 256
    max_spans: int = 64
    max_span_attributes: int = 48
    max_label_value_length: int = 64

    def __post_init__(self) -> None:
        for name, low, high in (("max_series", 1, 4096), ("max_spans", 1, 512),
                                ("max_span_attributes", 1, 128), ("max_label_value_length", 1, 128)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("invalid telemetry budget: " + name)


def _label(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", value) is not None and re.fullmatch(r"[0-9a-f]{40,64}", value) is None


@dataclass(frozen=True)
class MetricPolicy:
    """Consumer-owned finite catalogs; never derive these names from PR content."""

    workflow: str
    environment: str
    jobs: Mapping[int, str] = field(default_factory=dict)
    modules: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _label(self.workflow) or not _label(self.environment):
            raise ValueError("workflow/environment must be stable label identifiers")
        if len(self.jobs) > 256 or len(self.modules) > 256:
            raise ValueError("metric catalog exceeds bound")
        if any(type(key) is not int or key <= 0 or not _label(value) for key, value in self.jobs.items()) or any(not _label(value) for value in self.modules):
            raise ValueError("invalid metric label catalog")
        object.__setattr__(self, "jobs", MappingProxyType(dict(self.jobs)))
        object.__setattr__(self, "modules", tuple(sorted(set(self.modules))))


@dataclass(frozen=True)
class EvidenceIdentity:
    repository: str
    run_id: int
    attempt: int
    manifest_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise ValueError("repository identity is required")
        if any(type(value) is not int or not 0 < value < 2 ** 63 for value in (self.run_id, self.attempt)):
            raise ValueError("run and attempt identity must be positive integers")
        if not isinstance(self.manifest_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.manifest_digest):
            raise ValueError("manifest digest is required")

    @property
    def key(self) -> str:
        return hashlib.sha256(json.dumps([self.repository, self.run_id, self.attempt, self.manifest_digest], separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class MetricPoint:
    name: str
    unit: str
    values: tuple[float, ...]
    labels: Mapping[str, str]
    time_ns: int
    kind: str = "histogram"
    start_ns: int | None = None
    bounds: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"(toolkit|onmaru)_ci_[a-z_]+", self.name) or self.kind not in {"gauge", "histogram"}:
            raise ValueError("invalid CI metric")
        allowed = ONMARU_LABELS if self.name.startswith("onmaru_") else CI_LABELS
        if set(self.labels) - allowed or any(not _label(value) for value in self.labels.values()):
            raise ValueError("metric label is not allowed")
        if self.name.startswith("onmaru_"):
            instrument, unit, names = EMITTED_LAYER_METRICS.get(self.name, (None, None, None))
            if instrument is None or instrument != self.kind or unit != self.unit or set(self.labels) - names:
                raise ValueError("onmaru metric does not match its registered contract")
        if self.bounds and (self.kind != "histogram" or any(type(b) not in (int, float) or not math.isfinite(b) for b in self.bounds)
                            or any(b <= a for a, b in zip(self.bounds, self.bounds[1:])) or len(self.bounds) > 64):
            raise ValueError("invalid explicit histogram bounds")
        object.__setattr__(self, "bounds", tuple(float(b) for b in self.bounds))
        if self.labels.get("quality", "complete") not in QUALITIES or self.labels.get("outcome", "unknown") not in OUTCOMES:
            raise ValueError("metric label value is not allowed")
        if self.unit not in {"s", "1"} or type(self.time_ns) is not int or not 0 < self.time_ns < 2 ** 64:
            raise ValueError("invalid metric unit or timestamp")
        if self.start_ns is not None and (type(self.start_ns) is not int or not 0 < self.start_ns <= self.time_ns):
            raise ValueError("invalid metric start timestamp")
        if self.kind == "gauge" and len(self.values) != 1:
            raise ValueError("gauge points carry exactly one value")
        if not self.values or len(self.values) > 65536 or any(type(v) not in (int, float) or not 0 <= v <= 1e15 or not math.isfinite(v) for v in self.values):
            raise ValueError("metric values must be bounded and finite")
        object.__setattr__(self, "values", tuple(float(v) for v in self.values))
        object.__setattr__(self, "labels", MappingProxyType(dict(sorted(self.labels.items()))))


@dataclass(frozen=True)
class SpanRecord:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    start_ns: int
    end_ns: int
    attributes: Mapping[str, Any]
    status_code: int
    kind: int = 1

    def __post_init__(self) -> None:
        if any(type(value) is not int for value in (self.start_ns, self.end_ns)) or not 0 < self.start_ns <= self.end_ns < 2 ** 64:
            raise ValueError("span requires a valid observed interval")
        if not re.fullmatch(r"[0-9a-f]{32}", self.trace_id) or int(self.trace_id, 16) == 0 or not re.fullmatch(r"[0-9a-f]{16}", self.span_id) or int(self.span_id, 16) == 0:
            raise ValueError("invalid span identity")
        if self.parent_span_id is not None and (not re.fullmatch(r"[0-9a-f]{16}", self.parent_span_id) or int(self.parent_span_id, 16) == 0):
            raise ValueError("invalid parent span identity")
        if self.kind not in {1, 2} or self.status_code not in {0, 1, 2}:
            raise ValueError("invalid span kind or status")
        object.__setattr__(self, "attributes", MappingProxyType(dict(sorted(self.attributes.items()))))


@dataclass(frozen=True)
class TelemetryBundle:
    identity: EvidenceIdentity
    metrics: tuple[MetricPoint, ...]
    spans: tuple[SpanRecord, ...]
    issues: tuple[str, ...]
    ci_conclusion: str | None
