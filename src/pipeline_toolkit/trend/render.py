from __future__ import annotations

import html
import json


def render_json(result: dict) -> str:
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def render_markdown(result: dict) -> str:
    lines = ["# Release trend comparison", "", f"Status: `{result['status']}`", f"Baseline strategy: `{result['baseline_strategy']}`"]
    if result["status"] == "inconclusive":
        return "\n".join([*lines, f"Reason: `{result['reason']}`", ""])
    lines += ["", "| Side | Tag | Commit SHA | Image digest |", "| --- | --- | --- | --- |"]
    for side in ("baseline", "candidate"):
        release = result[f"{side}_release"]
        lines.append(f"| {side} | {release['tag']} | `{release['commit_sha']}` | `{release['image_digest']}` |")
    lines += ["", f"Metric: `{result['metric']}` ({result['unit']})", f"Samples: baseline {result['baseline_samples']}, candidate {result['candidate_samples']}", f"Delta: {result['absolute_delta']}; relative {result['relative_delta']}", ""]
    return "\n".join(lines)


def render_html(result: dict) -> str:
    return f"<html><body><pre>{html.escape(render_markdown(result))}</pre></body></html>\n"


def render_job_summary(result: dict) -> str:
    return render_markdown(result)
