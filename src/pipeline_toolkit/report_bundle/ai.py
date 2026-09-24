"""Opt-in OpenAI report adapter with a fail-closed Markdown contract."""

import json
import re
from typing import Any, Callable
import urllib.error
import urllib.request


_HEADINGS = {
    "developer": frozenset({
        "## Summary",
        "## Evidence quality",
        "## Eligible evidence",
        "## Limitations",
        "## Next steps",
    }),
    "easy": frozenset({
        "## 어떤 일이 있었나",
        "## 확인된 수치",
        "## 아직 성과로 말할 수 없는 부분",
        "## 다음에 확인할 일",
    }),
}
_UNSUPPORTED_PERFORMANCE_CLAIM = re.compile(
    r"""
    (?:
        \b\d+(?:\.\d+)?\s*%\s*(?:faster|improved|reduced|shorter)\b
      | \b(?:improved|improvement|reduced|reduction|shortened)\s+(?:by\s+)?\d+(?:\.\d+)?\s*%
      | \b(?:ci\s+)?performance\s+(?:has\s+)?(?:improved|increased|reduced)\s+(?:by\s+)?\d+(?:\.\d+)?\s*%
      | \b(?:the\s+)?(?:ci|pipeline|build|test(?:\s+suite)?)\s+(?:is|was|has\s+become)\s+(?:twice|three\s+times|\d+(?:\.\d+)?\s+times)\s+as\s+(?:fast|quick|efficient)\b
      | \b(?:ci|pipeline|build|test(?:\s+suite)?|performance)\s+(?:is|was|has\s+become)\s+(?:more\s+|much\s+|significantly\s+)?(?:faster|quicker|better|more\s+efficient)\b
      | \d+(?:\.\d+)?\s*%\s*(?:더\s*)?(?:빨라졌|개선(?:됐|되었|됨)?|향상(?:됐|되었|됨)?|단축(?:됐|되었|됨)?|감소(?:했|됐|되었|됨)?)
      | (?:성능|속도|CI|파이프라인)\s*(?:개선|향상)\s*폭?\s*(?:은|는|이|가)?\s*\d+(?:\.\d+)?\s*%
      | (?:CI|파이프라인|성능|속도).{0,40}(?:이전보다|더)\s*(?:\d+(?:\.\d+)?\s*%\s*)?(?:더\s*)?(?:빨라졌|개선(?:됐|되었|됨)?|향상(?:됐|되었|됨)?|단축(?:됐|되었|됨)?)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


class _RejectAllRedirects(urllib.request.HTTPRedirectHandler):
    """Stop redirects before urllib can create a second authenticated request."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "redirect rejected for authenticated OpenAI request",
            headers,
            fp,
        )


def _open_without_redirects(request: urllib.request.Request, timeout: int) -> Any:
    return urllib.request.build_opener(_RejectAllRedirects()).open(request, timeout=timeout)


def generate_openai_markdown(
    prompt: str,
    model: str,
    api_key: str,
    opener: Callable[..., Any] = _open_without_redirects,
) -> str:
    """Return OpenAI Markdown content without placing the API key in the body."""
    _require_non_empty(prompt, "prompt")
    _require_non_empty(model, "model")
    _require_non_empty(api_key, "api key")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with opener(request, timeout=30) as response:
        try:
            markdown = json.loads(response.read())["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("OpenAI response did not contain Markdown content") from error
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("OpenAI response did not contain Markdown content")
    if api_key in markdown:
        raise ValueError("OpenAI response contains a credential")
    return markdown


def validate_ai_markdown(markdown: str, audience: str) -> str:
    """Accept only audience-shaped Markdown without unsupported performance claims."""
    if audience not in _HEADINGS:
        raise ValueError("audience must be developer or easy")
    _require_non_empty(markdown, "markdown")
    if _UNSUPPORTED_PERFORMANCE_CLAIM.search(markdown):
        raise ValueError("AI Markdown contains an unsupported performance claim")
    headings = frozenset(line.strip() for line in markdown.splitlines() if line.lstrip().startswith("#"))
    if not any(heading.startswith("# ") for heading in headings):
        raise ValueError("AI Markdown is missing a required heading")
    missing = _HEADINGS[audience] - headings
    if missing:
        raise ValueError("AI Markdown is missing a required heading")
    return markdown


def _require_non_empty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
