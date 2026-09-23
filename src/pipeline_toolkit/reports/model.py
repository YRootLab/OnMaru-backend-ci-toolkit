from __future__ import annotations
from copy import deepcopy

def build_report(result: dict) -> dict:
    report = deepcopy(result)
    report.setdefault("status", "inconclusive")
    report.setdefault("metrics", {})
    artifacts = report.pop("artifacts", [])
    report["provenance"] = {"artifacts": sorted(artifacts, key=lambda item: (item.get("kind", ""), item.get("uri", ""), item.get("sha256", "")))}
    return report
