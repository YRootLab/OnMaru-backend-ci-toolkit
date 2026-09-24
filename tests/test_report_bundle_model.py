import json

import pytest

from pipeline_toolkit.report_bundle import (
    ReportBundleValidationError,
    is_performance_eligible,
    load_report_bundle,
)


def test_load_report_bundle_accepts_success_and_non_comparable_facts(tmp_path):
    source = tmp_path / "facts.json"
    source.write_text(json.dumps({
        "title": "CI observation", "observed_at": "2026-09-24", "summary": "Measured CI.",
        "facts": [{"name": "serial", "value": 454, "unit": "seconds", "status": "success",
                   "source_url": "https://github.com/org/repo/actions/runs/1", "comparable": False}],
        "limitations": ["same SHA samples are missing"], "next_steps": ["collect three samples"]
    }), encoding="utf-8")

    result = load_report_bundle(source)

    assert result.facts[0].value == 454
    assert not is_performance_eligible(result.facts[0])


def test_load_report_bundle_rejects_credential_url_and_failed_improvement_claim(tmp_path):
    source = tmp_path / "unsafe.json"
    source.write_text(json.dumps({"title": "x", "observed_at": "2026-09-24", "summary": "x",
        "facts": [{"name": "x", "value": 1, "unit": "seconds", "status": "failed",
                   "source_url": "https://token@example.test/run", "comparable": True}],
        "limitations": ["x"], "next_steps": ["x"]}), encoding="utf-8")

    with pytest.raises(ReportBundleValidationError):
        load_report_bundle(source)


@pytest.mark.parametrize("payload", [
    {"title": "x", "observed_at": "2026-09-24", "summary": "x", "facts": [], "limitations": [], "next_steps": []},
    {"title": "x", "observed_at": "2026/09/24", "summary": "x", "facts": [], "limitations": ["x"], "next_steps": ["x"]},
])
def test_load_report_bundle_rejects_missing_required_content_and_invalid_date(tmp_path, payload):
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReportBundleValidationError):
        load_report_bundle(source)


@pytest.mark.parametrize("fact", [
    {"name": "x", "value": float("nan"), "unit": "seconds", "status": "success", "source_url": "https://example.test/run", "comparable": True},
    {"name": "x", "value": 1, "unit": "seconds", "status": "unknown", "source_url": "https://example.test/run", "comparable": True},
    {"name": "x", "value": 1, "unit": "seconds", "status": "success", "source_url": "http://example.test/run", "comparable": True},
])
def test_load_report_bundle_rejects_invalid_fact_values(tmp_path, fact):
    source = tmp_path / "invalid-fact.json"
    source.write_text(json.dumps({"title": "x", "observed_at": "2026-09-24", "summary": "x",
        "facts": [fact], "limitations": ["x"], "next_steps": ["x"]}), encoding="utf-8")

    with pytest.raises(ReportBundleValidationError):
        load_report_bundle(source)


def test_load_report_bundle_rejects_secret_like_keys_recursively(tmp_path):
    source = tmp_path / "secret.json"
    source.write_text(json.dumps({"title": "x", "observed_at": "2026-09-24", "summary": "x",
        "facts": [{"name": "x", "value": 1, "unit": "seconds", "status": "success",
                   "source_url": "https://example.test/run", "comparable": True,
                   "metadata": {"api_token": "do-not-store"}}],
        "limitations": ["x"], "next_steps": ["x"]}), encoding="utf-8")

    with pytest.raises(ReportBundleValidationError):
        load_report_bundle(source)


@pytest.mark.parametrize("status", ["failed", "cancelled", "timeout", "missing"])
def test_only_successful_comparable_facts_are_performance_eligible(tmp_path, status):
    source = tmp_path / "ineligible.json"
    source.write_text(json.dumps({"title": "x", "observed_at": "2026-09-24", "summary": "x",
        "facts": [{"name": "x", "value": 1, "unit": "seconds", "status": status,
                   "source_url": "https://example.test/run", "comparable": True}],
        "limitations": ["x"], "next_steps": ["x"]}), encoding="utf-8")

    assert not is_performance_eligible(load_report_bundle(source).facts[0])
