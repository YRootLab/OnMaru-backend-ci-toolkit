#!/usr/bin/env python3
"""Send secret-free OTLP/HTTP JSON fixtures and query the local stack.

Uses only Python's standard library. Configuration contracts are always checked
by pytest; this optional live check requires a running local Compose stack.
"""
import argparse
import json
import math
import secrets
import sys
import time
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class RejectRedirects(HTTPRedirectHandler):
    """Fail before parsing, resolving or contacting any redirect destination."""

    def reject(self, req, response, code, message, headers):
        response.close()
        raise ValueError(f"HTTP redirect {code} is forbidden for localhost smoke requests")

    http_error_301 = http_error_302 = http_error_303 = http_error_307 = http_error_308 = reject


def local_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ValueError("URLs must be unauthenticated HTTP localhost origins")
    return value.rstrip("/")


def positive_timeout(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("timeout must be positive and finite")
    return value


def request(url, payload=None, timeout=3, decode_json=True):
    parsed = urlsplit(url)
    local_url(parsed._replace(path="", query="", fragment="").geturl())
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    # Explicit handlers also bypass urllib's global opener and OS/env proxies.
    opener = build_opener(ProxyHandler({}), RejectRedirects())
    with opener.open(Request(url, data=body, headers=headers), timeout=timeout) as response:
        content = response.read()
    return json.loads(content) if decode_json and content else {}


def fixture_payloads(trace_id, span_id, now_ns):
    resource = {"attributes": [{"key": "service.name", "value": {"stringValue": "toolkit-local-fixture"}}]}
    exemplar = {"timeUnixNano": str(now_ns), "asInt": "1", "traceId": trace_id, "spanId": span_id}
    metric = {
        "name": "toolkit_local_fixture_total",
        "description": "Disposable local stack connectivity fixture",
        "sum": {
            "aggregationTemporality": 2,
            "isMonotonic": True,
            "dataPoints": [{
                "startTimeUnixNano": str(now_ns - 1_000_000),
                "timeUnixNano": str(now_ns), "asInt": "1",
                "exemplars": [exemplar],
            }],
        },
    }
    span = {
        "traceId": trace_id, "spanId": span_id, "name": "local-stack-fixture",
        "kind": 2, "startTimeUnixNano": str(now_ns - 1_000_000),
        "endTimeUnixNano": str(now_ns), "status": {"code": 1},
    }
    scope = {"name": "toolkit.local.smoke", "version": "1"}
    metrics = {"resourceMetrics": [{"resource": resource, "scopeMetrics": [{"scope": scope, "metrics": [metric]}]}]}
    traces = {"resourceSpans": [{"resource": resource, "scopeSpans": [{"scope": scope, "spans": [span]}]}]}
    return metrics, traces


def validate_otlp(response):
    partial = response.get("partialSuccess", {})
    for key in ("rejectedSpans", "rejectedDataPoints"):
        if int(partial.get(key, 0)):
            raise ValueError(f"OTLP rejected data: {partial}")
    if partial.get("errorMessage"):
        raise ValueError(f"OTLP rejected/partial data: {partial}")


def validate_metric(response):
    results = response.get("data", {}).get("result", [])
    if response.get("status") != "success" or not any(float(item.get("value", [0, "nan"])[1]) == 1 for item in results):
        raise ValueError("fixture metric value 1 is unavailable in Prometheus")


def validate_trace(response):
    # Tempo's JSON API returns ResourceSpans as `batches` in this pinned version.
    batches = response.get("batches", response.get("resourceSpans", []))
    if not any(span.get("name") == "local-stack-fixture" for batch in batches
               for scope in batch.get("scopeSpans", []) for span in scope.get("spans", [])):
        raise ValueError("fixture trace span is unavailable in Tempo")


def validate_exemplar(response, trace_id):
    if response.get("status") != "success" or not any(
        item.get("labels", {}).get("trace_id") == trace_id
        for result in response.get("data", []) for item in result.get("exemplars", [])
    ):
        raise ValueError("fixture exemplar trace_id is unavailable in Prometheus")


def retry(check, timeout):
    deadline = time.monotonic() + positive_timeout(timeout)
    while True:
        remaining = deadline - time.monotonic()
        try:
            return check(max(0.01, min(3, remaining)))
        except (URLError, OSError, ValueError, KeyError) as error:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"local stack check timed out: {error}") from error
            time.sleep(min(0.5, remaining))


def check_health(collector, prometheus, tempo, grafana, timeout):
    def check(request_timeout):
        for url in [collector + "/", prometheus + "/-/ready", tempo + "/ready"]:
            request(url, timeout=request_timeout, decode_json=False)
        health = request(grafana + "/api/health", timeout=request_timeout)
        if health.get("database") != "ok":
            raise ValueError("Grafana database is not healthy")
        prom = request(grafana + "/api/datasources/uid/local-prometheus", timeout=request_timeout)
        traces = request(grafana + "/api/datasources/uid/local-tempo", timeout=request_timeout)
        if (prom.get("type") != "prometheus" or traces.get("type") != "tempo"
                or prom.get("jsonData", {}).get("exemplarTraceIdDestinations") != [
                    {"name": "trace_id", "datasourceUid": "local-tempo"}]
                or traces.get("jsonData", {}).get("tracesToMetrics", {}).get("datasourceUid") != "local-prometheus"):
            raise ValueError("Grafana metric/trace datasources are not linked")
    retry(check, timeout)


def query_fixture(prometheus, tempo, trace_id, timeout):
    def check(request_timeout):
        query = urlencode({"query": "toolkit_local_fixture_total"})
        validate_metric(request(prometheus + "/api/v1/query?" + query, timeout=request_timeout))
        validate_trace(request(tempo + "/api/traces/" + trace_id, timeout=request_timeout))
        exemplars = urlencode({"query": "toolkit_local_fixture_total", "start": time.time() - 300, "end": time.time()})
        validate_exemplar(request(prometheus + "/api/v1/query_exemplars?" + exemplars, timeout=request_timeout), trace_id)
    retry(check, timeout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=positive_timeout, default=60, help="retry budget per phase in seconds (default: 60)")
    parser.add_argument("--health-only", action="store_true", help="check readiness and datasource links without sending fixtures")
    for name, port in [("collector", 13133), ("otlp", 4318), ("prometheus", 9090), ("tempo", 3200), ("grafana", 3000)]:
        parser.add_argument("--" + name, type=local_url, default=f"http://127.0.0.1:{port}")
    args = parser.parse_args(argv)
    try:
        check_health(args.collector, args.prometheus, args.tempo, args.grafana, args.timeout)
        if args.health_only:
            print(json.dumps({"status": "healthy", "datasources": ["local-prometheus", "local-tempo"]}))
            return 0
        trace_id, span_id = secrets.token_hex(16), secrets.token_hex(8)
        metrics, traces = fixture_payloads(trace_id, span_id, time.time_ns())
        for signal, payload in [("traces", traces), ("metrics", metrics)]:
            validate_otlp(request(args.otlp + "/v1/" + signal, payload))
        query_fixture(args.prometheus, args.tempo, trace_id, args.timeout)
        print(json.dumps({"status": "passed", "metric": "toolkit_local_fixture_total", "trace_id": trace_id,
                          "trace_url": args.tempo + "/api/traces/" + trace_id, "exemplar": "verified"}))
        return 0
    except (RuntimeError, URLError, OSError, ValueError, KeyError) as error:
        print(f"Local observability smoke failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
