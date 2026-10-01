"""Bounded OTLP/HTTP JSON delivery with consumer-local durable checkpoints.

Acknowledgements suppress known successful replays, not ambiguous network loss:
OTLP does not provide an end-to-end exactly-once delivery guarantee.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import random
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from socket import timeout as SocketTimeout
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit

from .model import TelemetryBundle

MAX_RESPONSE_BYTES = 65536
MAX_TOTAL_BYTES = 16 * 1024 * 1024
SCOPE = {"name": "onmaru.pipeline-toolkit.ci", "version": "1"}
RESOURCE = {"attributes": [{"key": "service.name", "value": {"stringValue": "onmaru-ci"}}]}


@dataclass(frozen=True)
class ExportConfig:
    endpoint: str
    max_items: int = 128
    max_payload_bytes: int = 1024 * 1024
    max_batches: int = 256
    timeout_seconds: float = 5.0
    total_timeout_seconds: float = 30.0
    max_attempts: int = 3
    backoff_seconds: float = 0.25
    max_backoff_seconds: float = 5.0
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        try:
            parsed = urlsplit(self.endpoint)
            valid = parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})
            valid = valid and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
            valid = valid and not any(c.isspace() or c in "\\" for c in self.endpoint)
            parsed.port
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise ValueError("endpoint must be HTTPS (HTTP is limited to loopback), without credentials/query/fragment")
        for name, low, high in (("max_items", 1, 512), ("max_payload_bytes", 256, 4194304), ("max_batches", 1, 512), ("max_attempts", 1, 5)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("invalid exporter bound: " + name)
        for name, low, high in (("timeout_seconds", 0.01, 30), ("total_timeout_seconds", 0.01, 120), ("backoff_seconds", 0, 10), ("max_backoff_seconds", 0, 30)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not low <= value <= high:
                raise ValueError("invalid exporter bound: " + name)
        if any(not isinstance(k, str) or not isinstance(v, str) or "\r" in k + v or "\n" in k + v for k, v in self.headers.items()):
            raise ValueError("invalid exporter headers")
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


@dataclass(frozen=True)
class OtlpBatch:
    signal: str
    body: bytes
    item_count: int

    @property
    def key(self):
        return hashlib.sha256(self.signal.encode() + b":" + self.body).hexdigest()


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExportResult:
    status: str
    reason: str | None
    request_attempts: int
    acknowledged_batches: int
    total_batches: int
    ci_conclusion: str | None


def _attributes(values):
    def value(item):
        if type(item) is bool:
            return {"boolValue": item}
        if type(item) is int:
            return {"intValue": str(item)}
        return {"stringValue": str(item)}
    return [{"key": key, "value": value(item)} for key, item in sorted(values.items())]


def _payload(signal, items):
    if signal == "traces":
        spans = []
        for span in items:
            item = {"traceId": span.trace_id, "spanId": span.span_id, "name": span.name, "kind": span.kind,
                    "startTimeUnixNano": str(span.start_ns), "endTimeUnixNano": str(span.end_ns),
                    "attributes": _attributes(span.attributes), "status": {"code": span.status_code}}
            if span.parent_span_id:
                item["parentSpanId"] = span.parent_span_id
            spans.append(item)
        payload = {"resourceSpans": [{"resource": RESOURCE, "scopeSpans": [{"scope": SCOPE, "spans": spans}]}]}
    else:
        metrics = {}
        for point in items:
            key = (point.name, point.unit, point.kind)
            if key not in metrics:
                metrics[key] = {"name": point.name, "unit": point.unit, point.kind: {"dataPoints": []}}
                if point.kind == "histogram":
                    metrics[key][point.kind]["aggregationTemporality"] = 1  # DELTA
            data = {"attributes": _attributes(point.labels), "timeUnixNano": str(point.time_ns)}
            if point.kind == "histogram":
                if point.start_ns is not None:
                    data["startTimeUnixNano"] = str(point.start_ns)
                data.update({"count": str(len(point.values)),
                             "sum": sum(point.values), "min": min(point.values), "max": max(point.values),
                             "explicitBounds": [], "bucketCounts": [str(len(point.values))]})
            else:
                data["asDouble"] = sum(point.values)
            metrics[key][point.kind]["dataPoints"].append(data)
        payload = {"resourceMetrics": [{"resource": RESOURCE, "scopeMetrics": [{"scope": SCOPE, "metrics": list(metrics.values())}]}]}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def build_batches(bundle: TelemetryBundle, config: ExportConfig) -> tuple[OtlpBatch, ...]:
    """Build and validate every request before sending any of the observation."""
    batches, total_bytes = [], 0
    for signal, items in (("metrics", bundle.metrics), ("traces", bundle.spans)):
        pending = []
        for item in items:
            trial = pending + [item]
            body = _payload(signal, trial)
            if pending and (len(trial) > config.max_items or len(body) > config.max_payload_bytes):
                batches.append(OtlpBatch(signal, _payload(signal, pending), len(pending)))
                pending, body = [item], _payload(signal, [item])
            else:
                pending = trial
            if len(body) > config.max_payload_bytes or len(batches) >= config.max_batches:
                raise ValueError("payload_limit")
        if pending:
            batches.append(OtlpBatch(signal, _payload(signal, pending), len(pending)))
    total_bytes = sum(len(batch.body) for batch in batches)
    if len(batches) > config.max_batches or total_bytes > MAX_TOTAL_BYTES:
        raise ValueError("payload_limit")
    return tuple(batches)


class SQLiteReplayStore:
    """A consumer-owned SQLite file. No credentials, source payloads or URLs stored.

    A lease serializes concurrent exports. Acknowledged/partially accepted batches
    survive process restart. Full stores fail closed; retention is consumer-owned.
    """

    def __init__(self, path, *, max_entries=100000, clock=time.time):
        self.path, self.max_entries, self.clock = str(path), max_entries, clock
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS exports (key TEXT PRIMARY KEY, plan TEXT NOT NULL, owner TEXT, lease REAL NOT NULL, state TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS batches (export_key TEXT NOT NULL, key TEXT NOT NULL, state TEXT NOT NULL, PRIMARY KEY(export_key, key))")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=0.1)
        try:
            with db:
                yield db
        finally:
            db.close()

    def claim(self, key, plan, owner, lease_seconds):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT plan, owner, lease, state FROM exports WHERE key=?", (key,)).fetchone()
            if row:
                if row[0] != plan:
                    return "plan_mismatch"
                if row[3] in {"complete", "partial"}:
                    return row[3]
                if row[1] and row[2] > self.clock():
                    return "busy"
            elif db.execute("SELECT count(*) FROM exports").fetchone()[0] >= self.max_entries:
                raise ValueError("replay store full")
            db.execute("INSERT OR REPLACE INTO exports VALUES (?, ?, ?, ?, 'running')", (key, plan, owner, self.clock() + lease_seconds))
            return "claimed"

    def batch_state(self, key, batch):
        with self._connect() as db:
            row = db.execute("SELECT state FROM batches WHERE export_key=? AND key=?", (key, batch)).fetchone()
            return row[0] if row else None

    def record_batch(self, key, batch, owner, state):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner FROM exports WHERE key=?", (key,)).fetchone()
            if not row or row[0] != owner:
                raise ValueError("replay lease lost")
            db.execute("INSERT OR REPLACE INTO batches VALUES (?, ?, ?)", (key, batch, state))

    def finish(self, key, owner, state):
        with self._connect() as db:
            db.execute("UPDATE exports SET owner=NULL, lease=0, state=? WHERE key=? AND owner=?", (state, key, owner))


def http_transport(url, body, headers, timeout):
    """Direct HTTP(S), no proxy/redirect, bounded response and body-read deadline."""
    parsed = urlsplit(url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    deadline = time.monotonic() + timeout
    connection = connection_type(parsed.hostname, port=parsed.port, timeout=timeout)
    try:
        connection.request("POST", parsed.path or "/", body=body, headers=dict(headers))
        socket = connection.sock
        socket.settimeout(max(0.001, deadline - time.monotonic()))
        with connection.getresponse() as response:
            raw = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("response deadline exceeded")
                socket.settimeout(remaining)
                part = response.read1(min(4096, MAX_RESPONSE_BYTES + 1 - len(raw)))
                if not part:
                    return HttpResponse(response.status, bytes(raw), dict(response.headers))
                raw.extend(part)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError("response size bound")
    except SocketTimeout:
        raise TimeoutError("OTLP request timeout") from None
    finally:
        connection.close()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response key")
        result[key] = value
    return result


def _response(response):
    if not isinstance(response, HttpResponse) or len(response.body) > MAX_RESPONSE_BYTES:
        return "failed", "invalid_response"
    if response.status != 200:
        return "retry" if response.status in {429, 502, 503, 504} else "failed", "http_" + str(response.status)
    try:
        document = json.loads(response.body, object_pairs_hook=_unique_object)
        if not isinstance(document, dict):
            raise ValueError("invalid response")
        partial = document.get("partialSuccess", {})
        if not isinstance(partial, dict):
            raise ValueError("invalid partial success")
        rejected = 0
        for name in ("rejectedSpans", "rejectedDataPoints"):
            number = partial.get(name, 0)
            if type(number) not in (int, str) or (isinstance(number, str) and (not number.isascii() or not number.isdecimal())) or not 0 <= int(number) < 2 ** 63:
                raise ValueError("invalid rejected count")
            rejected += int(number)
        return ("partial", "receiver_partial_success") if rejected else ("accepted", None)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return "failed", "invalid_response"


def _delay(response, config, attempt, jitter):
    if response:
        value = next((v for k, v in response.headers.items() if k.lower() == "retry-after"), None)
        if value is not None:
            try:
                delay = float(value)
            except (TypeError, ValueError):
                try:
                    delay = parsedate_to_datetime(value).timestamp() - time.time()
                except (TypeError, ValueError, OverflowError):
                    delay = 0
            return max(0, delay)
    return min(config.max_backoff_seconds, config.backoff_seconds * 2 ** attempt * (1 + max(0, min(1, jitter()))))


def export_otlp(bundle: TelemetryBundle, config: ExportConfig, store: SQLiteReplayStore, *,
                transport=http_transport, sleep=time.sleep, clock=time.monotonic, jitter=random.random) -> ExportResult:
    """Return an observation-delivery result; never raise network/store failures.

    `ci_conclusion` is copied from evidence, regardless of export outcome. Injected
    transports must honor the supplied timeout; no background worker outlives this
    call. Consumer code decides when to call this optional post-run operation.
    """
    attempts, acknowledged, total = 0, 0, 0
    claimed, key, owner = False, None, uuid.uuid4().hex
    deadline = clock() + config.total_timeout_seconds

    def result(status, reason=None):
        return ExportResult(status, reason, attempts, acknowledged, total, bundle.ci_conclusion)

    try:
        try:
            batches = build_batches(bundle, config)
        except ValueError:
            return result("failed", "payload_limit")
        total = len(batches)
        key = hashlib.sha256((bundle.identity.key + ":" + config.endpoint.rstrip("/")).encode()).hexdigest()
        plan = hashlib.sha256(":".join(batch.key for batch in batches).encode()).hexdigest()
        claim = store.claim(key, plan, owner, config.total_timeout_seconds + 5)
        if claim == "complete":
            acknowledged = total
            return result("duplicate")
        if claim == "partial":
            return result("partial", "receiver_partial_success")
        if claim != "claimed":
            return result("busy" if claim == "busy" else "failed", "replay_" + claim)
        claimed = True
        headers = dict(config.headers)
        headers.update({"Content-Type": "application/json", "Accept": "application/json"})
        for batch in batches:
            if store.batch_state(key, batch.key) == "accepted":
                acknowledged += 1
                continue
            if store.batch_state(key, batch.key) == "partial":
                store.finish(key, owner, "partial")
                return result("partial", "receiver_partial_success")
            for attempt in range(config.max_attempts):
                remaining = deadline - clock()
                if remaining <= 0:
                    return result("failed", "deadline_exceeded")
                response = None
                attempts += 1
                try:
                    response = transport(config.endpoint.rstrip("/") + "/v1/" + batch.signal, batch.body, headers, min(config.timeout_seconds, remaining))
                    state, reason = _response(response)
                except (TimeoutError, OSError):
                    state, reason = "retry", "transport_error"
                except Exception:
                    state, reason = "failed", "transport_error"
                if state == "accepted":
                    store.record_batch(key, batch.key, owner, "accepted")
                    acknowledged += 1
                    break
                if state == "partial":
                    store.record_batch(key, batch.key, owner, "partial")
                    store.finish(key, owner, "partial")
                    return result("partial", reason)
                if deadline <= clock():
                    return result("failed", "deadline_exceeded")
                if state != "retry" or attempt + 1 == config.max_attempts:
                    return result("failed", reason)
                delay = _delay(response, config, attempt, jitter)
                if delay > config.max_backoff_seconds or delay >= deadline - clock():
                    return result("failed", "retry_delay_limit")
                sleep(delay)
        store.finish(key, owner, "complete")
        claimed = False
        return result("exported")
    except Exception:
        return result("failed", "export_state_error")
    finally:
        if claimed:
            try:
                store.finish(key, owner, "failed")
            except Exception:
                pass  # The lease expires; never mask the non-blocking result.
