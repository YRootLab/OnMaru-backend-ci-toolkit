def classify_error(status: int) -> str:
    return {401: "unauthorized", 403: "forbidden_or_rate_limited", 404: "not_found", 429: "rate_limited"}.get(status, "server_error" if status >= 500 else "unexpected")

def paginate(pages: list[list[dict]]) -> list[dict]:
    return [item for page in pages for item in page]
