import json

import pytest

from pipeline_toolkit.report_bundle.ai import generate_openai_markdown, validate_ai_markdown


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def test_openai_adapter_sends_prompt_without_api_key_in_body():
    seen = {}

    def opener(request, timeout):
        seen["body"] = request.data.decode("utf-8")
        seen["authorization"] = request.get_header("Authorization")
        assert timeout == 30
        return FakeResponse(json.dumps({"choices": [{"message": {"content": "# Report\n## 한계"}}]}))

    result = generate_openai_markdown("facts", "gpt-5", "secret-key", opener)

    assert result.startswith("# Report")
    assert "secret-key" not in seen["body"]
    assert seen["authorization"] == "Bearer secret-key"


@pytest.mark.parametrize(
    "audience, markdown",
    [
        ("easy", "# CI를 쉽게 설명한 보고서\n## 어떤 일이 있었나\n## 확인된 수치\n## 아직 성과로 말할 수 없는 부분\n## 다음에 확인할 일"),
        ("developer", "# CI technical report\n## Summary\n## Evidence quality\n## Eligible evidence\n## Limitations\n## Next steps"),
    ],
)
def test_validate_ai_markdown_accepts_required_headings(audience, markdown):
    assert validate_ai_markdown(markdown, audience) == markdown


@pytest.mark.parametrize("markdown", ["# x\n21% 빨라졌다", "# x\nCI is 21% faster"])
def test_validate_ai_markdown_rejects_unsupported_performance_claims(markdown):
    with pytest.raises(ValueError, match="performance claim"):
        validate_ai_markdown(markdown, "easy")


def test_validate_ai_markdown_rejects_missing_required_heading():
    with pytest.raises(ValueError, match="required heading"):
        validate_ai_markdown("# 쉬운 보고서\n## 어떤 일이 있었나", "easy")
