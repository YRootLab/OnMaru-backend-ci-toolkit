import importlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from test_otlp_transform import transformed


def api():
    import pipeline_toolkit.telemetry as telemetry
    assert hasattr(telemetry, "export_otlp"), "bounded OTLP exporter is missing"
    return importlib.import_module("pipeline_toolkit.telemetry.export")


def config(**overrides):
    return api().ExportConfig("http://127.0.0.1:4318", **overrides)


def all_points(batches):
    result = []
    for batch in batches:
        if batch.signal == "metrics":
            for scope in json.loads(batch.body)["resourceMetrics"][0]["scopeMetrics"]:
                for metric in scope["metrics"]:
                    result.extend(metric.get("gauge", metric.get("histogram"))["dataPoints"])
    return result


def test_otlp_json_batches_preserve_every_span_and_metric_without_identity_labels():
    exporter = api()
    bundle = transformed()
    batches = exporter.build_batches(bundle, config(max_items=2, max_payload_bytes=5000))
    assert len(all_points(batches)) == len(bundle.metrics)
    spans = [span for b in batches if b.signal == "traces" for span in json.loads(b.body)["resourceSpans"][0]["scopeSpans"][0]["spans"]]
    assert len(spans) == 3
    assert {s["startTimeUnixNano"] for s in spans} == {"1790812801000000000", "1790812802000000000"}
    assert {s["endTimeUnixNano"] for s in spans} == {"1790812809000000000", "1790812808000000000"}
    assert all(type(s["kind"]) is int and type(s["status"]["code"]) is int for s in spans)
    for batch in batches:
        assert batch.item_count <= 2 and len(batch.body) <= 5000
        assert batch.body == json.dumps(json.loads(batch.body), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    metric_body = b"".join(b.body for b in batches if b.signal == "metrics").decode()
    assert "manifest" not in metric_body and "run.id" not in metric_body and "example/backend" not in metric_body
    assert batches == exporter.build_batches(bundle, config(max_items=2, max_payload_bytes=5000))


def test_histogram_keeps_count_sum_and_duration_and_gauges_remain_non_cumulative():
    batches = api().build_batches(transformed(), config())
    metrics = [m for b in batches if b.signal == "metrics" for m in json.loads(b.body)["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]]
    duration = next(m for m in metrics if m["name"] == "toolkit_ci_job_duration_seconds")
    assert duration["histogram"]["aggregationTemporality"] == 1
    point = duration["histogram"]["dataPoints"][0]
    assert (point["count"], point["sum"], point["bucketCounts"]) == ("1", 8.0, ["1"])
    assert point["explicitBounds"] == []
    assert point["startTimeUnixNano"] == "1790812801000000000"
    work = next(m for m in metrics if m["name"] == "toolkit_ci_work_seconds")
    assert sorted(p["asDouble"] for p in work["gauge"]["dataPoints"]) == [6.0, 8.0]


def test_serialized_metric_labels_do_not_collide_with_prometheus_target_or_resource_labels():
    reserved = {"job", "instance", "__name__", "__address__", "le", "quantile", "otel_scope_name", "otel_scope_version", "service_name", "service_namespace", "service_instance_id"}
    points = all_points(api().build_batches(transformed(), config()))
    observed_jobs = set()
    for point in points:
        labels = {attribute["key"]: attribute["value"]["stringValue"] for attribute in point["attributes"]}
        assert not reserved.intersection(labels)
        assert not any(label.startswith("__") for label in labels)
        if "ci_job" in labels:
            observed_jobs.add(labels["ci_job"])
    assert observed_jobs == {"api", "worker"}


def test_oversize_item_and_batch_count_abort_before_any_transport(tmp_path):
    exporter = api()
    calls = []
    for settings in (config(max_payload_bytes=256), config(max_items=1, max_batches=1)):
        result = exporter.export_otlp(transformed(), settings, exporter.SQLiteReplayStore(tmp_path / "replay.sqlite"), transport=lambda *args: calls.append(args))
        assert result.status == "failed" and result.reason == "payload_limit"
        assert result.ci_conclusion == "cancelled"
    assert calls == []


def test_acknowledged_replay_is_suppressed_across_store_reopening(tmp_path):
    exporter = api()
    calls = []
    def transport(url, body, headers, timeout):
        calls.append(url)
        assert headers["Content-Type"] == "application/json" and timeout <= 5
        return exporter.HttpResponse(200, b"{}")
    path = tmp_path / "replay.sqlite"
    first = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(path), transport=transport)
    count = len(calls)
    second = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(path), transport=transport)
    assert first.status == "exported" and first.acknowledged_batches == 2
    assert second.status == "duplicate" and second.request_attempts == 0
    assert len(calls) == count == 2


def test_failed_trace_export_resumes_without_resending_acknowledged_metrics(tmp_path):
    exporter = api()
    store = exporter.SQLiteReplayStore(tmp_path / "replay.sqlite")
    calls = []
    def failing(url, body, headers, timeout):
        calls.append(url)
        return exporter.HttpResponse(200 if url.endswith("metrics") else 401, b"{}")
    first = exporter.export_otlp(transformed(), config(), store, transport=failing)
    assert first.status == "failed" and first.reason == "http_401" and first.acknowledged_batches == 1
    assert first.ci_conclusion == "cancelled"
    def working(url, body, headers, timeout):
        assert url.endswith("traces")
        return exporter.HttpResponse(200, b"{}")
    second = exporter.export_otlp(transformed(), config(), store, transport=working)
    assert second.status == "exported" and second.request_attempts == 1
    assert len(calls) == 2


def test_timeout_and_retryable_http_use_bounded_backoff_and_identical_payload(tmp_path):
    exporter = api()
    bodies, sleeps = [], []
    def transport(url, body, headers, timeout):
        bodies.append(body)
        assert timeout == 2
        if len(bodies) == 1:
            raise TimeoutError("authorization=do-not-leak")
        if len(bodies) == 2:
            return exporter.HttpResponse(503, b"{}", {"Retry-After": "2"})
        return exporter.HttpResponse(200, b"{}")
    result = exporter.export_otlp(transformed(), config(timeout_seconds=2), exporter.SQLiteReplayStore(tmp_path / "replay.sqlite"), transport=transport, sleep=sleeps.append, jitter=lambda: 0)
    assert result.status == "exported" and result.request_attempts == 4
    assert result.attempted_batches == result.succeeded_batches == result.total_batches == 2
    assert result.terminal_partial_batches == result.pending_batches == 0
    assert sleeps == [0.25, 2.0]
    assert bodies[0] == bodies[1] == bodies[2]
    assert "do-not-leak" not in repr(result)


@pytest.mark.parametrize("code", [400, 401, 403, 413, 500])
def test_permanent_http_errors_are_not_retried_or_allowed_to_change_ci_verdict(tmp_path, code):
    exporter = api()
    result = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(tmp_path / "replay.sqlite"), transport=lambda *args: exporter.HttpResponse(code, b'{"message":"secret"}'))
    assert result.status == "failed" and result.reason == "http_" + str(code)
    assert result.request_attempts == 1 and result.ci_conclusion == "cancelled"


def test_metrics_partial_success_still_delivers_traces_and_never_replays_terminal_batches(tmp_path):
    exporter = api()
    store = exporter.SQLiteReplayStore(tmp_path / "replay.sqlite")
    calls = []
    def partial(url, body, headers, timeout):
        calls.append(url)
        return exporter.HttpResponse(200, b'{"partialSuccess":{"rejectedDataPoints":"1","errorMessage":"password=secret"}}' if url.endswith("metrics") else b"{}")
    first = exporter.export_otlp(transformed(), config(), store, transport=partial)
    second = exporter.export_otlp(transformed(), config(), store, transport=partial)
    assert first.status == second.status == "partial"
    assert first.reason == second.reason == "receiver_partial_success"
    assert calls == ["http://127.0.0.1:4318/v1/metrics", "http://127.0.0.1:4318/v1/traces"]
    assert first.request_attempts == first.attempted_batches == 2
    assert second.request_attempts == second.attempted_batches == 0
    for result in (first, second):
        assert result.total_batches == 2
        assert result.acknowledged_batches == result.succeeded_batches == 1
        assert result.terminal_partial_batches == 1 and result.pending_batches == 0
    assert "secret" not in repr(first)


def test_partial_metric_batch_does_not_drop_other_metric_batches(tmp_path):
    exporter = api()
    settings = config(max_items=1)
    planned = exporter.build_batches(transformed(), settings)
    sent = []
    def transport(url, body, headers, timeout):
        sent.append((url, body))
        return exporter.HttpResponse(200, b'{"partialSuccess":{"rejectedDataPoints":"1"}}' if len(sent) == 1 else b"{}")
    result = exporter.export_otlp(transformed(), settings, exporter.SQLiteReplayStore(tmp_path / "replay.sqlite"), transport=transport)
    assert len(sent) == len(planned) > 2
    assert result.status == "partial" and result.terminal_partial_batches == 1
    assert result.succeeded_batches == len(planned) - 1
    assert result.attempted_batches == result.request_attempts == result.total_batches == len(planned)
    assert result.pending_batches == 0


def test_partial_metrics_with_failed_traces_replays_only_pending_traces(tmp_path):
    exporter = api()
    path = tmp_path / "replay.sqlite"
    def first_transport(url, body, headers, timeout):
        return exporter.HttpResponse(200, b'{"partialSuccess":{"rejectedDataPoints":"1"}}') if url.endswith("metrics") else exporter.HttpResponse(401, b"{}")
    first = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(path), transport=first_transport)
    assert first.status == "partial" and first.reason == "http_401"
    assert first.attempted_batches == 2 and first.succeeded_batches == 0
    assert first.terminal_partial_batches == 1 and first.pending_batches == 1
    def retry_transport(url, body, headers, timeout):
        assert url.endswith("traces"), "a partially accepted metric batch must not replay"
        return exporter.HttpResponse(200, b"{}")
    resumed = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(path), transport=retry_transport)
    assert resumed.status == "partial" and resumed.reason == "receiver_partial_success"
    assert resumed.request_attempts == resumed.attempted_batches == 1
    assert resumed.succeeded_batches == resumed.terminal_partial_batches == 1
    assert resumed.total_batches == 2 and resumed.pending_batches == 0


def test_replay_resumes_legacy_export_level_partial_state(tmp_path):
    exporter = api()
    class LegacyStore(exporter.SQLiteReplayStore):
        def finish(self, key, owner, state):
            super().finish(key, owner, "partial")
    path = tmp_path / "replay.sqlite"
    first = exporter.export_otlp(transformed(), config(), LegacyStore(path), transport=lambda url, *args: exporter.HttpResponse(200, b'{"partialSuccess":{"rejectedDataPoints":"1"}}') if url.endswith("metrics") else exporter.HttpResponse(401, b"{}"))
    assert first.status == "partial" and first.pending_batches == 1
    sent = []
    def transport(url, *args):
        sent.append(url)
        return exporter.HttpResponse(200, b"{}")
    resumed = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(path), transport=transport)
    assert sent == ["http://127.0.0.1:4318/v1/traces"]
    assert resumed.status == "partial" and resumed.pending_batches == 0


def test_checkpoint_read_failure_releases_the_newly_acquired_lease(tmp_path):
    exporter = api()
    class BrokenReader(exporter.SQLiteReplayStore):
        def batch_state(self, key, batch):
            raise OSError("unreadable checkpoint")
    path = tmp_path / "replay.sqlite"
    first = exporter.export_otlp(transformed(), config(), BrokenReader(path), transport=lambda *args: pytest.fail("unreadable checkpoint sent"))
    assert first.reason == "export_state_error"
    resumed = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(path), transport=lambda *args: exporter.HttpResponse(200, b"{}"))
    assert resumed.status == "exported" and resumed.succeeded_batches == 2


def test_export_deadline_and_attempt_limit_stop_retries(tmp_path):
    exporter = api()
    elapsed = [0.0]
    def slow(url, body, headers, timeout):
        elapsed[0] += timeout
        raise TimeoutError()
    result = exporter.export_otlp(transformed(), config(timeout_seconds=2, total_timeout_seconds=3), exporter.SQLiteReplayStore(tmp_path / "replay.sqlite"), transport=slow, clock=lambda: elapsed[0], sleep=lambda delay: elapsed.__setitem__(0, elapsed[0] + delay), jitter=lambda: 0)
    assert result.status == "failed" and result.reason == "deadline_exceeded"
    assert result.request_attempts == 2 and elapsed[0] == 3
    result = exporter.export_otlp(transformed(), config(max_attempts=2), exporter.SQLiteReplayStore(tmp_path / "other.sqlite"), transport=lambda *args: exporter.HttpResponse(503, b"{}"), sleep=lambda delay: None, jitter=lambda: 0)
    assert result.request_attempts == 2 and result.reason == "http_503"


@pytest.mark.parametrize("endpoint", ["http://example.com", "https://user:secret@example.com", "https://example.com?token=x", "file:///tmp/out", "https://example.com/#fragment"])
def test_unsafe_endpoint_configuration_is_rejected(endpoint):
    with pytest.raises(ValueError, match="endpoint"):
        api().ExportConfig(endpoint)


def test_actual_http_json_transport_accepts_local_collector_contract(tmp_path):
    exporter = api()
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, self.headers["Content-Type"], json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        result = exporter.export_otlp(transformed(), exporter.ExportConfig("http://127.0.0.1:" + str(server.server_port)), exporter.SQLiteReplayStore(tmp_path / "replay.sqlite"))
        assert result.status == "exported"
        assert [path for path, _, _ in received] == ["/v1/metrics", "/v1/traces"]
        assert all(content_type == "application/json" for _, content_type, _ in received)
        assert "resourceMetrics" in received[0][2] and "resourceSpans" in received[1][2]
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_concurrent_replay_is_busy_without_a_second_network_send(tmp_path):
    exporter = api()
    path = tmp_path / "replay.sqlite"
    results = []
    def transport(*args):
        results.append(exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(path), transport=lambda *args: pytest.fail("concurrent duplicate sent")))
        return exporter.HttpResponse(200, b"{}")
    result = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(path), transport=transport)
    assert result.status == "exported"
    assert all(result.status == "busy" and result.request_attempts == 0 for result in results)


def test_changed_batch_plan_does_not_silently_recount_acknowledged_evidence(tmp_path):
    exporter = api()
    store = exporter.SQLiteReplayStore(tmp_path / "replay.sqlite")
    first = exporter.export_otlp(transformed(), config(), store, transport=lambda *args: exporter.HttpResponse(200, b"{}"))
    assert first.status == "exported"
    changed = exporter.export_otlp(transformed(), config(max_items=1), store, transport=lambda *args: pytest.fail("changed replay sent"))
    assert changed.status == "failed" and changed.reason == "replay_plan_mismatch"


@pytest.mark.parametrize("body", [b'[]', b'not-json', b'{"partialSuccess":{"rejectedDataPoints":true}}', b'{"partialSuccess":{"rejectedDataPoints":1.5}}', b'{"partialSuccess":{"rejectedDataPoints":null}}', b'{"partialSuccess":{"rejectedDataPoints":"-1"}}', b'{}' * 40000])
def test_malformed_collector_response_never_acknowledges_or_retries(tmp_path, body):
    exporter = api()
    result = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(tmp_path / "replay.sqlite"), transport=lambda *args: exporter.HttpResponse(200, body))
    assert result.status == "failed" and result.reason == "invalid_response"
    assert result.acknowledged_batches == 0 and result.request_attempts == 1


def test_retry_after_exceeding_budget_is_not_shortened_into_aggressive_retry(tmp_path):
    exporter = api()
    result = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(tmp_path / "replay.sqlite"), transport=lambda *args: exporter.HttpResponse(429, b"{}", {"Retry-After": "300"}), sleep=lambda delay: pytest.fail("unbounded sleep"))
    assert result.reason == "retry_delay_limit" and result.request_attempts == 1


def test_store_failure_never_leaks_exception_text_or_changes_ci_verdict(tmp_path):
    exporter = api()
    store = exporter.SQLiteReplayStore(tmp_path / "replay.sqlite", max_entries=0)
    result = exporter.export_otlp(transformed(), config(), store, transport=lambda *args: pytest.fail("full store sent"))
    assert result.status == "failed" and result.reason == "export_state_error"
    assert result.ci_conclusion == "cancelled" and result.request_attempts == 0


def test_partial_ack_survives_crash_and_remaining_traces_resume_after_lease_expiry(tmp_path):
    exporter = api()
    class CrashingStore(exporter.SQLiteReplayStore):
        def record_batch(self, key, batch, owner, state):
            super().record_batch(key, batch, owner, state)
            if state == "partial":
                raise SystemExit("simulated process loss after durable partial checkpoint")
        def finish(self, key, owner, state):
            pass  # A lost process cannot release its lease.
    path = tmp_path / "replay.sqlite"
    now = [100.0]
    with pytest.raises(SystemExit):
        exporter.export_otlp(transformed(), config(), CrashingStore(path, clock=lambda: now[0]), transport=lambda *args: exporter.HttpResponse(200, b'{"partialSuccess":{"rejectedDataPoints":"1"}}'))
    replay_store = exporter.SQLiteReplayStore(path, clock=lambda: now[0])
    busy = exporter.export_otlp(transformed(), config(), replay_store, transport=lambda *args: pytest.fail("active lease sent"))
    assert busy.status == "busy" and busy.request_attempts == 0
    now[0] = 136.0
    sent = []
    def transport(url, body, headers, timeout):
        sent.append(url)
        assert url.endswith("traces")
        return exporter.HttpResponse(200, b"{}")
    resumed = exporter.export_otlp(transformed(), config(), replay_store, transport=transport)
    assert resumed.status == "partial" and resumed.terminal_partial_batches == 1
    assert resumed.succeeded_batches == 1 and resumed.total_batches == 2
    assert resumed.request_attempts == resumed.attempted_batches == 1
    assert resumed.pending_batches == 0 and len(sent) == 1


def test_http_transport_deadline_stops_a_trickling_response():
    exporter = api()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.end_headers()
            try:
                for part in [b"{", b"}"] + [b" "] * 8:
                    self.wfile.write(part)
                    self.wfile.flush()
                    time.sleep(0.03)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with pytest.raises(TimeoutError):
            exporter.http_transport("http://127.0.0.1:" + str(server.server_port), b"{}", {"Content-Type": "application/json"}, 0.05)
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_duplicate_keys_in_receiver_ack_are_not_accepted(tmp_path):
    exporter = api()
    result = exporter.export_otlp(transformed(), config(), exporter.SQLiteReplayStore(tmp_path / "replay.sqlite"), transport=lambda *args: exporter.HttpResponse(200, b'{"partialSuccess":{"rejectedDataPoints":"1","rejectedDataPoints":"0"}}'))
    assert result.status == "failed" and result.reason == "invalid_response"
