"""CI performance evidence envelope ``ci-performance-evidence/1.0``.

This namespace is separate from the module benchmark evidence contract in
``module_evidence``. Missing measurements are ``None`` and are never coerced to
zero. Legacy ``cache_state`` strings are preserved verbatim with quality
``legacy-limited`` and are never parsed into per-layer cache states.
"""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

SCHEMA_ID = "ci-performance-evidence/1.0"
MAX_PAYLOAD_BYTES = 64 * 1024

QUALITY_LEVELS = ("complete", "partial", "unavailable", "legacy-limited")
EXPERIMENT_CLASSES = ("controlled-cold", "controlled-warm", "realistic-pr", "unknown")
LAYER_NAMES = ("dependency", "build", "configuration")
LAYER_STATES = ("disabled", "cold", "warm", "partial", "invalidated", "unknown")
TIMING_NAMES = ("gradle_task", "context_init", "container_prepare", "flyway", "tests")

TOP_LEVEL_KEYS = frozenset(
    {"schema", "source", "producer", "toolchain", "clock", "quality", "timings_ms",
     "test_universe", "selected", "execution", "cache", "legacy"}
)
REQUIRED_KEYS = frozenset(
    {"schema", "source", "producer", "toolchain", "clock", "quality",
     "test_universe", "selected", "execution"}
)
TOOLCHAIN_REQUIRED = ("runner_image", "java_version", "python_version")

_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_RUN_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_UTC_ANCHOR = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z")
_TOOL_KEY = re.compile(r"[a-z_][a-z0-9_]{0,63}")


class PerformanceEvidenceError(ValueError):
    """Raised for any payload that violates the ci-performance-evidence/1.0 contract."""


# ---------------------------------------------------------------------------
# Strict parsing
# ---------------------------------------------------------------------------

def _reject_duplicate_keys(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PerformanceEvidenceError(f"duplicate key: {key}")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    raise PerformanceEvidenceError(f"non-finite JSON constant is not allowed: {name}")


def parse_envelope_text(text: str) -> Dict[str, Any]:
    """Strictly parse and validate an envelope from JSON text."""
    if not isinstance(text, str):
        raise PerformanceEvidenceError("payload must be text")
    if len(text.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise PerformanceEvidenceError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise PerformanceEvidenceError(f"invalid JSON: {exc}") from exc
    return validate_envelope(document)


def read_envelope_file(path: Any) -> Dict[str, Any]:
    """Read a file with a size bound enforced before decoding."""
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_PAYLOAD_BYTES + 1)
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise PerformanceEvidenceError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PerformanceEvidenceError("payload must be UTF-8") from exc
    return parse_envelope_text(text)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _fail(path: str, message: str) -> PerformanceEvidenceError:
    return PerformanceEvidenceError(f"{path}: {message}")


def _mapping(value: Any, path: str, required: Iterable[str], allowed: Iterable[str]) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(path, "must be an object")
    allowed_set = set(allowed) | set(required)
    unknown = sorted(set(value) - allowed_set)
    if unknown:
        raise _fail(path, f"unknown or forbidden keys: {', '.join(unknown)}")
    missing = sorted(set(required) - set(value))
    if missing:
        raise _fail(path, f"missing keys: {', '.join(missing)}")
    return value


def _legacy_fields(value: Any, path: str, required: Iterable[str]) -> Dict[str, Any]:
    """Legacy records may carry extra fields; the adapter only requires presence of these."""
    if not isinstance(value, dict):
        raise _fail(path, "must be an object")
    missing = sorted(set(required) - set(value))
    if missing:
        raise _fail(path, f"missing keys: {', '.join(missing)}")
    return value


def _text(value: Any, path: str, pattern: re.Pattern, max_length: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise _fail(path, "must be a non-empty bounded string")
    if pattern.fullmatch(value) is None:
        raise _fail(path, f"invalid identity value: {value!r}")
    return value


def _plain_text(value: Any, path: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise _fail(path, "must be a non-empty bounded string")
    return value


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _count(value: Any, path: str, minimum: int = 0) -> Optional[int]:
    if value is None:
        return None
    if not _is_int(value) or value < minimum:
        raise _fail(path, "must be a non-negative integer or null")
    return value


def _measurement(value: Any, path: str) -> Optional[float]:
    """Finite non-negative number, or None meaning unavailable. Never coerced to zero."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(path, "must be a number or null")
    if not math.isfinite(value):
        raise _fail(path, "must be finite")
    if value < 0:
        raise _fail(path, "must be non-negative")
    return value


def _digest(value: Any, path: str) -> Optional[str]:
    if value is None:
        return None
    return _text(value, path, _DIGEST, 71)


def validate_envelope(document: Any) -> Dict[str, Any]:
    """Validate a decoded envelope. Returns the same object when valid."""
    if not isinstance(document, dict):
        raise _fail("document", "must be an object")
    if document.get("schema") != SCHEMA_ID:
        raise _fail("schema", f"must equal {SCHEMA_ID} (other namespaces are rejected)")

    quality = document.get("quality")
    if quality not in QUALITY_LEVELS:
        raise _fail("quality", f"must be one of: {', '.join(QUALITY_LEVELS)}")
    is_legacy = quality == "legacy-limited"

    if is_legacy:
        _mapping(document, "document", REQUIRED_KEYS | {"legacy"}, {"timings_ms"})
    else:
        _mapping(document, "document", REQUIRED_KEYS | {"cache"}, {"timings_ms"})
    unknown_top = sorted(set(document) - TOP_LEVEL_KEYS)
    if unknown_top:
        raise _fail("document", f"unknown keys: {', '.join(unknown_top)}")

    source = _mapping(
        document["source"], "source",
        ("repository", "commit_sha", "workflow", "workflow_run_id", "run_attempt"), (),
    )
    _text(source["repository"], "source.repository", _REPOSITORY, 140)
    _text(source["commit_sha"], "source.commit_sha", _COMMIT_SHA, 40)
    _plain_text(source["workflow"], "source.workflow", 128)
    _text(source["workflow_run_id"], "source.workflow_run_id", _RUN_ID, 64)
    if source["run_attempt"] is None:
        if not is_legacy:
            raise _fail("source.run_attempt", "is required unless quality is legacy-limited")
    elif not _is_int(source["run_attempt"]) or source["run_attempt"] < 1:
        raise _fail("source.run_attempt", "must be an integer >= 1")

    producer = _mapping(document["producer"], "producer", ("name", "version"), ())
    _plain_text(producer["name"], "producer.name", 64)
    _plain_text(producer["version"], "producer.version", 64)

    toolchain = document["toolchain"]
    if not isinstance(toolchain, dict) or not 1 <= len(toolchain) <= 16:
        raise _fail("toolchain", "must be an object with 1..16 entries")
    for key, value in toolchain.items():
        if not isinstance(key, str) or _TOOL_KEY.fullmatch(key) is None:
            raise _fail("toolchain", f"invalid key: {key!r}")
        _plain_text(value, f"toolchain.{key}", 128)
    if not is_legacy:
        for key in TOOLCHAIN_REQUIRED:
            if key not in toolchain:
                raise _fail("toolchain", f"missing key: {key}")

    clock = _mapping(document["clock"], "clock", ("utc_anchor", "uncertainty_ms"), ())
    if clock["utc_anchor"] is None:
        if not is_legacy:
            raise _fail("clock.utc_anchor", "is required unless quality is legacy-limited")
    else:
        _text(clock["utc_anchor"], "clock.utc_anchor", _UTC_ANCHOR, 40)
    _measurement(clock["uncertainty_ms"], "clock.uncertainty_ms")

    timings = document.get("timings_ms")
    if timings is not None:
        if not isinstance(timings, dict):
            raise _fail("timings_ms", "must be an object")
        for name, value in timings.items():
            if name not in TIMING_NAMES:
                raise _fail("timings_ms", f"unknown timing: {name}")
            _measurement(value, f"timings_ms.{name}")

    universe = _mapping(document["test_universe"], "test_universe", ("digest", "size"), ())
    _digest(universe["digest"], "test_universe.digest")
    universe_size = _count(universe["size"], "test_universe.size")

    selected = _mapping(document["selected"], "selected", ("digest", "count"), ())
    _digest(selected["digest"], "selected.digest")
    selected_count = _count(selected["count"], "selected.count")

    execution = _mapping(document["execution"], "execution", ("executed_now", "verified_from_cache"), ())
    executed_now = _count(execution["executed_now"], "execution.executed_now")
    verified = _count(execution["verified_from_cache"], "execution.verified_from_cache")

    if universe_size is not None and selected_count is not None and selected_count > universe_size:
        raise _fail("selected.count", "must not exceed test_universe.size")
    if None not in (selected_count, executed_now, verified) and executed_now + verified > selected_count:
        raise _fail("execution", "executed_now + verified_from_cache must not exceed selected.count")

    if is_legacy:
        legacy = _mapping(document["legacy"], "legacy", ("cache_state",), ())
        _plain_text(legacy["cache_state"], "legacy.cache_state", 256)
    else:
        _validate_cache(document["cache"])

    _validate_quality_semantics(quality, document, selected_count, executed_now, verified)
    return document


def _validate_cache(cache: Any) -> None:
    cache = _mapping(cache, "cache", ("experiment_class", "policy_digest", "cacheIdentity"), ())
    if cache["experiment_class"] not in EXPERIMENT_CLASSES:
        raise _fail("cache.experiment_class", f"must be one of: {', '.join(EXPERIMENT_CLASSES)}")
    _digest(cache["policy_digest"], "cache.policy_digest")

    identity = _mapping(cache["cacheIdentity"], "cache.cacheIdentity", ("layers", "seedProvenance"), ())
    layers = identity["layers"]
    if not isinstance(layers, dict):
        raise _fail("cache.cacheIdentity.layers", "must be an object")
    for name, layer in layers.items():
        if name not in LAYER_NAMES:
            raise _fail("cache.cacheIdentity.layers", f"unknown layer: {name}")
        layer = _mapping(layer, f"cache.cacheIdentity.layers.{name}", ("state",), ())
        if layer["state"] not in LAYER_STATES:
            raise _fail(f"cache.cacheIdentity.layers.{name}.state",
                        f"must be one of: {', '.join(LAYER_STATES)}")

    seed = _mapping(identity["seedProvenance"], "cache.cacheIdentity.seedProvenance",
                    ("seeded", "seed_input_digest"), ())
    if seed["seeded"] is not None and not isinstance(seed["seeded"], bool):
        raise _fail("cache.cacheIdentity.seedProvenance.seeded", "must be a boolean or null")
    _digest(seed["seed_input_digest"], "cache.cacheIdentity.seedProvenance.seed_input_digest")


def _validate_quality_semantics(quality: str, document: Mapping[str, Any],
                                selected_count: Optional[int],
                                executed_now: Optional[int],
                                verified: Optional[int]) -> None:
    timings = document.get("timings_ms") or {}
    if quality == "complete":
        if None in (selected_count, executed_now, verified):
            raise _fail("quality", "complete requires selected.count and execution counts")
        if document["selected"]["digest"] is None or document["test_universe"]["digest"] is None:
            raise _fail("quality", "complete requires test universe and selected digests")
        layers = document["cache"]["cacheIdentity"]["layers"]
        if any(name not in layers for name in LAYER_NAMES):
            raise _fail("quality", "complete requires all cache layers")
    elif quality == "unavailable":
        if any(value is not None for value in (selected_count, executed_now, verified)):
            raise _fail("quality", "unavailable must not carry measured counts")
        if any(value is not None for value in timings.values()):
            raise _fail("quality", "unavailable must not carry measured timings")


# ---------------------------------------------------------------------------
# Writer and projections
# ---------------------------------------------------------------------------

def dumps_envelope(document: Mapping[str, Any]) -> str:
    """Validate and serialize deterministically (sorted keys, two-space indent)."""
    validated = validate_envelope(deepcopy(dict(document)))
    return json.dumps(validated, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def to_legacy_module_record(document: Mapping[str, Any]) -> Dict[str, Any]:
    """Project a new-writer envelope onto the legacy module-evidence identity shape.

    The legacy ``cache_state`` is a lossless text rendering of the layer vector,
    e.g. ``dependency=warm;build=cold;configuration=disabled``. Legacy-only fields
    that the envelope does not carry are written as the literal ``not-collected``.
    """
    validated = validate_envelope(deepcopy(dict(document)))
    if validated["quality"] == "legacy-limited":
        raise PerformanceEvidenceError("legacy-limited documents are not re-projected")
    layers = validated["cache"]["cacheIdentity"]["layers"]
    cache_state = ";".join(
        f"{name}={layers[name]['state']}" for name in LAYER_NAMES if name in layers
    ) or "unknown"
    toolchain = validated["toolchain"]
    source = validated["source"]
    return {
        "run_id": source["workflow_run_id"],
        "provenance": {
            "repository": source["repository"],
            "commit_sha": source["commit_sha"],
            "workflow": source["workflow"],
            "job": "not-collected",
        },
        "environment_identity": {
            "runner_image": toolchain["runner_image"],
            "java_version": toolchain["java_version"],
            "python_version": toolchain["python_version"],
            "cache_state": cache_state,
            "database_fixture": "not-collected",
            "cpu_memory_profile": "not-collected",
            "dependency_mode": "not-collected",
            "config_catalog_hash": "not-collected",
        },
    }


def read_legacy_module_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Legacy reader: module-evidence identity record -> envelope with quality legacy-limited.

    ``cache_state`` is preserved verbatim. No cacheIdentity or layer state is inferred.
    """
    if not isinstance(record, dict):
        raise _fail("legacy", "must be an object")
    provenance = _legacy_fields(record.get("provenance"), "legacy.provenance",
                                ("repository", "commit_sha", "workflow"))
    identity = _legacy_fields(record.get("environment_identity"), "legacy.environment_identity",
                              ("cache_state", *TOOLCHAIN_REQUIRED))
    if "run_id" not in record:
        raise _fail("legacy.run_id", "is required")
    document = {
        "schema": SCHEMA_ID,
        "source": {
            "repository": provenance["repository"],
            "commit_sha": provenance["commit_sha"],
            "workflow": provenance["workflow"],
            "workflow_run_id": record["run_id"],
            "run_attempt": None,
        },
        "producer": {"name": "legacy-module-evidence", "version": "unknown"},
        "toolchain": {key: identity[key] for key in TOOLCHAIN_REQUIRED},
        "clock": {"utc_anchor": None, "uncertainty_ms": None},
        "quality": "legacy-limited",
        "test_universe": {"digest": None, "size": None},
        "selected": {"digest": None, "count": None},
        "execution": {"executed_now": None, "verified_from_cache": None},
        "legacy": {"cache_state": identity["cache_state"]},
    }
    return validate_envelope(document)
