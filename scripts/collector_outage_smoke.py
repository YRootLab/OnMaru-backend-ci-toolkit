#!/usr/bin/env python3
"""Opt-in, disposable-stack-only Tempo outage; always attempt service restoration.

First run ci_dashboard_smoke.py to establish successful export counters. This
stops only Tempo in toolkit-local-observability and sends at most 16 x 512
synthetic spans; no GitHub requests, Cloud credentials or consumer data.
"""
import argparse
import json
import secrets
import subprocess
import time
from urllib.parse import urlencode

from ci_dashboard_smoke import ROOT, validate_frames, validate_values
from local_observability_smoke import request, retry, validate_otlp

PROMETHEUS = "http://127.0.0.1:9090"
GRAFANA = "http://127.0.0.1:3000"
OTLP = "http://127.0.0.1:4318"
COMPOSE = ["docker", "compose", "--project-name", "toolkit-local-observability", "-f", str(ROOT / "observability/local/compose.yaml")]


def outage_payloads(now_ns):
    payloads = []
    for _ in range(16):
        trace_id = secrets.token_hex(16)
        spans = [{"traceId": trace_id, "spanId": f"{index:016x}", "name": "collector-outage-fixture", "kind": 1, "startTimeUnixNano": str(now_ns - 1_000_000), "endTimeUnixNano": str(now_ns), "status": {"code": 1}} for index in range(1, 513)]
        payloads.append({"resourceSpans": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "toolkit-outage-fixture"}}]}, "scopeSpans": [{"scope": {"name": "toolkit.collector.outage", "version": "1"}, "spans": spans}]}]})
    return payloads


def query_value(query, timeout=3):
    response = request(PROMETHEUS + "/api/v1/query?" + urlencode({"query": query}), timeout=timeout)
    validate_values(response, [])
    return sum(float(item["value"][1]) for item in response["data"]["result"])


def verify_grafana_outage(queries, before, started_ms, timeout=55):
    keys = ("export_failed_spans", "export_queue_pressure", "export_in_flight")

    def observed_outage(request_timeout):
        for key in keys:
            response = request(GRAFANA + "/api/ds/query", {"from": str(started_ms - 1000), "to": str(time.time_ns() // 1_000_000), "queries": [{"refId": "A", "datasource": {"type": "prometheus", "uid": "local-prometheus"}, "expr": queries[key]["query"], "range": True, "intervalMs": 2000, "maxDataPoints": 1000}]}, timeout=request_timeout)
            validate_frames(response, numeric=True)
            values = [value for frame in response["results"]["A"]["frames"] for column in frame["data"]["values"][1:] for value in column if value is not None]
            if max(values) <= (before if key == "export_failed_spans" else 0):
                raise ValueError(f"Grafana outage range is missing query key: {key}")

    retry(observed_outage, timeout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise-outage", action="store_true", required=True, help="explicitly stop/restart only this disposable project's Tempo service")
    parser.parse_args(argv)
    running = subprocess.run(COMPOSE + ["ps", "--status", "running", "--services"], check=True, capture_output=True, text=True, timeout=10).stdout.splitlines()
    if set(running) != {"collector", "prometheus", "tempo", "grafana"}:
        raise ValueError("All four disposable local services must already be running")
    queries = {item["key"]: item for item in json.loads((ROOT / "observability/queries/ci-benchmark.json").read_text())["queries"]}
    keys = ("export_failed_spans", "export_queue_pressure", "export_in_flight")
    before = query_value(queries["export_failed_spans"]["query"])
    peaks = {key: 0.0 for key in keys}
    started_ms = time.time_ns() // 1_000_000
    try:
        subprocess.run(COMPOSE + ["stop", "tempo"], check=True, capture_output=True, timeout=20)
        for payload in outage_payloads(time.time_ns()):
            validate_otlp(request(OTLP + "/v1/traces", payload, timeout=3))

        def observed_failure(timeout):
            for key in keys:
                peaks[key] = max(peaks[key], query_value(queries[key]["query"], timeout))
            if peaks["export_failed_spans"] <= before or peaks["export_queue_pressure"] <= 0 or peaks["export_in_flight"] <= 0:
                raise ValueError("Waiting for real failed attempts and queue/in-flight pressure")
        retry(observed_failure, 55)
        verify_grafana_outage(queries, before, started_ms)
    finally:
        # No resource deletion: restart only Tempo; tmpfs data is disposable.
        subprocess.run(COMPOSE + ["start", "tempo"], check=True, capture_output=True, timeout=20)

    def recovered(timeout):
        request("http://127.0.0.1:3200/ready", timeout=timeout, decode_json=False)
        for key in ("export_queue_pressure", "export_in_flight"):
            if query_value(queries[key]["query"], timeout) != 0:
                raise ValueError("Tempo export is still draining/retrying")
    retry(recovered, 55)
    print(json.dumps({"status": "passed", "failed_span_attempts_before": before, "observed_peaks": peaks, "tempo_restored": True, "queue_and_in_flight_after": 0, "grafana_numeric_outage_frames": True, "synthetic_spans_sent": 8192}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
