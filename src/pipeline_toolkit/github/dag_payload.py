from __future__ import annotations
from datetime import datetime
from pipeline_toolkit.pipeline import Job

def _timestamp(value: str | None) -> datetime | None:
    if not value: return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def jobs_from_payload(payload: dict) -> list[Job]:
    raw = payload.get("jobs", [])
    names = {str(item.get("name")): str(item.get("id")) for item in raw}
    result = []
    for item in raw:
        conclusion = item.get("conclusion") or item.get("status") or "unknown"
        conclusion = {"failure": "failed", "timed_out": "timeout", "cancelled": "cancelled"}.get(conclusion, conclusion)
        needs = tuple(names[name] for name in item.get("needs", ()) if name in names)
        result.append(Job(str(item.get("id")), needs, _timestamp(item.get("started_at")), _timestamp(item.get("completed_at")), conclusion))
    return result
