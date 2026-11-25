"""Renderers for the performance comparison result of ``compare.performance``.

Both renderers are pure functions of the result, so identical results render identically.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def render_json(result: Dict[str, Any]) -> str:
    return json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def _fmt(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_fmt(item) for item in value) + "]"
    return str(value)


def _table(headers: List[str], rows: Iterable[List[Any]]) -> List[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows)
    return lines


def render_markdown(result: Dict[str, Any]) -> str:
    experiment = result["experiment"]
    lines = [
        f"# Performance comparison: {experiment['id']}",
        "",
        f"- Classification: `{result['classification']}`",
        f"- Profile: `{experiment['profile']}`",
        f"- Metric: `{experiment['metric']}` (milliseconds)",
        f"- Plan: `{experiment['plan_kind']}`, planned runs per side: `{experiment['planned_runs_per_side']}`",
        f"- Allowed variables (declared): `{', '.join(experiment['allowed_variables']) or 'none'}`",
        f"- As of: `{result['as_of']}`",
        f"- Policy: `{result['policy']['version']}`",
        "",
    ]
    if result["reasons"]:
        lines += ["## Incomparable reasons", ""]
        rows = []
        for reason in result["reasons"]:
            if reason["side"] is None:
                values = f"baseline={_fmt(reason.get('baseline'))}, candidate={_fmt(reason.get('candidate'))}"
            else:
                values = f"side={reason['side']}, expected={_fmt(reason.get('expected'))}, observed={_fmt(reason.get('observed'))}"
            rows.append([reason["code"], reason["field"], values])
        lines += _table(["code", "field", "values"], rows) + [""]
    if result["allowed_differences"]:
        lines += ["## Declared differences (allowed)", ""]
        rows = [
            [item["variable"], item["field"], item["baseline"], item["candidate"]]
            for item in result["allowed_differences"]
        ]
        lines += _table(["variable", "field", "baseline", "candidate"], rows) + [""]
    if result["insufficiency"]:
        lines += ["## Insufficient evidence", ""]
        lines += [
            f"- {item['side']}: {item['valid_samples']} valid samples, required {item['required']}"
            for item in result["insufficiency"]
        ] + [""]

    lines += ["## Sides", ""]
    rows = []
    for side in ("baseline", "candidate"):
        report = result["sides"][side]
        rows.append([
            side,
            report["attempts"],
            report["valid_samples"],
            f"{report['failed']} ({_fmt(report['rates']['failed'])})",
            f"{report['cancelled']} ({_fmt(report['rates']['cancelled'])})",
            f"{report['excluded']} ({_fmt(report['rates']['excluded'])})",
            report["median"],
            report["range"],
            report["p95"]["status"],
        ])
    lines += _table(
        ["side", "attempts", "valid", "failed (rate)", "cancelled (rate)", "excluded (rate)", "median", "range", "p95 status"],
        rows,
    ) + [""]
    for side in ("baseline", "candidate"):
        report = result["sides"][side]
        values = ", ".join(f"run {s['run_id']} (slot {s['slot']}): {_fmt(s['value'])}" for s in report["samples"])
        lines.append(f"- {side} individual values: {values or 'none'}")
        if report["exclusions"]:
            lines.append(f"- {side} exclusions: " + ", ".join(f"{k}={v}" for k, v in report["exclusions"].items()))
    lines += [""]

    comparison = result["comparison"]
    if comparison is not None:
        lines += ["## Comparison (descriptive, no significance claim)", ""]
        lines += [
            f"- Median delta (candidate - baseline): `{_fmt(comparison['median_delta'])}` ms",
            f"- Median delta ratio: `{_fmt(comparison['median_delta_ratio'])}`",
            f"- Paired deltas: `{comparison['paired']['pairs']}` pairs, median `{_fmt(comparison['paired']['median_delta'])}`",
            f"- Direction: `{comparison['direction']}`",
        ]
        if comparison["overhead"] is not None:
            lines.append(
                f"- Overhead budget: `{_fmt(comparison['overhead']['budget_ms'])}` ms, "
                f"observed delta `{_fmt(comparison['overhead']['delta_ms'])}` ms"
            )
        lines.append("")

    lines += ["## p95", ""]
    for side in ("baseline", "candidate"):
        p95 = result["sides"][side]["p95"]
        lines.append(
            f"- {side}: `{p95['status']}` ({p95['valid_runs_in_window']} valid runs in window, "
            f"required {p95['required_valid_runs']}, policy `{p95['policy_version']}`)"
        )
    lines += [
        "",
        "## Limitations",
        "",
        "- Three observations per side do not establish statistical significance.",
        "- p95 is a raw nearest-rank quantile and is not confirmed below the cohort run threshold.",
        "- This report does not change the release approval threshold.",
        "",
    ]
    return "\n".join(lines)
