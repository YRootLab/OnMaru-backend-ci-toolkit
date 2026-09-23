from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union
from urllib.parse import urlparse


class EvidenceStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ResourceUsage:
    cpu_seconds: Optional[float] = None
    max_rss_bytes: Optional[int] = None


@dataclass(frozen=True)
class RunProvenance:
    repository: str
    commit_sha: str
    workflow: str
    job: str


@dataclass(frozen=True)
class ModuleBenchmarkEvidence:
    module_id: str
    run_id: str
    metric_name: str
    metric_value: Optional[float]
    unit: str
    resource: ResourceUsage
    provenance: RunProvenance
    artifact_uri: Optional[str]
    status: Union[EvidenceStatus, str] = EvidenceStatus.SUCCESS
    complete: bool = True

    @property
    def eligible_for_performance_sample(self) -> bool:
        return (
            self.status == EvidenceStatus.SUCCESS
            or self.status == EvidenceStatus.SUCCESS.value
        ) and self.complete and self.metric_value is not None and bool(self.artifact_uri)


def validate_module_evidence(evidence: ModuleBenchmarkEvidence) -> None:
    _require_text(evidence.module_id, "module_id")
    _require_text(evidence.run_id, "run_id")
    _require_text(evidence.metric_name, "metric_name")
    _require_text(evidence.unit, "unit")
    _validate_status(evidence.status)
    _validate_resource(evidence.resource)
    _validate_provenance(evidence.provenance)

    if evidence.metric_value is not None and not isinstance(evidence.metric_value, (int, float)):
        raise ValueError("metric_value must be numeric")
    if evidence.complete and evidence.status in (EvidenceStatus.SUCCESS, EvidenceStatus.SUCCESS.value) and evidence.metric_value is None:
        raise ValueError("complete successful evidence requires metric_value")
    if evidence.artifact_uri:
        _validate_artifact_uri(evidence.artifact_uri)
    elif evidence.complete and evidence.status in (EvidenceStatus.SUCCESS, EvidenceStatus.SUCCESS.value):
        raise ValueError("complete successful evidence requires artifact_uri")


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")


def _validate_status(status: Union[EvidenceStatus, str]) -> None:
    try:
        EvidenceStatus(status)
    except ValueError as exc:
        raise ValueError(f"unsupported evidence status: {status}") from exc


def _validate_resource(resource: ResourceUsage) -> None:
    for field in ("cpu_seconds", "max_rss_bytes"):
        value = getattr(resource, field)
        if value is not None and (not isinstance(value, (int, float)) or value < 0):
            raise ValueError(f"resource.{field} must be a non-negative number")


def _validate_provenance(provenance: RunProvenance) -> None:
    for field in ("repository", "commit_sha", "workflow", "job"):
        _require_text(getattr(provenance, field), f"provenance.{field}")


def _validate_artifact_uri(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme not in {"artifact", "file", "gs", "https", "s3"}:
        raise ValueError("artifact_uri must use artifact, file, gs, https, or s3 URI scheme")
    if parsed.scheme == "file":
        if not parsed.path:
            raise ValueError("artifact_uri file URI requires a path")
    elif not parsed.netloc:
        raise ValueError("artifact_uri requires an authority")
