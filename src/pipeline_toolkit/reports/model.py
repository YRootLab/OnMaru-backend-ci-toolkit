from __future__ import annotations
from copy import deepcopy

def build_report(result: dict) -> dict:
    report = deepcopy(result)
    report.setdefault("status", "inconclusive")
    report.setdefault("metrics", {})
    artifacts = report.pop("artifacts", [])
    report["provenance"] = {"artifacts": sorted(artifacts, key=lambda item: (item.get("kind", ""), item.get("uri", ""), item.get("sha256", "")))}
    return report

def top_n(rows: list[dict], metric: str, count: int) -> list[dict]:
    return sorted(rows, key=lambda row: (-float(row.get(metric, 0)), str(row.get("name", ""))))[:max(0, count)]

def paginate(rows: list[dict], page: int = 1, page_size: int = 20) -> list[dict]:
    if page < 1 or page_size < 1: return []
    start = (page - 1) * page_size
    return rows[start:start + page_size]
