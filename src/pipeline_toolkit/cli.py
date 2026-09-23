from __future__ import annotations
import argparse
import base64
import json
import sys
from pathlib import Path
from pipeline_toolkit import __version__
from pipeline_toolkit.catalog import load_catalog, plan_affected_modules
from pipeline_toolkit.compare.statistics import compare_releases
from pipeline_toolkit.contracts import validate_document
from pipeline_toolkit.reports import build_report, render_html, render_job_summary, render_json, render_markdown, render_png

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline-toolkit")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version")
    validate = sub.add_parser("validate"); validate.add_argument("--document", required=True); validate.add_argument("--schema", required=True)
    compare = sub.add_parser("compare"); compare.add_argument("--baseline"); compare.add_argument("--candidate", required=True)
    report = sub.add_parser("report"); report.add_argument("--input", required=True); report.add_argument("--format", choices=("json", "markdown", "html", "job-summary", "png"), default="json"); report.add_argument("--output")
    module_plan = sub.add_parser("module-plan")
    module_plan.add_argument("--catalog", required=True)
    module_plan.add_argument("--changed-path", action="append", dest="changed_paths")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "version":
        print(json.dumps({"version": __version__}, sort_keys=True)); return 0
    if args.command == "validate":
        errors = validate_document(json.loads(Path(args.document).read_text()), args.schema)
        if errors:
            print(json.dumps({"valid": False, "errors": errors}, sort_keys=True)); return 1
        print(json.dumps({"valid": True}, sort_keys=True)); return 0
    if args.command == "compare":
        candidate = json.loads(Path(args.candidate).read_text()).get("samples", [])
        baseline = json.loads(Path(args.baseline).read_text()).get("samples", []) if args.baseline else []
        print(json.dumps(compare_releases(baseline, candidate, {}, {}), sort_keys=True)); return 0
    if args.command == "module-plan":
        try:
            plan = plan_affected_modules(load_catalog(args.catalog), tuple(args.changed_paths) if args.changed_paths else None)
        except ValueError as error:
            print(f"module-plan: invalid module catalog: {error}", file=sys.stderr)
            return 2
        print(json.dumps({
            "version": 1,
            "full_suite": plan.full_suite,
            "reason": plan.reason,
            "modules": [
                {
                    "id": module.id,
                    "paths": list(module.paths),
                    "depends_on": list(module.depends_on),
                    "test_command": module.test_command,
                    "resource_profile": module.resource_profile,
                }
                for module in plan.modules
            ],
        }, sort_keys=True))
        return 0
    report = build_report(json.loads(Path(args.input).read_text()))
    rendered = {"json": render_json, "markdown": render_markdown, "html": render_html, "job-summary": render_job_summary, "png": render_png}[args.format](report)
    if args.output:
        Path(args.output).write_bytes(base64.b64decode(rendered) if args.format == "png" else rendered.encode())
    elif args.format == "png": print(rendered)
    else: print(rendered, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
