import json
from copy import deepcopy
from pathlib import Path

import pytest

from pipeline_toolkit.contracts.module_evidence import (
    EnvironmentIdentity,
    ModuleBenchmarkEvidence,
    ResourceUsage,
    RunProvenance,
    validate_module_evidence,
)
from pipeline_toolkit.contracts.performance_evidence import (
    LAYER_NAMES,
    LAYER_STATES,
    MAX_PAYLOAD_BYTES,
    QUALITY_LEVELS,
    REQUIRED_KEYS,
    SCHEMA_ID,
    TIMING_NAMES,
    PerformanceEvidenceError,
    dumps_envelope,
    parse_envelope_text,
    read_envelope_file,
    read_legacy_module_record,
    to_legacy_module_record,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "performance-evidence"
SCHEMA_FILE = ROOT / "schemas" / "ci-performance-evidence-1.0.json"


def _fixture_text(name):
    return (FIXTURES / name).read_text()


def _valid_document():
    return json.loads(_fixture_text("valid.json"))


def _layers(document):
    return document["cache"]["cacheIdentity"]["layers"]


# ---------------------------------------------------------------------------
# Deterministic reads of the canonical fixtures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name", ["valid.json", "partial.json", "unavailable.json", "mixed-cache.json", "legacy.json"]
)
def test_fixture_reads_deterministically_and_rewrites_byte_identically(name):
    text = _fixture_text(name)

    first = parse_envelope_text(text)
    second = read_envelope_file(FIXTURES / name)

    assert first == second
    assert dumps_envelope(first) == text


def test_valid_fixture_has_complete_quality_and_counts():
    document = _valid_document()

    assert document["schema"] == SCHEMA_ID
    assert document["quality"] == "complete"
    assert document["execution"] == {"executed_now": 120, "verified_from_cache": 380}
    assert document["selected"]["count"] == 500
    assert document["test_universe"]["size"] == 1200
    assert "legacy" not in document


def test_partial_fixture_keeps_unmeasured_values_as_none_not_zero():
    document = json.loads(_fixture_text("partial.json"))

    assert document["quality"] == "partial"
    assert document["timings_ms"]["context_init"] is None
    assert document["timings_ms"]["container_prepare"] is None
    assert document["timings_ms"]["flyway"] == 1900.0
    assert document["execution"]["verified_from_cache"] is None
    assert _layers(document)["build"] == {"state": "partial"}
    assert _layers(document)["configuration"] == {"state": "unknown"}


def test_unavailable_fixture_carries_no_measured_values():
    document = json.loads(_fixture_text("unavailable.json"))

    assert document["quality"] == "unavailable"
    assert all(value is None for value in document["timings_ms"].values())
    assert document["selected"] == {"digest": None, "count": None}
    assert document["execution"] == {"executed_now": None, "verified_from_cache": None}
    assert _layers(document) == {}


def test_mixed_cache_dependency_warm_build_cold_configuration_disabled_is_preserved():
    document = read_envelope_file(FIXTURES / "mixed-cache.json")

    layers = _layers(document)
    assert layers["dependency"] == {"state": "warm"}
    assert layers["build"] == {"state": "cold"}
    assert layers["configuration"] == {"state": "disabled"}
    assert document["cache"]["cacheIdentity"]["seedProvenance"]["seeded"] is True


def test_zero_and_missing_timing_values_are_distinct():
    text = _fixture_text("valid.json")
    document = json.loads(text)
    document["timings_ms"]["tests"] = 0
    assert parse_envelope_text(dumps_envelope(document))["timings_ms"]["tests"] == 0

    document["timings_ms"]["tests"] = None
    assert parse_envelope_text(dumps_envelope(document))["timings_ms"]["tests"] is None


# ---------------------------------------------------------------------------
# Legacy cache_state handling
# ---------------------------------------------------------------------------

def test_legacy_fixture_preserves_cache_state_as_legacy_limited_without_layers():
    document = read_envelope_file(FIXTURES / "legacy.json")

    assert document["quality"] == "legacy-limited"
    assert document["legacy"] == {"cache_state": "warm"}
    assert "cache" not in document


@pytest.mark.parametrize(
    "cache_state",
    ["warm", "cold", "partial", "disabled", "mixed", "dependency=warm;build=cold", "unknown"],
)
def test_legacy_cache_strings_never_produce_per_layer_states(cache_state):
    record = json.loads(_fixture_text("legacy-module-record.json"))
    record["environment_identity"]["cache_state"] = cache_state

    document = read_legacy_module_record(record)

    assert document["legacy"] == {"cache_state": cache_state}
    assert "cache" not in document
    assert document["quality"] == "legacy-limited"


def test_legacy_adapter_reads_legacy_module_record_to_expected_envelope():
    record = json.loads(_fixture_text("legacy-module-record.json"))

    assert read_legacy_module_record(record) == json.loads(_fixture_text("legacy.json"))


def test_legacy_document_with_cache_identity_is_rejected():
    document = json.loads(_fixture_text("legacy.json"))
    document["cache"] = _valid_document()["cache"]

    with pytest.raises(PerformanceEvidenceError, match="forbidden keys: cache"):
        parse_envelope_text(json.dumps(document))


def test_new_document_carrying_legacy_block_is_rejected():
    document = _valid_document()
    document["legacy"] = {"cache_state": "warm"}

    with pytest.raises(PerformanceEvidenceError, match="forbidden keys: legacy"):
        parse_envelope_text(json.dumps(document))


# ---------------------------------------------------------------------------
# New writer and legacy reader round trip
# ---------------------------------------------------------------------------

def test_new_writer_output_projects_to_the_checked_in_legacy_record():
    projection = to_legacy_module_record(_valid_document())

    assert projection == json.loads(_fixture_text("roundtrip-legacy-projection.json"))
    assert projection["environment_identity"]["cache_state"] == (
        "dependency=warm;build=cold;configuration=disabled"
    )


def test_new_writer_round_trip_is_read_by_legacy_reader_and_module_evidence_contract():
    projection = json.loads(_fixture_text("roundtrip-legacy-projection.json"))

    legacy = read_legacy_module_record(projection)

    assert legacy["quality"] == "legacy-limited"
    assert legacy["legacy"]["cache_state"] == "dependency=warm;build=cold;configuration=disabled"
    assert "cache" not in legacy

    identity = projection["environment_identity"]
    evidence = ModuleBenchmarkEvidence(
        module_id="ci-performance",
        run_id=projection["run_id"],
        metric_name="wall_clock_seconds",
        metric_value=91.0,
        unit="seconds",
        resource=ResourceUsage(),
        provenance=RunProvenance(**projection["provenance"]),
        artifact_uri="artifact://github-actions/24712345678/ci-performance-evidence.json",
        environment_identity=EnvironmentIdentity(**identity),
    )
    validate_module_evidence(evidence)


def test_module_evidence_record_is_rejected_by_performance_namespace():
    module_record = json.loads(_fixture_text("legacy-module-record.json"))

    with pytest.raises(PerformanceEvidenceError, match="schema: must equal ci-performance-evidence/1.0"):
        parse_envelope_text(json.dumps(module_record))


def test_other_schema_identifiers_are_rejected():
    document = _valid_document()
    document["schema"] = "evidence-1.0"

    with pytest.raises(PerformanceEvidenceError, match="schema: must equal"):
        parse_envelope_text(json.dumps(document))


# ---------------------------------------------------------------------------
# Rejections: NaN, negative, duplicate keys, oversize, invalid identity
# ---------------------------------------------------------------------------

def test_nan_fixture_is_rejected():
    with pytest.raises(PerformanceEvidenceError, match="non-finite JSON constant"):
        read_envelope_file(FIXTURES / "invalid-nan.json")


def test_infinite_number_is_rejected_even_without_nan_token():
    text = _fixture_text("valid.json").replace('"tests": 91000.0', '"tests": 1e999')

    with pytest.raises(PerformanceEvidenceError, match="must be finite"):
        parse_envelope_text(text)


def test_negative_fixture_is_rejected():
    with pytest.raises(PerformanceEvidenceError, match="must be non-negative"):
        read_envelope_file(FIXTURES / "invalid-negative.json")


def test_negative_count_is_rejected():
    document = _valid_document()
    document["execution"]["executed_now"] = -1

    with pytest.raises(PerformanceEvidenceError, match="non-negative integer"):
        parse_envelope_text(json.dumps(document))


def test_duplicate_key_fixture_is_rejected():
    with pytest.raises(PerformanceEvidenceError, match="duplicate key: quality"):
        read_envelope_file(FIXTURES / "invalid-duplicate-key.json")


def test_duplicate_nested_key_is_rejected():
    text = _fixture_text("valid.json").replace(
        '"tests": 91000.0', '"tests": 91000.0, "tests": 1.0'
    )

    with pytest.raises(PerformanceEvidenceError, match="duplicate key: tests"):
        parse_envelope_text(text)


def test_oversize_payload_is_rejected_before_decoding(tmp_path):
    padded = _fixture_text("valid.json")
    padded = padded[:-2] + ",\n  \"padding\": \"" + "x" * MAX_PAYLOAD_BYTES + "\"\n}\n"
    assert len(padded.encode("utf-8")) > MAX_PAYLOAD_BYTES

    with pytest.raises(PerformanceEvidenceError, match="exceeds"):
        parse_envelope_text(padded)

    path = tmp_path / "oversize.json"
    path.write_text(padded)
    with pytest.raises(PerformanceEvidenceError, match="exceeds"):
        read_envelope_file(path)


def test_full_size_valid_envelope_under_limit_is_accepted():
    document = _valid_document()
    for index in range(16 - len(document["toolchain"])):
        document["toolchain"][f"extra_{index:02d}"] = "x" * 128
    text = dumps_envelope(document)

    assert len(text.encode("utf-8")) < MAX_PAYLOAD_BYTES
    assert parse_envelope_text(text) == document


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d["source"].update(commit_sha="ABC123"), "invalid identity value"),
        (lambda d: d["source"].update(commit_sha="a" * 39), "invalid identity value"),
        (lambda d: d["source"].update(repository="no-owner-slash"), "invalid identity value"),
        (lambda d: d["source"].update(repository="owner/name/extra"), "invalid identity value"),
        (lambda d: d["source"].update(workflow_run_id="run id with spaces"), "invalid identity value"),
        (lambda d: d["source"].update(run_attempt=0), "integer >= 1"),
        (lambda d: d["source"].update(run_attempt=True), "integer >= 1"),
        (lambda d: d["source"].update(run_attempt=None), "is required unless"),
        (lambda d: d["clock"].update(utc_anchor="2026-11-20 03:00:00"), "invalid identity value"),
        (lambda d: d["selected"].update(digest="sha256:ABC"), "invalid identity value"),
        (lambda d: d["producer"].update(name=""), "bounded string"),
        (lambda d: d["toolchain"].pop("runner_image"), "missing key: runner_image"),
        (lambda d: d["toolchain"].update({"Bad-Key": "x"}), "invalid key"),
        (lambda d: d["cache"]["cacheIdentity"]["layers"].update(container={"state": "warm"}),
         "unknown layer"),
        (lambda d: d["cache"]["cacheIdentity"]["layers"]["build"].update(state="hot"),
         "must be one of"),
        (lambda d: d["cache"].update(experiment_class="ad-hoc"), "must be one of"),
    ],
)
def test_invalid_identity_and_fields_are_rejected(mutate, message):
    document = _valid_document()
    mutate(document)

    with pytest.raises(PerformanceEvidenceError, match=message):
        parse_envelope_text(json.dumps(document))


def test_invalid_identity_fixture_is_rejected():
    with pytest.raises(PerformanceEvidenceError, match="invalid identity value"):
        read_envelope_file(FIXTURES / "invalid-identity.json")


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d["execution"].update(executed_now=900), "must not exceed selected.count"),
        (lambda d: d["selected"].update(count=1300), "must not exceed test_universe.size"),
        (lambda d: d["timings_ms"].update(mystery=1.0), "unknown timing"),
        (lambda d: d.update(extra=True), "unknown or forbidden keys: extra"),
        (lambda d: d.update(quality="great"), "quality: must be one of"),
    ],
)
def test_invariant_and_unknown_field_violations_are_rejected(mutate, message):
    document = _valid_document()
    mutate(document)

    with pytest.raises(PerformanceEvidenceError, match=message):
        parse_envelope_text(json.dumps(document))


def test_complete_quality_requires_counts_and_digests():
    document = _valid_document()
    document["execution"]["verified_from_cache"] = None

    with pytest.raises(PerformanceEvidenceError, match="complete requires"):
        parse_envelope_text(json.dumps(document))


def test_unavailable_quality_must_not_carry_measured_counts():
    document = json.loads(_fixture_text("unavailable.json"))
    document["execution"]["executed_now"] = 5

    with pytest.raises(PerformanceEvidenceError, match="unavailable must not carry"):
        parse_envelope_text(json.dumps(document))


def test_writer_refuses_non_finite_or_negative_values():
    document = _valid_document()
    document["timings_ms"]["tests"] = float("nan")

    with pytest.raises(PerformanceEvidenceError):
        dumps_envelope(document)


def test_writer_serializes_missing_values_as_null_never_zero():
    document = json.loads(_fixture_text("unavailable.json"))

    text = dumps_envelope(document)

    assert '"executed_now": null' in text
    assert '"gradle_task": null' in text
    assert '"executed_now": 0' not in text


def test_writer_output_is_deterministic():
    document = _valid_document()

    assert dumps_envelope(document) == dumps_envelope(deepcopy(document))


# ---------------------------------------------------------------------------
# Schema file stays in step with the reader constants
# ---------------------------------------------------------------------------

def test_json_schema_file_matches_reader_constants():
    schema = json.loads(SCHEMA_FILE.read_text())

    assert schema["$id"].endswith("ci-performance-evidence-1.0.json")
    assert schema["properties"]["schema"] == {"const": SCHEMA_ID}
    assert schema["properties"]["quality"]["enum"] == list(QUALITY_LEVELS)
    assert set(schema["required"]) == set(REQUIRED_KEYS)
    assert schema["$defs"]["layer"]["properties"]["state"]["enum"] == list(LAYER_STATES)
    assert set(schema["properties"]["cache"]["properties"]["cacheIdentity"]["properties"]["layers"]["properties"]) == set(LAYER_NAMES)
    assert set(schema["properties"]["timings_ms"]["properties"]) == set(TIMING_NAMES)


@pytest.mark.parametrize(
    "name", ["valid.json", "partial.json", "unavailable.json", "mixed-cache.json", "legacy.json"]
)
def test_schema_declares_every_key_used_by_good_fixtures(name):
    schema = json.loads(SCHEMA_FILE.read_text())
    document = json.loads(_fixture_text(name))

    assert set(document) <= set(schema["properties"])
