"""Import/query boundaries of the real dashboard, independent of Docker."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def document(relative):
    path = ROOT / relative
    assert path.is_file(), f"missing dashboard contract: {relative}"
    return json.loads(path.read_text())


def test_importable_dashboard_resolves_provisioned_datasources_and_every_query():
    dashboard = document("observability/dashboards/ci-benchmark.json")
    contracts = document("observability/queries/ci-benchmark.json")
    sources = yaml.safe_load((ROOT / "observability/local/grafana/datasources.yaml").read_text())
    uids = {source["uid"]: source["type"] for source in sources["datasources"]}
    assert dashboard["uid"] == "toolkit-ci-benchmark" and dashboard["schemaVersion"] >= 39
    assert dashboard["id"] is None and dashboard["templating"]["list"] == []
    assert len({panel["id"] for panel in dashboard["panels"]}) == len(dashboard["panels"])
    actual = {}
    for panel in dashboard["panels"]:
        for target in panel.get("targets", []):
            ds = target["datasource"]
            assert uids[ds["uid"]] == ds["type"]
            assert target["refId"] == "A"
            actual[panel["id"]] = target.get("expr", target.get("query"))
    assert actual == {item["panel_id"]: item["query"] for item in contracts["queries"]}


def test_duration_queries_use_sum_count_not_unavailable_quantiles_or_wall_clock():
    queries = document("observability/queries/ci-benchmark.json")["queries"]
    for scope, name in [("workflow", "workflow_observed_window"), ("job", "job_duration"), ("step", "step_duration"), ("module", "module_duration")]:
        query = next(item["query"] for item in queries if item["key"] == scope + "_duration")
        assert f"toolkit_ci_{name}_seconds_sum" in query
        assert f"toolkit_ci_{name}_seconds_count" in query
        assert "/" in query
        assert all(word not in query for word in ("histogram_quantile", "rate(", "increase(", "wall_clock", "critical_path"))
    for key in ("work", "outcome", "collection_quality"):
        query = next(item["query"] for item in queries if item["key"] == key)
        assert all(word not in query for word in ("rate(", "increase(", "sum_over_time(", "or vector(0)"))


def test_queries_have_fixed_finite_scope_and_no_identity_metric_labels():
    for item in document("observability/queries/ci-benchmark.json")["queries"]:
        query = item["query"]
        assert "$" not in query
        if item["language"] == "promql":
            if item.get("source") == "collector-internal":
                assert 'job="collector-internal"' in query
                assert "or vector(0)" not in query
                continue
            assert 'workflow="ci"' in query and 'environment="test"' in query
            assert not re.search(r"run_id|sha|digest|url|test_name|path", query)
            assert "topk(20," in query or item["key"] == "workflow_duration"
        else:
            assert 'span.toolkit.ci.scope = "workflow"' in query
            assert 'span.vcs.repository.name = "YRootLab/OnMaru-backend"' in query
            assert 'span.cicd.pipeline.run.id =~ "[1-9][0-9]{0,18}"' in query
            assert "select(" in query


def test_success_and_failure_tables_offer_safe_trace_actions_and_manifest_links():
    dashboard = document("observability/dashboards/ci-benchmark.json")
    tables = [panel for panel in dashboard["panels"] if panel["type"] == "table"]
    assert len(tables) == 2
    for panel in tables:
        target = panel["targets"][0]
        assert target["limit"] == 20 and target["tableType"] == "spans"
        overrides = panel["fieldConfig"]["overrides"]
        # Actual Grafana 13 Tempo spans-frame names (not TraceQL attribute syntax).
        assert {override["matcher"]["options"] for override in overrides} == {"traceIdHidden", "cicd.pipeline.run.id"}
        trace = next(override for override in overrides if override["matcher"]["options"] == "traceIdHidden")
        assert {prop["id"]: prop["value"] for prop in trace["properties"]}["custom.hideFrom"] == {"viz": False}
        links = [link for override in overrides for prop in override["properties"] if prop["id"] == "links" for link in prop["value"]]
        assert {link["title"] for link in links} == {"Tempo trace", "Actions run", "Manifest artifacts"}
        for link in links:
            assert ":percentencode}" in link["url"]
            assert "url.full" not in link["url"] and "repository" not in link["url"]
            assert link["url"].startswith(("/explore?", "https://github.com/YRootLab/OnMaru-backend/actions/runs/"))
    queries = [panel["targets"][0]["query"] for panel in tables]
    assert any('span.cicd.pipeline.result = "success"' in query for query in queries)
    assert any('span.cicd.pipeline.result != "success"' in query for query in queries)


def test_provisioning_loads_the_committed_dashboard_from_readonly_mount():
    path = ROOT / "observability/local/grafana/dashboards.yaml"
    assert path.is_file(), "dashboard provisioning is missing"
    provider = yaml.safe_load(path.read_text())["providers"][0]
    assert provider["type"] == "file" and provider["allowUiUpdates"] is False
    assert provider["options"]["path"] == "/var/lib/grafana/dashboards"
    mounts = yaml.safe_load((ROOT / "observability/local/compose.yaml").read_text())["services"]["grafana"]["volumes"]
    assert "./grafana/dashboards.yaml:/etc/grafana/provisioning/dashboards/local.yaml:ro" in mounts
    assert "../dashboards:/var/lib/grafana/dashboards:ro" in mounts


def test_bundled_query_plugins_cannot_be_replaced_by_unbounded_background_downloads():
    environment = yaml.safe_load((ROOT / "observability/local/compose.yaml").read_text())["services"]["grafana"]["environment"]
    assert environment.get("GF_PLUGINS_PREINSTALL_DISABLED") == "true"
    assert environment.get("GF_PLUGINS_PREINSTALL_AUTO_UPDATE") == "false"


def test_collector_internal_metrics_are_scraped_without_host_exposure():
    collector = yaml.safe_load((ROOT / "observability/local/otel-collector.yaml").read_text())
    telemetry = collector["service"].get("telemetry", {})
    assert telemetry.get("metrics", {}).get("readers") == [{"pull": {"exporter": {"prometheus": {"host": "0.0.0.0", "port": 8888, "without_type_suffix": False, "without_units": True}}}}]
    jobs = yaml.safe_load((ROOT / "observability/local/prometheus.yaml").read_text())["scrape_configs"]
    assert any(job["job_name"] == "collector-internal" and job["static_configs"] == [{"targets": ["collector:8888"]}] for job in jobs)
    job = next(job for job in jobs if job["job_name"] == "collector-internal")
    assert job.get("sample_limit") == 128
    kept = job.get("metric_relabel_configs", [])
    assert len(kept) == 1 and kept[0]["action"] == "keep" and kept[0]["source_labels"] == ["__name__"]
    for name in ("send_failed_spans_total", "send_failed_metric_points_total", "sent_spans_total", "sent_metric_points_total", "queue_size", "queue_capacity", "in_flight_requests"):
        assert re.fullmatch(kept[0]["regex"], "otelcol_exporter_" + name)
    assert not re.fullmatch(kept[0]["regex"], "otelcol_exporter_enqueue_size_bucket")
    compose = yaml.safe_load((ROOT / "observability/local/compose.yaml").read_text())
    assert not any("8888" in port for service in compose["services"].values() for port in service.get("ports", []))


def test_export_health_does_not_invent_metrics_or_treat_no_data_as_success():
    dashboard = document("observability/dashboards/ci-benchmark.json")
    panels = {panel["id"]: panel for panel in dashboard["panels"]}
    queries = {item["key"]: item for item in document("observability/queries/ci-benchmark.json")["queries"]}
    for key, metric in (("export_failed_spans", "otelcol_exporter_send_failed_spans_total"), ("export_failed_metric_points", "otelcol_exporter_send_failed_metric_points_total"), ("export_queue_pressure", "otelcol_exporter_queue_size"), ("export_in_flight", "otelcol_exporter_in_flight_requests"), ("collector_scrape_health", "up{")):
        assert key in queries, "missing actual exporter-health signal: " + key
        item = queries[key]
        assert item["source"] == "collector-internal"
        assert metric in item["query"]
        assert panels[item["panel_id"]]["type"] == "timeseries"
        if key != "collector_scrape_health":
            assert 'and on() (up{job="collector-internal",instance="collector:8888"} == 1)' in item["query"]
        if key.startswith("export_failed"):
            assert "0 * sum by (exporter) (otelcol_exporter_sent_" in item["query"]
    assert "otelcol_exporter_queue_capacity" in queries["export_queue_pressure"]["query"]
    notices = [panel["options"]["content"] for panel in panels.values() if panel["type"] == "text"]
    assert any("pre-Collector" in notice and "ExportResult" in notice for notice in notices)


def test_canonical_generator_reproduces_committed_dashboard():
    script = ROOT / "scripts/build_ci_dashboard.py"
    assert script.is_file(), "canonical dashboard builder is missing"
    result = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr + result.stdout


def smoke_module():
    path = ROOT / "scripts/ci_dashboard_smoke.py"
    assert path.is_file(), "source-to-dashboard smoke tool is missing"
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("ci_dashboard_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_outage_fixture_is_bounded_and_uses_only_synthetic_trace_payloads():
    path = ROOT / "scripts/collector_outage_smoke.py"
    assert path.is_file(), "scoped Collector outage smoke is missing"
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("collector_outage_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payloads = module.outage_payloads(1790812810000000000)
    assert len(payloads) == 16
    for payload in payloads:
        assert len(json.dumps(payload).encode()) < 256 * 1024
        scope = payload["resourceSpans"][0]["scopeSpans"][0]
        spans = scope["spans"]
        assert len(spans) == 512 and len({span["spanId"] for span in spans}) == 512
        assert {span["name"] for span in spans} == {"collector-outage-fixture"}
    assert len({payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"] for payload in payloads}) == 16


def test_live_smoke_uses_real_success_failure_evidence_and_reserved_label_safe_transform():
    smoke = smoke_module()
    from pipeline_toolkit.telemetry import MetricPolicy, transform_actions_evidence
    for outcome, run_id in (("success", 8100000001), ("failure", 8100000002)):
        evidence = smoke.fixture_evidence(outcome, run_id, 1790812810000000000)
        assert evidence["run"]["conclusion"] == outcome
        assert evidence["metrics"]["observed_job_window_seconds"] == 8
        bundle = transform_actions_evidence(evidence, MetricPolicy("ci", "test", jobs={701: "api", 702: "worker"}, modules=("api", "worker")), observed_at_ns=1790812810000000000)
        assert {span.attributes["cicd.pipeline.run.id"] for span in bundle.spans} == {str(run_id)}
        assert next(span for span in bundle.spans if span.attributes["toolkit.ci.scope"] == "workflow").attributes["cicd.pipeline.result"] == outcome
        job = next(point for point in bundle.metrics if point.name == "toolkit_ci_job_duration_seconds")
        assert job.labels["ci_job"] == "api"
        assert all(not ({"job", "instance"} & set(point.labels)) for point in bundle.metrics)


def test_live_smoke_requires_nonempty_query_frames_and_expected_values():
    smoke = smoke_module()
    with pytest.raises(ValueError):
        smoke.validate_frames({"results": {"A": {"frames": []}}})
    with pytest.raises(ValueError):
        smoke.validate_frames({"results": {"A": {"error": "bad query"}}})
    with pytest.raises(ValueError):
        smoke.validate_frames({"results": {"A": {"frames": [{"data": {"values": [[]]}}]}}})
    with pytest.raises(ValueError):
        smoke.validate_frames({"results": {"A": {"frames": [{"data": {"values": [[1], [None]]}}]}}})
    smoke.validate_frames({"results": {"A": {"frames": [{"data": {"values": [[1], [8]]}}]}}})
    with pytest.raises(ValueError):
        smoke.validate_frames({"results": {"A": {"frames": [{"data": {"values": [[1], ["not a number"]]}}]}}}, numeric=True)
    with pytest.raises(ValueError):
        smoke.validate_frames({"results": {"A": {"frames": [{"data": {"values": [[1], [float("inf")]]}}]}}}, numeric=True)
    with pytest.raises(ValueError):
        smoke.validate_values({"status": "success", "data": {"result": [{"value": [1, "nan"]}]}}, [8])
    smoke.validate_values({"status": "success", "data": {"result": [{"value": [1, "8"]}]}}, [8])
