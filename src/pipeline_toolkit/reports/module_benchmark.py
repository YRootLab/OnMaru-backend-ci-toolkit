from __future__ import annotations

import json

from pipeline_toolkit.compare.module_benchmark import ModuleBenchmarkComparison


def render_module_benchmark_json(result: ModuleBenchmarkComparison) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_module_benchmark_markdown(result: ModuleBenchmarkComparison) -> str:
    data = result.to_dict()
    samples = data["valid_sample_count"]
    values = data["sample_values"]
    sample_range = data["sample_range"]
    threshold = f"{data['policy_threshold']:.0%}"
    return "\n".join(
        [
            "# Module benchmark comparison",
            "",
            f"- Classification: `{data['classification']}`",
            f"- Policy outcome: `{data['policy_outcome']}`",
            f"- Policy threshold: `{threshold}`",
            f"- Required samples: `{data['required_samples']}`",
            f"- Valid samples: baseline `{samples['baseline']}`, candidate `{samples['candidate']}`",
            f"- Baseline samples: {_format_values(values['baseline'])}",
            f"- Candidate samples: {_format_values(values['candidate'])}",
            f"- Sample range: baseline {_format_range(sample_range['baseline'])}, candidate {_format_range(sample_range['candidate'])}",
            f"- Baseline identity: `{data['baseline_identity']}`",
            f"- Comparability reason: `{data['comparability_reason']}`",
            f"- Reason: `{data['reason']}`",
        ]
    ) + "\n"


def _format_values(values: list[float]) -> str:
    return ", ".join(f"`{value:g}`" for value in values) or "none"


def _format_range(value: float | None) -> str:
    return f"`{value:g}`" if value is not None else "none"
