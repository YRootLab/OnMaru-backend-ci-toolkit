from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
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
