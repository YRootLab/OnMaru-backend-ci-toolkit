from __future__ import annotations

import argparse
import json
from pathlib import Path

from .collect import wait_and_collect
from .compare import compare_collection
from .contract import ExperimentError, load_document, safe_link
from .github import GitHub
from .plan import create_plan, dispatch


def add_parser(subparsers):
    parser = subparsers.add_parser("experiment", help="Explicit pipeline experiment; defaults to dry-run")
    actions = parser.add_subparsers(dest="experiment_action")
    parser.set_defaults(experiment_action="dry-run", repo_root=".", scope="ci", reason="pipeline experiment")
    for name in ("dry-run", "dispatch"):
        action = actions.add_parser(name)
        action.add_argument("--repo-root", default=".")
        action.add_argument("--scope", default="ci")
        action.add_argument("--reason", default="pipeline experiment")
    wait = actions.add_parser("wait")
    wait.add_argument("--receipt", required=True)
    wait.add_argument("--timeout", type=float, default=1800)
    wait.add_argument("--poll-interval", type=float, default=5)
    compare = actions.add_parser("compare")
    compare.add_argument("--input", required=True)
    compare.add_argument("--format", choices=("json", "markdown"), default="json")


def execute(args, github=None):
    github = github or GitHub()
    try:
        if args.experiment_action in ("dry-run", "dispatch"):
            operation = create_plan if args.experiment_action == "dry-run" else dispatch
            result = operation(github, Path(args.repo_root).resolve(), args.scope, args.reason)
        elif args.experiment_action == "wait":
            result = wait_and_collect(github, load_document(Path(args.receipt)), timeout=args.timeout, poll_interval=args.poll_interval)
        else:
            result = compare_collection(load_document(Path(args.input)))
        if getattr(args, "format", "json") == "markdown":
            print(render_summary(result), end="")
        else:
            print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ExperimentError, ValueError, TypeError, OverflowError) as error:
        code = error.code if isinstance(error, ExperimentError) else "invalid_input"
        print(json.dumps({"error": {"code": code, "recovery": "Inspect consumer-local evidence and docs/benchmark-experiment.md; do not automatically dispatch again."}}, sort_keys=True))
        return 2


def render_summary(result):
    comparison = result["comparison"]
    lines = ["# Pipeline benchmark experiment", "", f"Policy: `{result['policy_version']}`", f"Baseline: `{result['baseline_ref']}`", f"Candidate: `{result['candidate_ref']}`", f"Verdict: `{result['verdict']}`", ""]
    for side in ("baseline", "candidate"):
        lines.append(f"{side}: observations {comparison['sample_values'][side]}; median {comparison[side + '_median']}; range {comparison['sample_range'][side]}")
    lines.extend([f"Absolute delta: {comparison['absolute_delta']}", f"Relative delta: {comparison['relative_delta']}", "", "Exclusions:", "", "```json", json.dumps(result["exclusions"], sort_keys=True), "```", ""])
    for kind in ("actions", "manifests", "grafana"):
        for link in result["links"].get(kind, []):
            try:
                safe_link(link, grafana=kind == "grafana")
            except ExperimentError:
                continue
            lines.append(f"- {kind}: <{link}>")
    return "\n".join(lines) + "\n"
