"""Layer telemetry (onmaru_ci_*): buckets, replay, budgets, waterfall and dashboard links."""
import copy
import hashlib
import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from pipeline_toolkit.contracts.performance_evidence import parse_envelope_text
from pipeline_toolkit.normalize.performance import normalize_execution
from pipeline_toolkit.telemetry import (BudgetExceeded, EvidenceIdentity, MetricPoint, MetricPolicy,
                                        SQLiteReplayStore, TelemetryBudget, TelemetryBundle, export_otlp,
                                        transform_layer_evidence)
from pipeline_toolkit.telemetry.export import ExportConfig, build_batches
from pipeline_toolkit.telemetry.model import (EMITTED_LAYER_METRICS, ONMARU_BOUNDS, ONMARU_LABELS,
                                              UNAVAILABLE_LAYER_METRICS, CACHE_RESULTS, EVENTS, TEST_TYPES)
from pipeline_toolkit.telemetry.transform import LANES

from test_performance_ingest import ENVELOPE, FIXTURES, artifact, timeline

ROOT = Path(__file__).resolve().parents[1]
POLICY = MetricPolicy("ci", "test")
RUN_ID = "24712345678"
SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
RUN_URL = "https://github.com/YRootLab/OnMaru-backend/actions/runs/" + RUN_ID
OBSERVED_NS = 1790812801000000000
WINDOW_START_NS = 1795143480000000000  # 2026-11-20T02:58:00Z, from the job fixture
WINDOW_END_NS = WINDOW_START_NS + 360 * 1_000_000_000


def envelope_bytes(document=None):
    return json.dumps(document if document is not None else ENVELOPE, sort_keys=True).encode("utf-8")


def manifest(envelope=None, *, run_overrides=None):
    return normalize_execution(timeline(run_overrides), [artifact(envelope)])


def layer(manifest_value=None, *, envelope=None, budget=None, lane="spring-full", test_type="affected",
          event="pull_request", observed_at_ns=OBSERVED_NS, performance=True):
    value = manifest_value if manifest_value is not None else manifest(envelope)
    raw = envelope_bytes(envelope) if performance and value["performance"]["status"] == "joined" else None
    return transform_layer_evidence(value, POLICY, event=event, lane=lane, test_type=test_type,
                                    performance_bytes=raw, observed_at_ns=observed_at_ns, budget=budget)


def payloads(bundle, config=None):
    config = config or ExportConfig("http://127.0.0.1:4318")
    return build_batches(bundle, config)


# --------------------------------------------------------------------------
# OTLP receiver fixture: cumulative series are replaced by identity, not summed.
# --------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        receiver = self.server.receiver
        receiver.requests.append((self.path, body))
        status = receiver.script.pop(0) if receiver.script else 200
        if status == 200:
            receiver.apply(self.path, body)
        reply = b"{}"
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


class Receiver:
    def __init__(self, script=()):
        self.script = list(script)
        self.requests = []
        self.series = {}
        self.spans = {}
        self.violations = []

    def apply(self, path, body):
        document = json.loads(body)
        if path == "/v1/traces":
            for resource in document["resourceSpans"]:
                for scope in resource["scopeSpans"]:
                    for span in scope["spans"]:
                        self.spans[span["spanId"]] = span
            return
        for resource in document["resourceMetrics"]:
            for scope in resource["scopeMetrics"]:
                for metric in scope["metrics"]:
                    kind = "histogram" if "histogram" in metric else "gauge"
                    temporality = metric[kind].get("aggregationTemporality")
                    for point in metric[kind]["dataPoints"]:
                        key = (metric["name"], json.dumps(point["attributes"], sort_keys=True), point.get("startTimeUnixNano"))
                        self.series[key] = {"kind": kind, "temporality": temporality, "point": point}
                        if kind == "histogram":
                            self._check_histogram(metric["name"], point)

    def _check_histogram(self, name, point):
        bounds = point["explicitBounds"]
        counts = [int(c) for c in point["bucketCounts"]]
        if len(counts) != len(bounds) + 1 or sum(counts) != int(point["count"]) or any(b >= c for b, c in zip(bounds, bounds[1:])):
            self.violations.append(name)

    def points(self, name):
        return [entry for (metric, _, _), entry in self.series.items() if metric == name]

    def metric_bodies(self):
        return b"".join(body for path, body in self.requests if path == "/v1/metrics")


@pytest.fixture
def receiver_server():
    servers = []

    def start(script=()):
        receiver = Receiver(script)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.receiver = receiver
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        return receiver, f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def export(bundle, endpoint, store_path, *, max_attempts=3):
    config = ExportConfig(endpoint, max_attempts=max_attempts, backoff_seconds=0)
    return export_otlp(bundle, config, SQLiteReplayStore(store_path), sleep=lambda _: None)


# --------------------------------------------------------------------------
# Histogram buckets, count, sum and cumulative temporality
# --------------------------------------------------------------------------

def attributes(series_key):
    """Decode the OTLP attribute list stored in a receiver series key."""
    return {item["key"]: next(iter(item["value"].values())) for item in json.loads(series_key[1])}


def bucket_index(value):
    return next((i for i, bound in enumerate(ONMARU_BOUNDS) if value <= bound), len(ONMARU_BOUNDS))


def test_histogram_buckets_count_sum_and_cumulative_temporality_match_receiver(receiver_server, tmp_path):
    receiver, endpoint = receiver_server()
    bundle = layer()
    result = export(bundle, endpoint, tmp_path / "replay.sqlite")
    assert result.status == "exported" and result.ci_conclusion == "success"
    assert receiver.violations == []

    (workflow,) = receiver.points("onmaru_ci_workflow_duration_seconds")
    point = workflow["point"]
    assert workflow["kind"] == "histogram" and workflow["temporality"] == 2
    assert point["count"] == "1" and point["sum"] == pytest.approx(360.0)
    assert point["explicitBounds"] == list(ONMARU_BOUNDS)
    expected = [0] * (len(ONMARU_BOUNDS) + 1)
    expected[bucket_index(360.0)] = 1
    assert point["bucketCounts"] == [str(c) for c in expected]
    assert point["startTimeUnixNano"] == str(WINDOW_START_NS)
    assert point["timeUnixNano"] == str(WINDOW_END_NS)

    jobs = {attributes(key)["lane"]: entry["point"] for key, entry in receiver.series.items() if key[0] == "onmaru_ci_job_duration_seconds"}
    assert jobs["spring-full"]["count"] == "1" and jobs["spring-full"]["sum"] == pytest.approx(300.0)
    assert [int(c) for c in jobs["spring-full"]["bucketCounts"]].index(1) == bucket_index(300.0) == 6

    (container,) = receiver.points("onmaru_ci_testcontainers_startup_seconds")
    assert container["point"]["sum"] == pytest.approx(4.1)

    gauge = receiver.points("onmaru_ci_tests_selected_total")[0]
    assert gauge["kind"] == "gauge" and gauge["point"]["asDouble"] == 500.0
    assert "count" not in gauge["point"] and "startTimeUnixNano" not in gauge["point"]


def test_bucket_edges_are_upper_inclusive_and_overflow_is_open_ended():
    values = (1.0, 1.0000001, 3600.0, 3600.5)
    point = MetricPoint("onmaru_ci_job_duration_seconds", "s", values, {"workflow": "ci", "lane": "other", "result": "success"},
                        WINDOW_END_NS, "histogram", WINDOW_START_NS, ONMARU_BOUNDS)
    identity = EvidenceIdentity("YRootLab/OnMaru-backend", 1, 1, "sha256:" + "a" * 64)
    bundle = TelemetryBundle(identity, (point,), (), (), "success")
    body = json.loads(payloads(bundle)[0].body)
    data = body["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["histogram"]["dataPoints"][0]
    counts = [int(c) for c in data["bucketCounts"]]
    assert counts[0] == 1 and counts[1] == 1 and counts[10] == 1 and counts[11] == 1
    assert len(counts) == len(ONMARU_BOUNDS) + 1 and sum(counts) == int(data["count"]) == 4


# --------------------------------------------------------------------------
# Replay, restart and retry: no double count, source conclusion preserved
# --------------------------------------------------------------------------

def test_replay_after_restart_is_suppressed_without_requests(receiver_server, tmp_path):
    receiver, endpoint = receiver_server()
    store_path = tmp_path / "replay.sqlite"
    bundle = layer()
    assert export(bundle, endpoint, store_path).status == "exported"
    before = copy.deepcopy(receiver.series)
    requests_before = len(receiver.requests)
    replay = export(bundle, endpoint, store_path)  # new store object: simulated process restart
    assert replay.status == "duplicate" and replay.request_attempts == 0 and replay.ci_conclusion == "success"
    assert len(receiver.requests) == requests_before and receiver.series == before


def test_retry_resends_identical_snapshot_and_receiver_counts_it_once(receiver_server, tmp_path):
    receiver, endpoint = receiver_server(script=[503])
    bundle = layer()
    result = export(bundle, endpoint, tmp_path / "replay.sqlite")
    assert result.status == "exported" and result.request_attempts == 3
    metric_bodies = [body for path, body in receiver.requests if path == "/v1/metrics"]
    assert len(metric_bodies) == 2 and metric_bodies[0] == metric_bodies[1]
    for name in EMITTED_LAYER_METRICS:
        for entry in receiver.points(name):
            if entry["kind"] == "histogram":
                assert entry["point"]["count"] == "1"
    workflow = receiver.points("onmaru_ci_workflow_duration_seconds")
    assert len(workflow) == 1 and workflow[0]["point"]["count"] == "1"


def test_same_run_rebuilt_at_a_later_time_produces_identical_payloads():
    first = layer(observed_at_ns=OBSERVED_NS)
    second = layer(observed_at_ns=OBSERVED_NS + 9_000_000_000)
    assert [b.body for b in payloads(first)] == [b.body for b in payloads(second)]
    assert first.identity.key == second.identity.key


# --------------------------------------------------------------------------
# Verdict and export status are separate
# --------------------------------------------------------------------------

def test_export_outage_and_recovery_leave_source_verdict_unchanged(receiver_server, tmp_path):
    receiver, endpoint = receiver_server(script=[503, 503])
    bundle = layer()
    outage = export(bundle, endpoint, tmp_path / "replay.sqlite", max_attempts=2)
    assert outage.status == "failed" and outage.ci_conclusion == "success"
    assert bundle.ci_conclusion == "success"
    assert [b.body for b in payloads(bundle)] == [b.body for b in payloads(layer())]
    recovered = export(bundle, endpoint, tmp_path / "replay.sqlite")
    assert recovered.status == "exported" and recovered.ci_conclusion == "success"
    assert receiver.points("onmaru_ci_workflow_duration_seconds")[0]["point"]["count"] == "1"


def test_failed_source_stays_failed_in_metrics_and_trace():
    failed = manifest(run_overrides={"conclusion": "failure"})
    bundle = layer(failed)
    assert bundle.ci_conclusion == "failure"
    (workflow_span,) = [s for s in bundle.spans if s.name.startswith("RUN")]
    assert workflow_span.attributes["cicd.pipeline.result"] == "failure"
    assert workflow_span.status_code == 2
    workflow = next(p for p in bundle.metrics if p.name == "onmaru_ci_workflow_duration_seconds")
    assert dict(workflow.labels)["result"] == "failure"


# --------------------------------------------------------------------------
# Finite labels, budgets and raw identity
# --------------------------------------------------------------------------

@pytest.mark.parametrize("budget", [
    TelemetryBudget(max_series=2),
    TelemetryBudget(max_spans=2),
    TelemetryBudget(max_span_attributes=3),
    TelemetryBudget(max_label_value_length=4),
])
def test_label_and_span_budget_overflow_is_rejected_not_truncated(budget):
    with pytest.raises(BudgetExceeded):
        layer(budget=budget)


@pytest.mark.parametrize("field, value", [("max_series", 0), ("max_spans", 10_000), ("max_span_attributes", True)])
def test_invalid_budget_configuration_is_rejected(field, value):
    with pytest.raises(ValueError):
        TelemetryBudget(**{field: value})


@pytest.mark.parametrize("keyword, value", [
    ("lane", SHA), ("lane", "PR-123"), ("lane", RUN_URL), ("lane", "ServiceTest"),
    ("event", "pull_request;drop"), ("event", SHA), ("test_type", "10-tests"),
])
def test_raw_identity_or_unknown_values_are_never_labels(keyword, value):
    kwargs = {"lane": "spring-full", "event": "pull_request", "test_type": "affected"}
    kwargs[keyword] = value
    with pytest.raises(ValueError):
        transform_layer_evidence(manifest(), POLICY, observed_at_ns=OBSERVED_NS,
                                 performance_bytes=envelope_bytes(), **kwargs)


def test_metric_labels_are_finite_and_identity_free_in_every_payload():
    bundle = layer()
    assert bundle.metrics
    for point in bundle.metrics:
        assert set(point.labels) <= ONMARU_LABELS
        assert point.labels["workflow"] == "ci"
        if "lane" in point.labels:
            assert point.labels["lane"] in LANES
        if "event" in point.labels:
            assert point.labels["event"] in EVENTS
        if "test_type" in point.labels:
            assert point.labels["test_type"] in TEST_TYPES
        if "cache_result" in point.labels:
            assert point.labels["cache_result"] in CACHE_RESULTS
        if "result" in point.labels:
            assert point.labels["result"] in {"success", "failure", "cancellation", "timeout", "skip", "error", "unknown", "incomplete"}
    body = b"".join(batch.body for batch in payloads(bundle) if batch.signal == "metrics").decode()
    for forbidden in (SHA, RUN_ID, RUN_URL, bundle.identity.manifest_digest, "YRootLab"):
        assert forbidden not in body
    spans = b"".join(batch.body for batch in payloads(bundle) if batch.signal == "traces").decode()
    assert RUN_URL in spans and SHA in spans


def test_manifest_and_envelope_tampering_fail_closed():
    value = manifest()
    tampered = copy.deepcopy(value)
    tampered["source"]["conclusion"] = "failure"
    with pytest.raises(ValueError, match="modified"):
        transform_layer_evidence(tampered, POLICY, event="push", lane="spring-full", observed_at_ns=OBSERVED_NS,
                                 performance_bytes=envelope_bytes())
    altered = envelope_bytes(dict(ENVELOPE, quality="partial"))
    with pytest.raises(ValueError, match="digest"):
        transform_layer_evidence(value, POLICY, event="push", lane="spring-full", observed_at_ns=OBSERVED_NS,
                                 performance_bytes=altered)
    with pytest.raises(ValueError, match="requires its artifact bytes"):
        transform_layer_evidence(value, POLICY, event="push", lane="spring-full", observed_at_ns=OBSERVED_NS)
    unjoined = normalize_execution(timeline(), [])
    with pytest.raises(ValueError, match="without a joined manifest"):
        transform_layer_evidence(unjoined, POLICY, event="push", lane="other", observed_at_ns=OBSERVED_NS,
                                 performance_bytes=envelope_bytes())


# --------------------------------------------------------------------------
# Nested waterfall inside the tests span; no re-addition
# --------------------------------------------------------------------------

def spans_by_name(bundle):
    return {span.name: span for span in bundle.spans}


def test_context_container_flyway_are_a_waterfall_inside_test_duration():
    bundle = layer()
    spans = spans_by_name(bundle)
    tests = spans["tests"]
    assert tests.end_ns - tests.start_ns == 91_000_000_000
    assert tests.parent_span_id == spans["RUN ci"].span_id
    for name in ("context_init", "container_prepare", "flyway"):
        child = spans[name]
        assert child.parent_span_id == tests.span_id
        assert tests.start_ns <= child.start_ns <= child.end_ns <= tests.end_ns
        assert child.attributes["toolkit.ci.nested_in"] == "tests"
        assert child.attributes["toolkit.ci.placement"] == "unverified"
        assert child.attributes["toolkit.ci.clipped"] is False
    assert spans["context_init"].end_ns - spans["context_init"].start_ns == 8_200_500_000
    # Nested durations are not summed into any metric or into the test span.
    nested_total = 8_200_500_000 + 4_100_000_000 + 1_900_000_000
    values = [v for point in bundle.metrics for v in point.values]
    assert all(abs(v - nested_total / 1e9) > 1e-6 for v in values)


def test_nested_timing_longer_than_tests_is_clipped_and_marked():
    document = copy.deepcopy(ENVELOPE)
    document["timings_ms"] = {"tests": 1000.0, "context_init": 8200.5, "container_prepare": 0.0}
    spans = spans_by_name(layer(envelope=document))
    assert spans["tests"].end_ns - spans["tests"].start_ns == 1_000_000_000
    assert spans["context_init"].end_ns - spans["context_init"].start_ns == 1_000_000_000
    assert spans["context_init"].attributes["toolkit.ci.clipped"] is True
    assert spans["container_prepare"].end_ns == spans["container_prepare"].start_ns


def test_unavailable_measurements_are_omitted_not_zero():
    unavailable = json.loads((FIXTURES / "performance-evidence/unavailable.json").read_text())
    bundle = layer(envelope=unavailable)
    names = {point.name for point in bundle.metrics}
    assert "onmaru_ci_tests_selected_total" not in names
    assert "onmaru_ci_tests_executed_total" not in names
    assert "onmaru_ci_build_cache_operations_total" not in names
    assert not any(name.startswith(("tests", "context", "container", "flyway", "gradle")) for name in spans_by_name(bundle))


# --------------------------------------------------------------------------
# Contract registry and dashboard
# --------------------------------------------------------------------------

ISSUE_METRICS = {
    "onmaru_ci_workflow_duration_seconds", "onmaru_ci_job_duration_seconds", "onmaru_ci_gradle_task_duration_seconds",
    "onmaru_ci_gradle_tasks_total", "onmaru_ci_build_cache_operations_total", "onmaru_ci_build_cache_bytes",
    "onmaru_ci_tests_selected_total", "onmaru_ci_tests_executed_total", "onmaru_ci_spring_context_loads_total",
    "onmaru_ci_testcontainers_startup_seconds", "onmaru_ci_affected_fallback_total", "onmaru_ci_selection_mismatch_total",
}


def test_every_issue_metric_is_either_emitted_or_declared_unavailable():
    assert set(EMITTED_LAYER_METRICS) | UNAVAILABLE_LAYER_METRICS == ISSUE_METRICS
    assert not set(EMITTED_LAYER_METRICS) & UNAVAILABLE_LAYER_METRICS
    emitted = {point.name for point in layer().metrics}
    assert emitted <= set(EMITTED_LAYER_METRICS)
    assert not emitted & UNAVAILABLE_LAYER_METRICS


def performance_dashboard():
    return json.loads((ROOT / "observability/dashboards/ci-performance.json").read_text())


def test_generated_performance_dashboard_is_current_and_queries_use_registered_names():
    script = ROOT / "scripts/build_ci_dashboard.py"
    result = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    queries = json.loads((ROOT / "observability/queries/ci-performance.json").read_text())["queries"]
    for item in queries:
        if item["language"] != "promql" or item.get("source") == "collector-internal":
            continue
        names = {re.sub(r"_(bucket|sum|count)$", "", name) for name in re.findall(r"onmaru_ci_[a-z_]+", item["query"])}
        assert names and names <= set(EMITTED_LAYER_METRICS) | UNAVAILABLE_LAYER_METRICS
        labels = set(re.findall(r'([a-z_]+)\s*(?:=~|!=|=)\s*"', item["query"]))
        for group in re.findall(r"by \(([^)]*)\)", item["query"]):
            labels |= {label.strip() for label in group.split(",")}
        if item.get("source") != "collector-internal":
            assert labels <= ONMARU_LABELS | {"le"}, labels


def test_gauges_never_get_rate_and_histograms_are_not_quantile_across_runs():
    for item in json.loads((ROOT / "observability/queries/ci-performance.json").read_text())["queries"]:
        query = item["query"]
        assert "rate(" not in query and "increase(" not in query and "irate(" not in query
        if "histogram_quantile" in query:
            assert "_bucket{" in query


def test_every_trace_panel_links_tempo_and_actions_to_the_same_run():
    dashboard = performance_dashboard()
    trace_panels = [panel for panel in dashboard["panels"] if panel["type"] == "table"]
    assert len(trace_panels) == 3
    for panel in trace_panels:
        overrides = {o["matcher"]["options"]: o for o in panel["fieldConfig"]["overrides"]}
        links = {link["title"]: link["url"] for prop in overrides["cicd.pipeline.run.id"]["properties"] for link in prop["value"]}
        assert links["Actions run"] == "https://github.com/YRootLab/OnMaru-backend/actions/runs/${__value.raw:percentencode}"
        assert links["Manifest artifacts"] == links["Actions run"] + "#artifacts"

    bundle = layer()
    workflow = next(span for span in bundle.spans if span.attributes["toolkit.ci.scope"] == "layer-run")
    layer_panel = next(p for p in trace_panels if "layer-run" in p["targets"][0]["query"])
    overrides = {o["matcher"]["options"]: o for o in layer_panel["fieldConfig"]["overrides"]}
    actions_url = next(l["url"] for prop in overrides["cicd.pipeline.run.id"]["properties"] for l in prop["value"] if l["title"] == "Actions run")
    rendered = actions_url.replace("${__value.raw:percentencode}", workflow.attributes["cicd.pipeline.run.id"])
    assert rendered == workflow.attributes["cicd.pipeline.run.url.full"] == RUN_URL

    placeholder = "${__value.raw:percentencode}"
    tempo_url = next(link["url"] for prop in overrides["traceIdHidden"]["properties"] if prop["id"] == "links" for link in prop["value"] if link["title"] == "Tempo trace")
    assert tempo_url.count(placeholder) == 1
    rendered = tempo_url.replace(placeholder, workflow.trace_id)
    panes = json.loads(unquote(parse_qs(urlsplit(rendered).query)["panes"][0]))
    assert panes["trace"]["datasource"] == "local-tempo"
    assert panes["trace"]["queries"][0]["query"] == workflow.trace_id


def test_layer_trace_id_differs_from_actions_evidence_trace_for_the_same_run():
    from test_otlp_transform import transformed
    actions = transformed()
    layer_bundle = layer()
    assert actions.spans[0].trace_id != layer_bundle.spans[0].trace_id
    assert {s.attributes["toolkit.ci.scope"] for s in layer_bundle.spans} <= {"layer-run", "layer"}


def test_offline_smoke_covers_success_failure_outage_and_replay():
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run([sys.executable, str(ROOT / "scripts/ci_dashboard_smoke.py"), "--offline"],
                            capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "passed"
    scenarios = report["scenarios"]
    assert scenarios["success"] == {"export": "exported", "verdict": "success"}
    assert scenarios["failure"] == {"export": "exported", "verdict": "failure"}
    assert scenarios["outage"]["export"] == "failed" and scenarios["outage"]["verdict"] == "success"
    assert scenarios["replay"] == {"export": "duplicate", "request_attempts": 0}
    assert scenarios["outage_recovery"] == {"export": "exported"}
