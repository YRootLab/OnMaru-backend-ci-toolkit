from pathlib import Path


PROMPT = Path("docs/to-be/onmaru-backend-parallel-ci-toolkit-rollout-prompt.md")


def test_rollout_prompt_preserves_safe_replacement_and_shadow_rollout_order():
    text = PROMPT.read_text()

    assert "PR #374를 즉시 닫지 않는다" in text
    assert "대체 PR" in text
    assert "shadow check" in text
    assert "직렬 `verify`" in text
    assert "#364" in text
    assert "#365" in text
    assert "#368" in text


def test_rollout_prompt_requires_immutable_inputs_and_comparable_evidence():
    text = PROMPT.read_text()

    assert "40자리 commit SHA" in text
    assert "toolkit_ref" in text
    assert "세 번" in text
    assert "CPU·메모리(RSS)" in text
    assert "0으로 기록하지 않는다" in text
    assert "branch protection" in text
