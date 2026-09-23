from __future__ import annotations
import html, json
from typing import Any

def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"

def render_markdown(report: dict[str, Any]) -> str:
    status = report.get("status", "unknown")
    lines = ["# Benchmark report", "", f"- Status: `{status}`"]
    for key in ("wall_clock_seconds", "work_seconds", "critical_path_seconds", "sample_count"):
        if key in report: lines.append(f"- {key}: `{report[key]}`")
    for key in sorted(k for k in report if k not in {"status", "wall_clock_seconds", "work_seconds", "critical_path_seconds", "sample_count"}):
        lines.append(f"- {key}: `{report[key]}`")
    return "\n".join(lines) + "\n"

def render_html(report: dict[str, Any]) -> str:
    body = html.escape(render_markdown(report)).replace("\n", "<br>\n")
    return "<!doctype html><meta charset='utf-8'><title>Benchmark report</title><main>" + body + "</main>\n"
