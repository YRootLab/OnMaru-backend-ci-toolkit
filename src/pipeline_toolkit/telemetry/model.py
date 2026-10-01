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
CI_LABELS = frozenset({"workflow", "environment", "job", "module", "scope", "outcome", "quality"})
OUTCOMES = frozenset({"success", "failure", "cancellation", "timeout", "skip", "error", "unknown", "incomplete"})
QUALITIES = frozenset({"available", "unavailable", "complete", "partial", "invalid", "missing"})


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

    def __post_init__(self) -> None:
        if not re.fullmatch(r"toolkit_ci_[a-z_]+", self.name) or self.kind not in {"gauge", "histogram"}:
            raise ValueError("invalid CI metric")
        if set(self.labels) - CI_LABELS or any(not _label(value) for value in self.labels.values()):
            raise ValueError("metric label is not allowed")
        if self.labels.get("quality", "complete") not in QUALITIES or self.labels.get("outcome", "unknown") not in OUTCOMES:
            raise ValueError("metric label value is not allowed")
        if self.unit not in {"s", "1"} or type(self.time_ns) is not int or not 0 < self.time_ns < 2 ** 64:
            raise ValueError("invalid metric unit or timestamp")
        if self.start_ns is not None and (type(self.start_ns) is not int or not 0 < self.start_ns <= self.time_ns):
            raise ValueError("invalid metric start timestamp")
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
