#!/usr/bin/env python3
"""Export synthetic success/failure evidence and verify provisioned Grafana queries.

Localhost only. Creates no GitHub runs, credentials or consumer source files.
Run with PYTHONPATH=src against the disposable #119 stack.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import urlencode

from local_observability_smoke import local_url, positive_timeout, request, retry
from pipeline_toolkit.telemetry import ExportConfig, MetricPolicy, SQLiteReplayStore, export_otlp, transform_actions_evidence
from pipeline_toolkit.telemetry.timeline import normalize_actions_timeline

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "YRootLab/OnMaru-backend"


def fixture_evidence(outcome, run_id, now_ns):
    if outcome not in ("success", "failure"):
        raise ValueError("fixture outcome must be success or failure")
    end = now_ns // 1_000_000_000 - 10

    def stamp(seconds):
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")

    run = {"id": run_id, "run_attempt": 1, "status": "completed", "conclusion": outcome, "head_sha": "a" * 40, "html_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}", "repository": {"full_name": REPOSITORY}}
    jobs = [{"id": 701, "run_id": run_id, "run_attempt": 1, "name": "Synthetic API fixture", "status": "completed", "conclusion": outcome, "started_at": stamp(end - 8), "completed_at": stamp(end), "steps": [{"number": 1, "name": "Synthetic tests", "status": "completed", "conclusion": outcome, "started_at": stamp(end - 7), "completed_at": stamp(end - 1)}]}]
    expected = {"api": 701}
    if outcome == "failure":
        jobs.append({"id": 702, "run_id": run_id, "run_attempt": 1, "name": "Synthetic missing worker", "status": "completed", "conclusion": "cancelled", "started_at": None, "completed_at": None, "steps": []})
        expected["worker"] = 702
    module = {"schema_version": 1, "run_id": run_id, "run_attempt": 1, "job_id": 701, "toolkit_ref": "b" * 40, "module_id": "api", "exit_code": int(outcome == "failure"), "wall_clock_seconds": 6.0, "complete": True}
    return normalize_actions_timeline(run, {"total_count": len(jobs), "jobs": jobs}, toolkit_ref="b" * 40, expected_modules=expected, module_artifacts=[{"id": 91, "data": json.dumps(module).encode()}])


def validate_frames(response, *, numeric=False):
    result = response.get("results", {}).get("A", {})
    # A timestamp-only/all-null series is not evidence of displayed data.
    values = [value for frame in result.get("frames", []) for column in frame.get("data", {}).get("values", [])[1:] for value in column if value is not None]
    if result.get("error") or not values or (numeric and any(type(value) not in (int, float) or not math.isfinite(value) for value in values)):
        raise ValueError("Grafana query returned an error or empty frames")


def validate_values(response, expected):
    actual = [float(item.get("value", [0, "nan"])[1]) for item in response.get("data", {}).get("result", [])]
    if response.get("status") != "success" or not actual or any(not math.isfinite(value) for value in actual) or any(value not in actual for value in expected):
        raise ValueError("PromQL source values do not match the fixture")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=positive_timeout, default=45)
    for name, port in (("grafana", 3000), ("prometheus", 9090), ("tempo", 3200), ("otlp", 4318)):
        parser.add_argument("--" + name, type=local_url, default=f"http://127.0.0.1:{port}")
    args = parser.parse_args(argv)
    now = time.time_ns()
    contract = json.loads((ROOT / "observability/queries/ci-benchmark.json").read_text())
    dashboard = request(args.grafana + "/api/dashboards/uid/toolkit-ci-benchmark")
    if not dashboard.get("meta", {}).get("provisioned"):
        raise ValueError("CI dashboard was not imported by provisioning")
    panels = {panel["id"]: panel for panel in dashboard["dashboard"]["panels"]}
    expected = json.loads((ROOT / "observability/dashboards/ci-benchmark.json").read_text())
    if panels != {panel["id"]: panel for panel in expected["panels"]}:
        raise ValueError("Grafana imported a different dashboard revision")
    traces = {}
    policy = MetricPolicy("ci", "test", jobs={701: "api", 702: "worker"}, modules=("api", "worker"))
    with tempfile.TemporaryDirectory(prefix="toolkit-ci-dashboard-") as temporary:
        store = SQLiteReplayStore(Path(temporary) / "replay.sqlite")
        for index, outcome in enumerate(("success", "failure"), 1):
            evidence = fixture_evidence(outcome, 8100000000 + index, now)
            bundle = transform_actions_evidence(evidence, policy, observed_at_ns=now)
            result = export_otlp(bundle, ExportConfig(args.otlp), store)
            if result.status != "exported" or result.ci_conclusion != outcome:
                raise ValueError("Synthetic evidence export failed: " + result.reason)
            replay = export_otlp(bundle, ExportConfig(args.otlp), store)
            if replay.status != "duplicate" or replay.request_attempts != 0:
                raise ValueError("Acknowledged fixture replay was not suppressed")
            traces[outcome] = bundle.spans[0].trace_id
    checked = []
    for item in contract["queries"]:
        target = dict(panels[item["panel_id"]]["targets"][0])
        target.update(intervalMs=2000, maxDataPoints=1000)
        numeric_values = []

        def check(timeout):
            if item["language"] == "promql":
                response = request(args.prometheus + "/api/v1/query?" + urlencode({"query": item["query"]}), timeout=timeout)
                values = {"workflow_duration": [8], "job_duration": [8], "step_duration": [6], "module_duration": [6], "work": [6, 8]}.get(item["key"], [1])
                if item.get("source") == "collector-internal":
                    values = [1] if item["key"] == "collector_scrape_health" else []
                validate_values(response, values)
                numeric_values[:] = [float(record["value"][1]) for record in response["data"]["result"]]
            else:
                outcome = "success" if item["key"] == "success_traces" else "failure"
                response = request(args.tempo + "/api/search?" + urlencode({"q": item["query"], "limit": 20, "spss": 1, "start": now // 1_000_000_000 - 3600, "end": now // 1_000_000_000 + 60}), timeout=timeout)
                if traces[outcome] not in {trace["traceID"] for trace in response.get("traces", [])}:
                    raise ValueError("Expected outcome trace was not found by canonical TraceQL")
            response = request(args.grafana + "/api/ds/query", {"from": str(now // 1_000_000 - 3600000), "to": str(time.time_ns() // 1_000_000), "queries": [target]}, timeout=timeout)
            validate_frames(response, numeric=item["language"] == "promql")
            if item["language"] == "traceql":
                frame = response["results"]["A"]["frames"][0]
                columns = {field["name"]: values for field, values in zip(frame["schema"]["fields"], frame["data"]["values"])}
                for override in panels[item["panel_id"]]["fieldConfig"]["overrides"]:
                    if override["matcher"]["options"] not in columns:
                        raise ValueError("Drilldown link is attached to a missing Grafana field")
                if traces[outcome] not in columns["traceIdHidden"] or not all(re.fullmatch(r"[1-9][0-9]{0,18}", value) for value in columns["cicd.pipeline.run.id"]):
                    raise ValueError("Trace/run drilldown identity is invalid")
            return response

        response = retry(check, args.timeout)
        checked.append({"key": item["key"], "frames": len(response["results"]["A"]["frames"]), "values": numeric_values, "fields": [field["name"] for frame in response["results"]["A"]["frames"] for field in frame.get("schema", {}).get("fields", [])]})
    print(json.dumps({"status": "passed", "dashboard_uid": "toolkit-ci-benchmark", "provisioned": True, "queries": checked, "traces": traces, "replay": "duplicate_without_requests", "fixture": "synthetic; Actions/artifact links are destinations only"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
