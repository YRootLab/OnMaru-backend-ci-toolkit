from __future__ import annotations

from pipeline_toolkit.recommendations.model import (
    DraftPullRequestPayload,
    IssuePayload,
    MutationTarget,
    Recommendation,
    RecommendationType,
    RemediationDisposition,
    RemediationPayload,
)


_ALLOWED_REMEDIATION_TYPES = {
    RecommendationType.CATALOG,
    RecommendationType.CACHE,
    RecommendationType.MATRIX,
    RecommendationType.CONCURRENCY,
    RecommendationType.PATH_FILTER,
}
_ALLOWED_MUTATION_TARGETS = {
    MutationTarget.CATALOG,
    MutationTarget.CACHE,
    MutationTarget.MATRIX,
    MutationTarget.CONCURRENCY,
    MutationTarget.PATH_FILTER,
}


def build_remediation_payload(recommendation: Recommendation) -> RemediationPayload:
    downgrade_reason = _downgrade_reason(recommendation)
    audit = {
        "recommendation_id": recommendation.recommendation_id,
        "confidence": recommendation.confidence.value,
        "stable_reason": recommendation.stable_reason,
        "evidence_uri": recommendation.evidence_uri,
        "mutation_targets": [target.value for target in recommendation.mutation_targets],
    }
    if downgrade_reason:
        audit["downgrade_reason"] = downgrade_reason
    issue = IssuePayload(
        title=f"CI benchmark recommendation: {recommendation.summary}",
        body=_issue_body(recommendation, downgrade_reason),
        labels=("ci-benchmark", "automated-recommendation"),
        audit=audit,
    )
    if downgrade_reason:
        return RemediationPayload(RemediationDisposition.ISSUE_ONLY, issue, None)

    draft_audit = {
        **audit,
        "allowed_mutation_targets": [target.value for target in recommendation.mutation_targets],
        "human_review_required": True,
    }
    draft = DraftPullRequestPayload(
        title=f"draft(ci): {recommendation.summary}",
        body=_draft_body(recommendation),
        draft=True,
        allowed_mutation_targets=recommendation.mutation_targets,
        audit=draft_audit,
    )
    return RemediationPayload(RemediationDisposition.DRAFT_PULL_REQUEST, issue, draft)


def _downgrade_reason(recommendation: Recommendation) -> str | None:
    if recommendation.recommendation_type not in _ALLOWED_REMEDIATION_TYPES:
        return f"disallowed_recommendation_type:{recommendation.recommendation_type.value}"
    for target in recommendation.mutation_targets:
        if target not in _ALLOWED_MUTATION_TARGETS:
            return f"disallowed_mutation_target:{target.value}"
    return None


def _issue_body(recommendation: Recommendation, downgrade_reason: str | None) -> str:
    lines = [
        "## Benchmark recommendation",
        "",
        recommendation.summary,
        "",
        f"- Recommendation type: `{recommendation.recommendation_type.value}`",
        f"- Confidence: `{recommendation.confidence.value}`",
        f"- Stable reason: `{recommendation.stable_reason}`",
        f"- Evidence: {recommendation.evidence_uri}",
        f"- Proposed mutation targets: `{', '.join(target.value for target in recommendation.mutation_targets)}`",
        "- Human review is required before any change.",
    ]
    if downgrade_reason:
        lines.append(f"- Draft PR suppressed: `{downgrade_reason}`")
    return "\n".join(lines) + "\n"


def _draft_body(recommendation: Recommendation) -> str:
    return "\n".join(
        [
            "## Restricted automated remediation",
            "",
            recommendation.summary,
            "",
            f"- Evidence: {recommendation.evidence_uri}",
            f"- Stable reason: `{recommendation.stable_reason}`",
            "- This is a draft PR and requires human review.",
            "- Allowed scope: catalog, cache, matrix, concurrency, or path filter only.",
        ]
    ) + "\n"
