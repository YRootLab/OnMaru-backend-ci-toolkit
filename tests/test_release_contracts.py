import pytest
from pipeline_toolkit.contracts import Deployment, Release, validate
from pipeline_toolkit.provenance.release import compare_release_identity

def release(tag="v1", sha="a", digest="sha256:abc"):
    return Release("org/repo", tag, sha * 40 if len(sha) == 1 else sha, digest)

def test_deployment_requires_environment_and_matches_release_digest():
    deployment = Deployment("staging", "v1", "sha256:abc", "2026-01-01T00:00:00Z")
    validate(deployment)
    assert compare_release_identity(release(), deployment) == {"match": True}

def test_digest_mismatch_and_tag_only_identity_are_rejected():
    with pytest.raises(ValueError): compare_release_identity(release(), Deployment("staging", "v1", "sha256:def", "2026-01-01T00:00:00Z"))
    with pytest.raises(ValueError): validate(Release("org/repo", "v1", "", ""))

def test_same_release_cannot_be_used_as_baseline_and_candidate():
    with pytest.raises(ValueError): compare_release_identity(release(), Deployment("staging", "v1", "sha256:abc", "2026-01-01T00:00:00Z"), require_distinct=True)
