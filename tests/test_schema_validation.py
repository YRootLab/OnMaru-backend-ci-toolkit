import json
import pytest
from pipeline_toolkit.contracts.schema import migrate_document, validate_document

def test_versioned_evidence_fixture_round_trips_against_schema():
    document = json.loads(open("tests/fixtures/schemas/evidence.json").read())
    assert validate_document(document, "schemas/evidence-1.0.json") == []

def test_schema_validation_reports_version_and_required_field_errors():
    errors = validate_document({"schema_version": "9.0"}, "schemas/evidence-1.0.json")
    assert "schema_version must equal 1.0" in errors
    assert any(error.startswith("missing required field:") for error in errors)

def test_legacy_evidence_migrates_deterministically_to_current_schema():
    migrated = migrate_document({"schema_version": "0.9", "benchmark_id": "x", "status": "success", "value": 1, "unit": "seconds", "source": "fixture"})
    assert migrated["schema_version"] == "1.0"
    assert migrated["quality"] == "success"
    assert validate_document(migrated, "schemas/evidence-1.0.json") == []

def test_invalid_json_schema_path_is_explicit():
    with pytest.raises(FileNotFoundError):
        validate_document({}, "schemas/does-not-exist.json")
