import json
import pytest
from pipeline_toolkit.telemetry import TelemetryEvent, serialize_event

def test_telemetry_event_carries_run_comparison_trace_and_low_cardinality_labels():
    event = TelemetryEvent("toolkit_collection_duration_seconds", 1.25, {"collector": "junit", "status": "success"}, "run-1", "comparison-1", "trace-1")
    document = json.loads(serialize_event(event))
    assert document["run_id"] == "run-1"
    assert document["comparison_id"] == "comparison-1"
    assert document["trace_id"] == "trace-1"
    assert document["labels"] == {"collector": "junit", "status": "success"}

def test_high_cardinality_labels_are_rejected():
    with pytest.raises(ValueError, match="label is not allowed"):
        TelemetryEvent("toolkit_collection_duration_seconds", 1, {"commit_sha": "abc"}, "run-1")

def test_structured_event_redacts_secrets_and_is_deterministic():
    event = TelemetryEvent("toolkit_collection_failures_total", 1, {"reason": "token=secret"}, "run-1", attributes={"authorization": "secret"})
    first = serialize_event(event)
    assert first == serialize_event(event)
    assert "secret" not in first
    assert "[REDACTED]" in first
