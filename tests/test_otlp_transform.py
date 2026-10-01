"""Source-derived assertions: no exporter helper computes expected timings."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from pipeline_toolkit.telemetry.timeline import normalize_actions_timeline


def api():
    from pipeline_toolkit import telemetry
    assert hasattr(telemetry, "transform_actions_evidence"), "Actions OTLP transformation is missing"
    return telemetry


def source():
    raw = json.loads(Path("tests/fixtures/github-actions/attempt-failure.json").read_text())
    return normalize_actions_timeline(raw["run"], raw["jobs"], toolkit_ref="b" * 40,
        expected_modules={"api": 701, "worker": 702},
        module_artifacts=[{"id": 91, "data": json.dumps(raw["module"]).encode()}])


def policy():
    return api().MetricPolicy(workflow="ci", environment="test", jobs={701: "api", 702: "worker"}, modules=("api", "worker"))


def transformed(evidence=None):
    return api().transform_actions_evidence(source() if evidence is None else evidence, policy(), observed_at_ns=1790812810000000000)


def reseal(evidence):
    evidence.pop("evidence_digest", None)
    evidence["evidence_digest"] = "sha256:" + hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return evidence


def test_workflow_job_step_spans_preserve_source_timing_and_results():
    bundle = transformed()
    spans = {span.attributes["toolkit.ci.scope"]: span for span in bundle.spans}
    assert set(spans) == {"workflow", "job", "step"}  # cancelled worker lacks a valid interval
    assert (spans["workflow"].start_ns, spans["workflow"].end_ns) == (1790812801000000000, 1790812809000000000)
    assert (spans["job"].start_ns, spans["job"].end_ns) == (1790812801000000000, 1790812809000000000)
    assert (spans["step"].start_ns, spans["step"].end_ns) == (1790812802000000000, 1790812808000000000)
    assert spans["job"].parent_span_id == spans["workflow"].span_id
    assert spans["step"].parent_span_id == spans["job"].span_id
    assert spans["workflow"].attributes["cicd.pipeline.result"] == "cancellation"
    assert spans["workflow"].attributes["toolkit.ci.timing"] == "observed_job_window"
    assert spans["job"].attributes["cicd.pipeline.task.run.result"] == "failure"
    assert spans["step"].status_code == 2
    assert spans["step"].attributes["toolkit.ci.source_conclusion"] == "failure"
    assert "job:702:timestamp_unavailable" in bundle.issues
    assert "step:702:1:timestamp_invalid" in bundle.issues
    assert len({s.trace_id for s in bundle.spans}) == 1
    assert all(len(s.trace_id) == 32 and len(s.span_id) == 16 for s in bundle.spans)


def test_metrics_include_durations_work_outcomes_and_explicit_missing_quality():
    bundle = transformed()
    by_name = {}
    for metric in bundle.metrics:
        by_name.setdefault(metric.name, []).append(metric)
    assert by_name["toolkit_ci_workflow_observed_window_seconds"][0].values == (8.0,)
    assert by_name["toolkit_ci_job_duration_seconds"][0].values == (8.0,)
    assert by_name["toolkit_ci_step_duration_seconds"][0].values == (6.0,)
    assert by_name["toolkit_ci_module_duration_seconds"][0].values == (6.0,)
    work = {m.labels["scope"]: m.values for m in by_name["toolkit_ci_work_seconds"]}
    assert work == {"job": (8.0,), "module": (6.0,)}
    assert any(m.labels["scope"] == "workflow" and m.labels["outcome"] == "cancellation" for m in by_name["toolkit_ci_outcome"])
    assert any(m.labels["scope"] == "artifact" and m.labels["quality"] == "partial" for m in by_name["toolkit_ci_collection_quality"])
    assert "toolkit_ci_workflow_duration_seconds" not in by_name
    assert not any("critical" in name or "queue_seconds" in name for name in by_name)


def test_identity_is_trace_only_and_replay_key_distinguishes_attempt_and_digest():
    evidence = source()
    first = transformed(evidence)
    assert first.identity.repository == "example/backend"
    assert first.identity.run_id == 42 and first.identity.attempt == 2
    assert first.identity.manifest_digest == evidence["evidence_digest"]
    assert first.identity.key == transformed(evidence).identity.key
    for span in first.spans:
        assert span.attributes["toolkit.ci.manifest.digest"] == evidence["evidence_digest"]
        assert span.attributes["cicd.pipeline.run.id"] == "42"
        assert span.attributes["toolkit.ci.run.attempt"] == 2
    metric_text = json.dumps([dict(m.labels) for m in first.metrics])
    for forbidden in ("example/backend", "https://", "a" * 40, "b" * 40, evidence["evidence_digest"], "Run API tests"):
        assert forbidden not in metric_text
    evidence["identity"]["run_attempt"] = evidence["run"]["attempt"] = 3
    assert first.identity.key != transformed(reseal(evidence)).identity.key


def test_untrusted_job_names_never_become_metric_labels_and_undeclared_modules_are_other():
    evidence = source()
    evidence["jobs"][0]["name"] = "tests/private/account.py " + "d" * 40
    evidence["modules"][0]["module_id"] = "user-secret"
    bundle = api().transform_actions_evidence(reseal(evidence), api().MetricPolicy("ci", "test"), observed_at_ns=1790812810000000000)
    assert all(m.labels.get("job", "other") == "other" for m in bundle.metrics)
    assert all(m.labels.get("module", "other") == "other" for m in bundle.metrics)
    assert "user-secret" not in json.dumps([dict(m.labels) for m in bundle.metrics])


@pytest.mark.parametrize("labels", [{"run_id": "42"}, {"sha": "a" * 40}, {"test_name": "test_api"}, {"path": "src/a"}, {"url": "https://example.com"}])
def test_typed_metric_rejects_high_cardinality_label_keys(labels):
    telemetry = api()
    with pytest.raises(ValueError, match="label"):
        telemetry.MetricPoint("toolkit_ci_work_seconds", "s", (1.0,), labels, 1, "gauge")


def test_missing_all_timestamps_emits_no_spans_and_retains_quality_metrics():
    raw = json.loads(Path("tests/fixtures/github-actions/attempt-failure.json").read_text())
    for job in raw["jobs"]["jobs"]:
        job["started_at"] = job["completed_at"] = None
        for step in job["steps"]:
            step["started_at"] = step["completed_at"] = None
    evidence = normalize_actions_timeline(raw["run"], raw["jobs"], toolkit_ref="b" * 40, expected_modules={"api": 701}, module_artifacts=[])
    bundle = transformed(evidence)
    assert not bundle.spans
    assert not any("duration" in m.name or "observed_window" in m.name for m in bundle.metrics)
    assert any(m.labels.get("quality") == "missing" for m in bundle.metrics)
    assert bundle.ci_conclusion == "cancelled"


def test_tampered_digest_and_unsupported_schema_fail_before_transformation():
    evidence = source()
    evidence["jobs"][0]["duration_seconds"] = 900
    with pytest.raises(ValueError, match="digest"):
        transformed(evidence)
    evidence = source()
    evidence["schema_version"] = 2
    with pytest.raises(ValueError, match="schema"):
        transformed(reseal(evidence))


def test_fractional_source_and_offset_timestamps_are_not_rounded_for_spans():
    raw = json.loads(Path("tests/fixtures/github-actions/attempt-failure.json").read_text())
    raw["jobs"] = {"total_count": 1, "jobs": [dict(raw["jobs"]["jobs"][0],
        started_at="2026-10-01T01:00:01.123456+01:00", completed_at="2026-10-01T00:00:09.123456Z", steps=[])]}
    evidence = normalize_actions_timeline(raw["run"], raw["jobs"])
    bundle = transformed(evidence)
    assert {(s.start_ns, s.end_ns) for s in bundle.spans} == {(1790812801123456000, 1790812809123456000)}


@pytest.mark.parametrize("mutation", ["job_duration", "step_duration", "work", "window", "duplicate_job", "duplicate_step", "module_job", "invalid_interval"])
def test_resealed_but_inconsistent_evidence_is_rejected(mutation):
    evidence = source()
    if mutation == "job_duration":
        evidence["jobs"][0]["duration_seconds"] = 100
    elif mutation == "step_duration":
        evidence["jobs"][0]["steps"][0]["duration_seconds"] = 100
    elif mutation == "work":
        evidence["metrics"]["sum_job_work_seconds"] = 100
    elif mutation == "window":
        evidence["metrics"]["observed_job_window_seconds"] = 100
    elif mutation == "duplicate_job":
        evidence["jobs"].append(copy.deepcopy(evidence["jobs"][0]))
    elif mutation == "duplicate_step":
        evidence["jobs"][0]["steps"].append(copy.deepcopy(evidence["jobs"][0]["steps"][0]))
    elif mutation == "module_job":
        evidence["modules"][0]["job_id"] = 999
    else:
        evidence["jobs"][0]["started_at"] = "not-a-timestamp"
    with pytest.raises(ValueError, match="evidence"):
        transformed(reseal(evidence))


def test_observed_step_with_missing_job_timestamps_remains_an_unparented_span():
    raw = json.loads(Path("tests/fixtures/github-actions/attempt-failure.json").read_text())
    raw["jobs"] = {"total_count": 1, "jobs": [dict(raw["jobs"]["jobs"][0], started_at=None, completed_at=None)]}
    bundle = transformed(normalize_actions_timeline(raw["run"], raw["jobs"]))
    assert len(bundle.spans) == 1
    assert bundle.spans[0].parent_span_id is None
    assert (bundle.spans[0].start_ns, bundle.spans[0].end_ns) == (1790812802000000000, 1790812808000000000)


def test_jobs_with_same_catalog_label_are_one_histogram_with_both_samples():
    raw = json.loads(Path("tests/fixtures/github-actions/attempt-failure.json").read_text())
    raw["jobs"]["jobs"][1] = dict(raw["jobs"]["jobs"][0], id=702, completed_at="2026-10-01T00:00:11Z", steps=[])
    evidence = normalize_actions_timeline(raw["run"], raw["jobs"])
    bundle = api().transform_actions_evidence(evidence, api().MetricPolicy("ci", "test", jobs={701: "test", 702: "test"}), observed_at_ns=1790812820000000000)
    duration = [m for m in bundle.metrics if m.name == "toolkit_ci_job_duration_seconds"]
    assert len(duration) == 1 and duration[0].values == (8.0, 10.0)


def test_model_rejects_invalid_span_identity_and_freezes_metric_labels():
    telemetry = api()
    with pytest.raises(ValueError, match="span"):
        telemetry.SpanRecord("job", "not-hex", "bad", None, 1, 2, {}, 1)
    labels = {"scope": "job"}
    point = telemetry.MetricPoint("toolkit_ci_work_seconds", "s", (1,), labels, 1, "gauge")
    labels["run_id"] = "42"
    assert "run_id" not in point.labels
    with pytest.raises(TypeError):
        point.labels["run_id"] = "42"


def test_reconstructed_task_links_are_source_correlated_and_never_metric_labels():
    spans = transformed().spans
    task = next(span for span in spans if span.attributes["toolkit.ci.scope"] == "job")
    assert task.attributes["cicd.pipeline.task.run.url.full"] == "https://github.com/example/backend/actions/runs/42/job/701"
    step = next(span for span in spans if span.attributes["toolkit.ci.scope"] == "step")
    assert step.attributes["cicd.pipeline.task.run.url.full"] == "https://github.com/example/backend/actions/runs/42/job/701#step:1:1"
