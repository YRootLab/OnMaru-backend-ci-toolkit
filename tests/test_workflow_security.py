from pipeline_toolkit.security.workflow_policy import validate_workflow_text
from pipeline_toolkit.provenance.digest import verify_image_digest

SAFE = """name: safe
on:
  pull_request:
permissions:
  contents: read
jobs:
  verify:
    steps:
      - uses: actions/checkout@v4
      - run: python -m pytest
"""

def test_safe_pull_request_workflow_has_no_policy_violations():
    assert validate_workflow_text(SAFE) == []

def test_fork_sensitive_workflow_rejects_write_permissions_and_secrets():
    unsafe = SAFE.replace("contents: read", "contents: write\n  packages: write").replace("python -m pytest", "echo ${{ secrets.PROD_TOKEN }}")
    violations = validate_workflow_text(unsafe)
    assert "pull_request_requires_read_only_contents" in violations
    assert "fork_workflow_must_not_reference_secrets" in violations

def test_pull_request_target_is_rejected():
    assert "pull_request_target_is_not_allowed" in validate_workflow_text(SAFE.replace("pull_request:", "pull_request_target:"))

def test_staging_digest_must_match_before_comparison():
    assert verify_image_digest("sha256:abc", "sha256:abc") is True
    assert verify_image_digest("sha256:abc", "sha256:def") is False
