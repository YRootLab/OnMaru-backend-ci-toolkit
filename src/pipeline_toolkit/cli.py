from __future__ import annotations
import argparse
import base64
import json
import os
import sys
import urllib.error
from pathlib import Path
from pipeline_toolkit import __version__
from pipeline_toolkit.catalog import load_catalog, plan_affected_modules
from pipeline_toolkit.compare.statistics import compare_releases
from pipeline_toolkit.contracts import validate_document
from pipeline_toolkit.report_bundle.ai import generate_openai_markdown, validate_ai_markdown
from pipeline_toolkit.report_bundle.model import ReportBundleValidationError, load_report_bundle
from pipeline_toolkit.report_bundle.render import (
    render_developer_draft,
    render_developer_prompt,
    render_easy_draft,
    render_easy_prompt,
)
from pipeline_toolkit.report_bundle.write import plan_outputs, write_outputs
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
    bundle = sub.add_parser("report-bundle")
    bundle.add_argument("--input", required=True)
    bundle.add_argument("--slug", required=True)
    bundle.add_argument("--audience", choices=("developer", "easy", "both"), default="both")
    bundle.add_argument("--repo-root", default=".")
    bundle.add_argument("--easy-output")
    bundle.add_argument("--write", action="store_true")
    bundle.add_argument("--overwrite", action="store_true")
    bundle.add_argument("--ai-provider", choices=("openai",))
    bundle.add_argument("--model")
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
    if args.command == "report-bundle":
        return _report_bundle(args)
    report = build_report(json.loads(Path(args.input).read_text()))
    rendered = {"json": render_json, "markdown": render_markdown, "html": render_html, "job-summary": render_job_summary, "png": render_png}[args.format](report)
    if args.output:
        Path(args.output).write_bytes(base64.b64decode(rendered) if args.format == "png" else rendered.encode())
    elif args.format == "png": print(rendered)
    else: print(rendered, end="")
    return 0


def _report_bundle(args: argparse.Namespace) -> int:
    if args.overwrite and not args.write:
        return _report_bundle_error("--overwrite requires --write")
    if bool(args.ai_provider) != bool(args.model):
        return _report_bundle_error("--ai-provider and --model must be supplied together")
    if args.ai_provider and not args.write:
        return _report_bundle_error("AI generation requires --write")

    try:
        bundle = load_report_bundle(Path(args.input))
        plan = plan_outputs(
            Path(args.repo_root), bundle.observed_at, args.slug, args.audience,
            Path(args.easy_output) if args.easy_output else None,
        )
    except (ReportBundleValidationError, ValueError) as error:
        return _report_bundle_error(str(error))

    contents = _report_bundle_contents(bundle, plan)
    ai_requested = args.ai_provider is not None
    if ai_requested:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return _report_bundle_error("OPENAI_API_KEY is required for OpenAI generation")
        try:
            _replace_with_ai_outputs(contents, plan, args.model, api_key)
        except (urllib.error.URLError, ValueError):
            return _report_bundle_error("AI report generation failed")

    destinations = tuple(sorted(contents, key=lambda path: str(path)))
    if args.write:
        try:
            write_outputs(plan, contents, overwrite=args.overwrite)
        except (FileExistsError, OSError, ValueError) as error:
            return _report_bundle_error(str(error))
    print(json.dumps({
        "ai_requested": ai_requested,
        "audiences": _audiences(args.audience),
        "dry_run": not args.write,
        "planned_paths": [_relative_path(path, plan.root) for path in destinations],
    }, sort_keys=True))
    return 0


def _report_bundle_contents(bundle, plan) -> dict[Path, str]:
    contents: dict[Path, str] = {}
    if plan.developer_markdown is not None:
        contents[plan.developer_markdown] = render_developer_draft(bundle)
        contents[plan.developer_prompt] = render_developer_prompt(bundle)
    if plan.easy_markdown is not None:
        contents[plan.easy_markdown] = render_easy_draft(bundle)
        contents[plan.easy_prompt] = render_easy_prompt(bundle)
    return contents


def _replace_with_ai_outputs(contents, plan, model: str, api_key: str) -> None:
    for audience, markdown_path, prompt_path in (
        ("developer", plan.developer_markdown, plan.developer_prompt),
        ("easy", plan.easy_markdown, plan.easy_prompt),
    ):
        if markdown_path is not None and prompt_path is not None:
            markdown = generate_openai_markdown(contents[prompt_path], model, api_key)
            contents[markdown_path] = validate_ai_markdown(markdown, audience)


def _audiences(audience: str) -> list[str]:
    return ["developer", "easy"] if audience == "both" else [audience]


def _relative_path(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _report_bundle_error(message: str) -> int:
    print(f"report-bundle: {message}", file=sys.stderr)
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
