"""Local stack boundary contracts; these run without Docker or credentials."""
import importlib.util
import json
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "observability/local"


def config(name):
    path = LOCAL / name
    assert path.is_file(), f"missing local stack configuration: {name}"
    return yaml.safe_load(path.read_text())


def test_compose_confines_ports_and_bounds_disposable_storage():
    compose = config("compose.yaml")
    services = compose["services"]
    assert set(services) == {"collector", "prometheus", "tempo", "grafana"}
    for service in services.values():
        assert re.search(r":v?\d+\.\d+\.\d+$", service["image"])
        assert service["healthcheck"]["test"][0] == "CMD"
        assert service["mem_limit"]
        assert service["logging"]["options"]["max-size"] == "5m"
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:")
        for mount in service.get("volumes", []):
            if mount.startswith("./"):
                assert mount.endswith(":ro")
                assert (LOCAL / mount.split(":")[0]).exists()
    volumes = compose["volumes"]
    assert set(volumes) == {"prometheus-data", "tempo-data", "grafana-data"}
    for volume in volumes.values():
        assert volume["driver_opts"]["type"] == "tmpfs"
        assert re.search(r"size=\d+m", volume["driver_opts"]["o"])
    assert "--storage.tsdb.retention.time=1h" in services["prometheus"]["command"]
    assert "--storage.tsdb.retention.size=128MB" in services["prometheus"]["command"]
    assert services["collector"]["depends_on"]["tempo"]["condition"] == "service_healthy"
    grafana_env = services["grafana"]["environment"]
    assert grafana_env["GF_AUTH_BASIC_ENABLED"] == "false"
    assert grafana_env["GF_SECURITY_DISABLE_INITIAL_ADMIN_CREATION"] == "true"
    # Explore needs Editor in current OSS Grafana; datasource edits still need Admin.
    assert grafana_env["GF_AUTH_ANONYMOUS_ORG_ROLE"] == "Editor"


def test_otlp_signals_reach_scrape_and_trace_backends():
    collector = config("otel-collector.yaml")
    protocols = collector["receivers"]["otlp"]["protocols"]
    assert protocols["grpc"]["endpoint"] == "0.0.0.0:4317"
    assert protocols["http"]["endpoint"] == "0.0.0.0:4318"
    pipelines = collector["service"]["pipelines"]
    assert pipelines["metrics"]["exporters"] == ["prometheus"]
    assert pipelines["traces"]["exporters"] == ["otlp_grpc/tempo"]
    for pipeline in pipelines.values():
        assert pipeline["receivers"] == ["otlp"]
        assert pipeline["processors"][0] == "memory_limiter"
    assert "health_check" in collector["service"]["extensions"]
    assert collector["exporters"]["otlp_grpc/tempo"]["endpoint"] == "tempo:4317"
    assert collector["exporters"]["prometheus"]["enable_open_metrics"] is True
    assert collector["exporters"]["prometheus"]["resource_constant_labels"]["included"] == ["service.name"]
    assert collector["exporters"]["prometheus"]["translation_strategy"] == "UnderscoreEscapingWithoutSuffixes"
    prometheus = config("prometheus.yaml")
    assert {target for job in prometheus["scrape_configs"] for group in job["static_configs"] for target in group["targets"]} >= {"collector:8889"}
    tempo = config("tempo.yaml")
    assert tempo["distributor"]["receivers"]["otlp"]["protocols"]["grpc"]["endpoint"] == "0.0.0.0:4317"
    assert tempo["storage"]["trace"]["backend"] == "local"
    assert tempo["compactor"]["compaction"]["block_retention"] == "1h"
    assert tempo["usage_report"]["reporting_enabled"] is False


def test_grafana_provisions_bidirectional_metric_trace_links():
    datasources = {item["uid"]: item for item in config("grafana/datasources.yaml")["datasources"]}
    prom = datasources["local-prometheus"]
    tempo = datasources["local-tempo"]
    assert (prom["type"], prom["url"]) == ("prometheus", "http://prometheus:9090")
    assert (tempo["type"], tempo["url"]) == ("tempo", "http://tempo:3200")
    assert prom["jsonData"]["exemplarTraceIdDestinations"] == [{"name": "trace_id", "datasourceUid": tempo["uid"]}]
    assert tempo["jsonData"]["tracesToMetrics"]["datasourceUid"] == prom["uid"]
    assert all(item["editable"] is False for item in datasources.values())


@pytest.fixture
def smoke():
    path = ROOT / "scripts/local_observability_smoke.py"
    assert path.is_file(), "missing fixture/query smoke tool"
    spec = importlib.util.spec_from_file_location("local_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_has_correlated_cumulative_counter_and_trace(smoke):
    metrics, traces = smoke.fixture_payloads("a" * 32, "b" * 16, 1_000_000_000)
    metric = metrics["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
    assert metric["name"] == "toolkit_local_fixture_total"
    assert metric["sum"]["isMonotonic"] is True
    assert metric["sum"]["aggregationTemporality"] == 2
    point = metric["sum"]["dataPoints"][0]
    assert point["asInt"] == "1"
    assert point["exemplars"][0]["traceId"] == "a" * 32
    span = traces["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["traceId"] == "a" * 32
    assert span["name"] == "local-stack-fixture"
    assert int(span["endTimeUnixNano"]) > int(span["startTimeUnixNano"])


def test_smoke_queries_real_http_boundaries_and_rejects_partial_success(smoke):
    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            captured.append(self.path)
            payload = {"status": "success", "data": {"result": [{"value": [1, "1"]}]}}
            if self.path.startswith("/api/traces/"):
                payload = {"batches": [{"scopeSpans": [{"spans": [{"name": "local-stack-fixture"}]}]}]}
            elif self.path.startswith("/api/v1/query_exemplars"):
                payload = {"status": "success", "data": [{"exemplars": [{"labels": {"trace_id": "a" * 32}}]}]}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        smoke.query_fixture(url, url, "a" * 32, timeout=1)
        assert any("query=toolkit_local_fixture_total" in path for path in captured)
        assert "/api/traces/" + "a" * 32 in captured
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    with pytest.raises(ValueError, match="metric"):
        smoke.validate_metric({"status": "success", "data": {"result": []}})
    with pytest.raises(ValueError, match="trace"):
        smoke.validate_trace({"batches": []})
    with pytest.raises(ValueError, match="exemplar"):
        smoke.validate_exemplar({"status": "success", "data": []}, "a" * 32)


def test_smoke_rejects_otlp_partial_success(smoke):
    smoke.validate_otlp({})
    smoke.validate_otlp({"partialSuccess": {"rejectedSpans": "0"}})
    for response in [{"partialSuccess": {"rejectedSpans": "1"}}, {"partialSuccess": {"rejectedDataPoints": "2"}}]:
        with pytest.raises(ValueError, match="rejected"):
            smoke.validate_otlp(response)


def test_smoke_rejects_nonlocal_and_nonfinite_configuration(smoke):
    for url in ["https://remote.example", "http://0.0.0.0:4318", "http://user:password@localhost:4318"]:
        with pytest.raises(ValueError, match="localhost"):
            smoke.local_url(url)
    for timeout in [0, -1, float("inf"), float("nan")]:
        with pytest.raises(ValueError, match="timeout"):
            smoke.positive_timeout(timeout)


def test_smoke_cli_checks_provisioning_and_delivers_both_signals(smoke, capsys):
    posted = {}
    linked = [True]

    class Handler(BaseHTTPRequestHandler):
        def respond(self, value):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_POST(self):
            posted[self.path] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.respond({})

        def do_GET(self):
            if self.path == "/api/health":
                self.respond({"database": "ok"})
            elif self.path.endswith("/local-prometheus"):
                self.respond({"type": "prometheus", "jsonData": {"exemplarTraceIdDestinations": [
                    {"name": "trace_id", "datasourceUid": "local-tempo" if linked[0] else "missing"}]}})
            elif self.path.endswith("/local-tempo"):
                self.respond({"type": "tempo", "jsonData": {"tracesToMetrics": {"datasourceUid": "local-prometheus"}}})
            elif self.path.startswith("/api/v1/query_exemplars"):
                trace_id = posted["/v1/traces"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
                self.respond({"status": "success", "data": [{"exemplars": [{"labels": {"trace_id": trace_id}}]}]})
            elif self.path.startswith("/api/v1/query?"):
                self.respond({"status": "success", "data": {"result": [{"value": [1, "1"]}]}})
            elif self.path.startswith("/api/traces/"):
                trace = posted["/v1/traces"]["resourceSpans"][0]
                self.respond({"batches": [trace]})
            else:
                self.respond({})

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    args = [arg for name in ("collector", "otlp", "prometheus", "tempo", "grafana") for arg in ("--" + name, url)]
    try:
        assert smoke.main(args + ["--health-only", "--timeout", "0.1"]) == 0
        assert posted == {}
        assert json.loads(capsys.readouterr().out)["status"] == "healthy"
        assert smoke.main(args + ["--timeout", "0.1"]) == 0
        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "passed"
        assert set(posted) == {"/v1/metrics", "/v1/traces"}
        assert output["trace_id"] == posted["/v1/traces"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
        linked[0] = False
        assert smoke.main(args + ["--health-only", "--timeout", "0.02"]) == 1
        assert "not linked" in capsys.readouterr().err
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
