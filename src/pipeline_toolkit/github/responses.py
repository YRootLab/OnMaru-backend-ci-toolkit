def classify_error(status: int) -> str:
    return {401: "unauthorized", 403: "forbidden_or_rate_limited", 404: "not_found", 429: "rate_limited"}.get(status, "server_error" if status >= 500 else "unexpected")

def paginate(pages: list[list[dict]]) -> list[dict]:
    return [item for page in pages for item in page]


def collect_attempt_jobs(repository, run_id, attempt, fetch_page):
    """Collect only one attempt using a consumer-owned authenticated JSON transport.

    The callback receives a relative REST path, never an untrusted pagination URL.
    Exceptions (including permission/rate limit failures) propagate to the caller.
    An empty page yields partial evidence; inconsistent pages fail closed.
    """
    import re
    from pipeline_toolkit.telemetry.timeline import MAX_JOBS

    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be owner/name")
    if any(type(value) is not int or value <= 0 for value in (run_id, attempt)):
        raise ValueError("run id and attempt must be positive integers")
    jobs, seen, total, page = [], set(), None, 1
    while True:
        path = f"/repos/{repository}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}"
        response = fetch_page(path)
        if not isinstance(response, dict):
            raise ValueError("jobs page must be an object")
        count, batch = response.get("total_count"), response.get("jobs")
        if type(count) is not int or not 0 <= count <= MAX_JOBS:
            raise ValueError("job count exceeds collection bound or is invalid")
        if not isinstance(batch, list) or len(batch) > 100 or len(jobs) + len(batch) > count:
            raise ValueError("invalid jobs pagination")
        if total is not None and total != count:
            raise ValueError("jobs total changed during pagination")
        total = count
        for job in batch:
            if not isinstance(job, dict) or type(job.get("id")) is not int or job["id"] <= 0 or job["id"] in seen:
                raise ValueError("job ids must be unique positive integers")
            if any(type(job.get(key, value)) is not int or job.get(key, value) != value for key, value in (("run_id", run_id), ("run_attempt", attempt))):
                raise ValueError("job run or attempt does not match requested attempt")
            seen.add(job["id"])
            jobs.append(job)
        if len(jobs) == total or not batch:
            return {"total_count": total, "jobs": jobs}
        page += 1
        if page > MAX_JOBS:
            raise ValueError("jobs pagination exceeds collection bound")
