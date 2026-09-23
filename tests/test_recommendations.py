import pytest

from pipeline_toolkit.recommendations import (
    Confidence,
    MutationTarget,
    Recommendation,
    RecommendationType,
    RemediationDisposition,
    build_remediation_payload,
)


def recommendation(*, kind=RecommendationType.CACHE, targets=(MutationTarget.CACHE,)):
    return Recommendation(
        recommendation_id="rec-cache-001",
        recommendation_type=kind,
        confidence=Confidence.HIGH,
        stable_reason="comparable_duration_regression",
        evidence_uri="https://github.com/YRootLab/OnMaru-backend/actions/runs/123/artifacts/456",
        summary="Restore the verified Gradle cache profile.",
        mutation_targets=targets,
    )


def test_builds_evidence_linked_automatic_issue_payload_with_audit_fields():
    payload = build_remediation_payload(recommendation())

    assert payload.disposition is RemediationDisposition.DRAFT_PULL_REQUEST
    assert payload.issue.title == "CI benchmark recommendation: Restore the verified Gradle cache profile."
    assert "comparable_duration_regression" in payload.issue.body
    assert "https://github.com/YRootLab/OnMaru-backend/actions/runs/123/artifacts/456" in payload.issue.body
    assert payload.issue.audit == {
        "recommendation_id": "rec-cache-001",
        "confidence": "high",
        "stable_reason": "comparable_duration_regression",
        "evidence_uri": "https://github.com/YRootLab/OnMaru-backend/actions/runs/123/artifacts/456",
        "mutation_targets": ["cache"],
    }


@pytest.mark.parametrize(
    "kind,target",
    [
        (RecommendationType.CATALOG, MutationTarget.CATALOG),
        (RecommendationType.CACHE, MutationTarget.CACHE),
        (RecommendationType.MATRIX, MutationTarget.MATRIX),
        (RecommendationType.CONCURRENCY, MutationTarget.CONCURRENCY),
        (RecommendationType.PATH_FILTER, MutationTarget.PATH_FILTER),
    ],
)
def test_allowlisted_remediation_type_and_target_get_a_draft_pr_payload(kind, target):
    payload = build_remediation_payload(recommendation(kind=kind, targets=(target,)))

    assert payload.disposition is RemediationDisposition.DRAFT_PULL_REQUEST
    assert payload.draft_pull_request is not None
    assert payload.draft_pull_request.draft is True
    assert payload.draft_pull_request.audit["allowed_mutation_targets"] == [target.value]


@pytest.mark.parametrize(
    "target",
    [
        MutationTarget.APPLICATION,
        MutationTarget.DEPLOYMENT,
        MutationTarget.SECRET,
        MutationTarget.PRODUCTION,
    ],
)
def test_disallowed_mutation_target_is_downgraded_to_issue_only(target):
    payload = build_remediation_payload(recommendation(targets=(target,)))

    assert payload.disposition is RemediationDisposition.ISSUE_ONLY
    assert payload.draft_pull_request is None
    assert payload.issue.audit["downgrade_reason"] == f"disallowed_mutation_target:{target.value}"


def test_application_recommendation_is_downgraded_even_when_target_is_allowlisted():
    payload = build_remediation_payload(
        recommendation(kind=RecommendationType.APPLICATION, targets=(MutationTarget.CACHE,))
    )

    assert payload.disposition is RemediationDisposition.ISSUE_ONLY
    assert payload.draft_pull_request is None
    assert payload.issue.audit["downgrade_reason"] == "disallowed_recommendation_type:application"


@pytest.mark.parametrize(
    "stable_reason,evidence_uri",
    [
        ("Not stable", "https://github.com/YRootLab/OnMaru-backend/actions/runs/123"),
        ("comparable_duration_regression", "mailto:operator@example.com"),
    ],
)
def test_recommendation_requires_machine_stable_reason_and_evidence_uri(stable_reason, evidence_uri):
    with pytest.raises(ValueError):
        Recommendation(
            recommendation_id="rec-invalid-001",
            recommendation_type=RecommendationType.CACHE,
            confidence=Confidence.LOW,
            stable_reason=stable_reason,
            evidence_uri=evidence_uri,
            summary="Invalid recommendation.",
            mutation_targets=(MutationTarget.CACHE,),
        )
