#!/usr/bin/env python3
"""Export synthetic success/failure evidence and verify provisioned Grafana queries.

Localhost only. Creates no GitHub runs, credentials or consumer source files.
Run with PYTHONPATH=src against the disposable #119 stack.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time
from urllib.parse import urlencode

from local_observability_smoke import local_url, positive_timeout, request, retry
from pipeline_toolkit.normalize.performance import normalize_execution
from pipeline_toolkit.telemetry import ExportConfig, MetricPolicy, SQLiteReplayStore, export_otlp, transform_actions_evidence, transform_layer_evidence
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


def validate_outcomes(response):
    """A numeric 1 under unknown must not masquerade as a module failure."""
    validate_values(response, [1])
    values = {(item.get("metric", {}).get("scope"), item.get("metric", {}).get("outcome")): float(item["value"][1])
              for item in response["data"]["result"]}
    for scope in ("workflow", "module"):
        for outcome in ("success", "failure"):
            if values.get((scope, outcome), 0) < 1:
                raise ValueError("PromQL source outcome labels do not match the fixture")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=positive_timeout, default=45)
    parser.add_argument("--offline", action="store_true", help="run the in-process success/failure/outage/replay layer smoke; no Docker")
    for name, port in (("grafana", 3000), ("prometheus", 9090), ("tempo", 3200), ("otlp", 4318)):
        parser.add_argument("--" + name, type=local_url, default=f"http://127.0.0.1:{port}")
    args = parser.parse_args(argv)
    if args.offline:
        print(json.dumps(offline_smoke(), sort_keys=True))
        return 0
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
                if item["key"] == "outcome":
                    validate_outcomes(response)
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
    layer = live_layer_check(args, now, args.timeout)
    print(json.dumps({"status": "passed", "layer": layer, "dashboard_uid": "toolkit-ci-benchmark", "provisioned": True, "queries": checked, "traces": traces, "replay": "duplicate_without_requests", "fixture": "synthetic; Actions/artifact links are destinations only"}, sort_keys=True))
    return 0

# ---------------------------------------------------------------------------
# Offline layer smoke: success, failure, outage and replay without Docker.
# ---------------------------------------------------------------------------

LAYER_SHA = "a" * 40


def layer_envelope(run_id, anchor):
    return {
        "schema": "ci-performance-evidence/1.0",
        "source": {"repository": REPOSITORY, "commit_sha": LAYER_SHA, "workflow": "verify",
                   "workflow_run_id": str(run_id), "run_attempt": 1},
        "producer": {"name": "smoke-fixture", "version": "1"},
        "toolchain": {"runner_image": "ubuntu-24.04", "java_version": "21.0.8", "python_version": "3.12.11"},
        "clock": {"utc_anchor": anchor, "uncertainty_ms": 50},
        "quality": "complete",
        "test_universe": {"digest": "sha256:" + "1" * 64, "size": 1200},
        "selected": {"digest": "sha256:" + "2" * 64, "count": 500},
        "execution": {"executed_now": 120, "verified_from_cache": 380},
        "cache": {"experiment_class": "realistic-pr", "policy_digest": "sha256:" + "3" * 64,
                  "cacheIdentity": {"layers": {"dependency": {"state": "warm"}, "build": {"state": "cold"},
                                               "configuration": {"state": "disabled"}},
                                    "seedProvenance": {"seeded": False, "seed_input_digest": None}}},
        "timings_ms": {"gradle_task": 65000.25, "context_init": 8200.5, "container_prepare": 4100.0,
                       "flyway": 1900.0, "tests": 91000.0},
    }


def layer_bundle(outcome, run_id, now_ns):
    """Actions attempt plus performance artifact, normalized and transformed to onmaru_ci telemetry."""
    if outcome not in ("success", "failure"):
        raise ValueError("fixture outcome must be success or failure")
    end = now_ns // 1_000_000_000 - 10

    def stamp(seconds):
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")

    run = {"id": run_id, "run_attempt": 1, "status": "completed", "conclusion": outcome, "head_sha": LAYER_SHA,
           "html_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}", "repository": {"full_name": REPOSITORY}}
    jobs = [{"id": 901, "run_id": run_id, "run_attempt": 1, "name": "[spring-full] Synthetic full tests",
             "status": "completed", "conclusion": outcome, "started_at": stamp(end - 360), "completed_at": stamp(end), "steps": []}]
    timeline = normalize_actions_timeline(run, {"total_count": len(jobs), "jobs": jobs}, toolkit_ref="b" * 40,
                                          expected_modules={}, module_artifacts=[])
    anchor = datetime.fromtimestamp(end - 300, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    raw = json.dumps(layer_envelope(run_id, anchor), sort_keys=True).encode("utf-8")
    manifest = normalize_execution(timeline, [{"id": 77, "name": "ci-performance-evidence", "size_in_bytes": len(raw), "data": raw}])
    bundle = transform_layer_evidence(manifest, MetricPolicy("ci", "test"), event="pull_request", lane="spring-full",
                                      test_type="affected", performance_bytes=raw, observed_at_ns=now_ns)
    return bundle, manifest


class OfflineReceiver(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.received.append((self.path, body))
        reply = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


def closed_endpoint():
    """A loopback port with nothing listening: a real connection refusal, not a mock."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{probe.getsockname()[1]}"


def offline_smoke():
    now = time.time_ns()
    server = ThreadingHTTPServer(("127.0.0.1", 0), OfflineReceiver)
    server.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    live = f"http://127.0.0.1:{server.server_address[1]}"
    scenarios = {}
    try:
        with tempfile.TemporaryDirectory(prefix="toolkit-layer-smoke-") as temporary:
            store_path = Path(temporary) / "replay.sqlite"

            success, success_manifest = layer_bundle("success", 8100000001, now)
            result = export_otlp(success, ExportConfig(live, backoff_seconds=0), SQLiteReplayStore(store_path), sleep=lambda _: None)
            if result.status != "exported" or result.ci_conclusion != "success" or success_manifest["source"]["verdict"] != "success":
                raise ValueError("success scenario did not export with a success verdict")
            scenarios["success"] = {"export": result.status, "verdict": success_manifest["source"]["verdict"]}

            failure, failure_manifest = layer_bundle("failure", 8100000002, now)
            result = export_otlp(failure, ExportConfig(live, backoff_seconds=0), SQLiteReplayStore(store_path), sleep=lambda _: None)
            if result.status != "exported" or result.ci_conclusion != "failure" or failure_manifest["source"]["verdict"] != "failure":
                raise ValueError("failure scenario did not preserve the failure verdict")
            scenarios["failure"] = {"export": result.status, "verdict": failure_manifest["source"]["verdict"]}

            requests_before_replay = len(server.received)
            replay = export_otlp(success, ExportConfig(live, backoff_seconds=0), SQLiteReplayStore(store_path), sleep=lambda _: None)
            if replay.status != "duplicate" or replay.request_attempts != 0 or len(server.received) != requests_before_replay:
                raise ValueError("replay after restart was not suppressed")
            scenarios["replay"] = {"export": replay.status, "request_attempts": replay.request_attempts}

            outage_bundle, outage_manifest = layer_bundle("success", 8100000003, now)
            outage = export_otlp(outage_bundle, ExportConfig(closed_endpoint(), max_attempts=1, backoff_seconds=0),
                                 SQLiteReplayStore(store_path), sleep=lambda _: None)
            if outage.status != "failed" or outage.ci_conclusion != "success" or outage_manifest["source"]["verdict"] != "success":
                raise ValueError("outage scenario changed the source verdict or reported success")
            scenarios["outage"] = {"export": outage.status, "reason": outage.reason, "verdict": outage_manifest["source"]["verdict"]}

            recovered = export_otlp(outage_bundle, ExportConfig(live, backoff_seconds=0), SQLiteReplayStore(store_path), sleep=lambda _: None)
            if recovered.status != "exported" or recovered.ci_conclusion != "success":
                raise ValueError("outage recovery did not deliver the retained observation")
            scenarios["outage_recovery"] = {"export": recovered.status}
    finally:
        server.shutdown()
        server.server_close()
    return {"status": "passed", "mode": "offline", "scenarios": scenarios,
            "receiver": "in-process loopback fixture; no Docker, Grafana or GitHub access"}

def live_layer_check(args, now, timeout):
    """Export layer success/failure fixtures, then verify Prometheus, Tempo and the performance dashboard agree."""
    dashboard = request(args.grafana + "/api/dashboards/uid/toolkit-ci-performance")
    if not dashboard.get("meta", {}).get("provisioned"):
        raise ValueError("layer performance dashboard was not imported by provisioning")
    expected = json.loads((ROOT / "observability/dashboards/ci-performance.json").read_text())
    panels = {panel["id"]: panel for panel in dashboard["dashboard"]["panels"]}
    if panels != {panel["id"]: panel for panel in expected["panels"]}:
        raise ValueError("Grafana imported a different layer dashboard revision")
    runs, traces, manifests = {}, {}, {}
    with tempfile.TemporaryDirectory(prefix="toolkit-layer-live-") as temporary:
        store = SQLiteReplayStore(Path(temporary) / "replay.sqlite")
        for outcome, run_id in (("success", 8100000011), ("failure", 8100000012)):
            bundle, manifest = layer_bundle(outcome, run_id, now)
            result = export_otlp(bundle, ExportConfig(args.otlp, backoff_seconds=0), store, sleep=lambda _: None)
            if result.status != "exported" or result.ci_conclusion != outcome or manifest["source"]["verdict"] != outcome:
                raise ValueError("layer fixture export failed or changed its verdict: " + str(result.reason))
            runs[outcome] = str(run_id)
            traces[outcome] = next(span.trace_id for span in bundle.spans if span.attributes["toolkit.ci.scope"] == "layer-run")
            manifests[outcome] = manifest["source"]["run_url"]

    def prometheus_results(response):
        if response.get("status") != "success":
            raise ValueError("Prometheus layer query failed")
        return {item["metric"].get("result"): float(item["value"][1]) for item in response["data"]["result"]}

    def check_prometheus(timeout):
        query = 'sum by (result) (onmaru_ci_workflow_duration_seconds_count{workflow="ci"})'
        results = prometheus_results(request(args.prometheus + "/api/v1/query?" + urlencode({"query": query}), timeout=timeout))
        if results.get("success", 0) < 1 or results.get("failure", 0) < 1:
            raise ValueError("Prometheus does not show both layer outcomes")
        return results

    counts = retry(check_prometheus, timeout)
    selected = request(args.prometheus + "/api/v1/query?" + urlencode({"query": 'sum by (test_type) (onmaru_ci_tests_selected_total{workflow="ci"})'}))
    if [float(item["value"][1]) for item in selected["data"]["result"]] != [500.0]:
        raise ValueError("Prometheus selected-test snapshot does not match the fixture")

    def check_trace(timeout):
        query = '{ span.toolkit.ci.scope = "layer-run" && span.cicd.pipeline.run.id = "%s" }'
        found = {}
        for outcome, run_id in runs.items():
            response = request(args.tempo + "/api/search?" + urlencode({"q": query % run_id, "limit": 5, "spss": 1, "start": now // 1_000_000_000 - 3600, "end": now // 1_000_000_000 + 60}), timeout=timeout)
            ids = {trace["traceID"] for trace in response.get("traces", [])}
            if traces[outcome] not in ids:
                raise ValueError("Tempo did not return the layer trace for run " + run_id)
            found[outcome] = traces[outcome]
        return found

    tempo_found = retry(check_trace, timeout)

    checked = []
    for panel_id in (6, 9, 15, 16, 17):
        panel = panels[panel_id]
        target = dict(panel["targets"][0], intervalMs=2000, maxDataPoints=1000)

        def check_panel(timeout, target=target, panel=panel):
            response = request(args.grafana + "/api/ds/query", {"from": str(now // 1_000_000 - 3600000), "to": str(time.time_ns() // 1_000_000), "queries": [target]}, timeout=timeout)
            validate_frames(response, numeric=panel["targets"][0]["datasource"]["type"] == "prometheus")
            return response

        response = retry(check_panel, timeout)
        frame = response["results"]["A"]["frames"][0]
        checked.append({"panel_id": panel_id, "frames": len(response["results"]["A"]["frames"]), "title": panel["title"]})
        if panel_id == 17:
            columns = {field["name"]: values for field, values in zip(frame["schema"]["fields"], frame["data"]["values"])}
            run_ids = set(columns.get("cicd.pipeline.run.id", []))
            if not set(runs.values()) <= run_ids:
                raise ValueError("layer trace table does not show both fixture runs")
            for outcome, run_id in runs.items():
                link = "https://github.com/" + REPOSITORY + "/actions/runs/" + run_id
                if link != manifests[outcome]:
                    raise ValueError("Actions link would not open the same run as the manifest")
    return {"status": "passed", "runs": runs, "trace_ids": tempo_found, "prometheus_outcomes": counts, "panels": checked}


if __name__ == "__main__":
    sys.exit(main())
