from __future__ import annotations

import json

from pipeline_toolkit.compare.module_benchmark import ModuleBenchmarkComparison


def render_module_benchmark_json(result: ModuleBenchmarkComparison) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_module_benchmark_markdown(result: ModuleBenchmarkComparison) -> str:
    data = result.to_dict()
    samples = data["valid_sample_count"]
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
            f"- Baseline identity: `{data['baseline_identity']}`",
            f"- Comparability reason: `{data['comparability_reason']}`",
            f"- Reason: `{data['reason']}`",
        ]
    ) + "\n"
