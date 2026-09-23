from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional, Tuple
from urllib.parse import urlparse


class RecommendationType(str, Enum):
    CATALOG = "catalog"
    CACHE = "cache"
    MATRIX = "matrix"
    CONCURRENCY = "concurrency"
    PATH_FILTER = "path_filter"
    APPLICATION = "application"
    DEPLOYMENT = "deployment"
    SECRET = "secret"
    PRODUCTION = "production"


class MutationTarget(str, Enum):
    CATALOG = "catalog"
    CACHE = "cache"
    MATRIX = "matrix"
    CONCURRENCY = "concurrency"
    PATH_FILTER = "path_filter"
    APPLICATION = "application"
    DEPLOYMENT = "deployment"
    SECRET = "secret"
    PRODUCTION = "production"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RemediationDisposition(str, Enum):
    ISSUE_ONLY = "issue_only"
    DRAFT_PULL_REQUEST = "draft_pull_request"


@dataclass(frozen=True)
class Recommendation:
    recommendation_id: str
    recommendation_type: RecommendationType
    confidence: Confidence
    stable_reason: str
    evidence_uri: str
    summary: str
    mutation_targets: Tuple[MutationTarget, ...]

    def __post_init__(self) -> None:
        _require_text(self.recommendation_id, "recommendation_id")
        _require_text(self.summary, "summary")
        if not isinstance(self.recommendation_type, RecommendationType):
            raise ValueError("recommendation_type must be a RecommendationType")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("confidence must be a Confidence")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.stable_reason):
            raise ValueError("stable_reason must be lowercase snake_case")
        _validate_evidence_uri(self.evidence_uri)
        if not self.mutation_targets or any(not isinstance(target, MutationTarget) for target in self.mutation_targets):
            raise ValueError("mutation_targets must contain MutationTarget values")


@dataclass(frozen=True)
class IssuePayload:
    title: str
    body: str
    labels: Tuple[str, ...]
    audit: dict[str, object]


@dataclass(frozen=True)
class DraftPullRequestPayload:
    title: str
    body: str
    draft: bool
    allowed_mutation_targets: Tuple[MutationTarget, ...]
    audit: dict[str, object]


@dataclass(frozen=True)
class RemediationPayload:
    disposition: RemediationDisposition
    issue: IssuePayload
    draft_pull_request: Optional[DraftPullRequestPayload]


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")


def _validate_evidence_uri(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme not in {"https", "artifact", "s3", "gs"} or not parsed.netloc:
        raise ValueError("evidence_uri must use an authoritative artifact URI")
