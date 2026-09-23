import re

_SECRET = re.compile(r"(?i)(token|password|secret|api[_-]?key|authorization)(\s*[:=]\s*)([^\s,;]+)")

def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    result = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    for secret in secrets:
        if secret: result = result.replace(secret, "[REDACTED]")
    return result
