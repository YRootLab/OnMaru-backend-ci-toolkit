"""Bounded JSON evidence parsing. No archive extraction, filesystem or network access."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter

MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 16 * MAX_ARTIFACT_BYTES
MAX_ARTIFACTS = 256
MODULE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
TOOLKIT_REF = re.compile(r"[0-9a-f]{40}\Z")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _module(data, run_id, attempt, toolkit_ref, job_ids, expected):
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema")
    if any(type(data.get(key)) is not int or data[key] <= 0 for key in ("run_id", "run_attempt")):
        raise ValueError("identity")
    module_id = data.get("module_id")
    if not isinstance(module_id, str) or not MODULE_ID.fullmatch(module_id):
        raise ValueError("schema")
    job_id = data.get("job_id", expected.get(module_id) if expected is not None else None)
    if type(job_id) is not int or job_id <= 0 or job_id not in job_ids:
        raise ValueError("identity")
    if (data["run_id"], data["run_attempt"], data.get("toolkit_ref")) != (run_id, attempt, toolkit_ref):
        raise ValueError("identity")
    if expected is not None and expected.get(module_id) != job_id:
        raise ValueError("identity")
    if type(data.get("complete")) is not bool:
        raise ValueError("schema")
    exit_code, duration = data.get("exit_code"), data.get("wall_clock_seconds")
    if exit_code is not None and (type(exit_code) is not int or not 0 <= exit_code <= 255):
        raise ValueError("schema")
    if duration is not None and (type(duration) not in (int, float) or not 0 <= duration <= 31_536_000 or not math.isfinite(duration)):
        raise ValueError("schema")
    complete = data["complete"] and exit_code is not None and duration is not None
    return {"module_id": module_id, "job_id": job_id, "exit_code": exit_code,
            "wall_clock_seconds": duration, "complete": complete,
            "status": "failed" if exit_code not in (None, 0) else "success" if complete else "incomplete"}


def join_module_artifacts(artifacts, *, run_id, attempt, toolkit_ref, job_ids, expected):
    """Validate raw JSON bytes and explicit module→job mapping; quarantine duplicates.

    `digest` optionally verifies the JSON member, NOT a GitHub ZIP archive digest.
    All accepted members receive a computed content digest regardless of metadata.
    """
    if not isinstance(artifacts, list) or len(artifacts) > MAX_ARTIFACTS:
        raise ValueError("artifacts exceed collection bound or are invalid")
    if expected is not None:
        if not isinstance(expected, dict) or len(expected) > MAX_ARTIFACTS:
            raise ValueError("expected modules exceed collection bound")
        for module_id, job_id in expected.items():
            if not isinstance(module_id, str) or not MODULE_ID.fullmatch(module_id) or type(job_id) is not int or job_id <= 0:
                raise ValueError("invalid expected module mapping")
    total_bytes = sum(len(a.get("data", b"")) for a in artifacts if isinstance(a, dict) and isinstance(a.get("data"), bytes))
    if total_bytes > MAX_TOTAL_ARTIFACT_BYTES:
        raise ValueError("total artifact bytes exceed collection bound")
    records, candidates, issues = [], [], []
    for artifact in artifacts:
        record = {"id": None, "digest": None, "quality": "invalid"}
        try:
            if not isinstance(artifact, dict) or type(artifact.get("id")) is not int or artifact["id"] <= 0:
                raise ValueError("metadata")
            record["id"] = artifact["id"]
            raw = artifact.get("data")
            if not isinstance(raw, bytes) or len(raw) > MAX_ARTIFACT_BYTES:
                raise ValueError("size")
            digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            record["digest"] = digest
            if artifact.get("digest", digest) != digest:
                raise ValueError("digest_mismatch")
            try:
                data = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
            except (ValueError, UnicodeError, RecursionError):
                raise ValueError("json") from None
            module = _module(data, run_id, attempt, toolkit_ref, job_ids, expected)
            module.update(artifact_id=record["id"], artifact_digest=digest)
            record["quality"] = "complete" if module["complete"] else "partial"
            record["module_id"] = module["module_id"]
            candidates.append((record, module))
        except ValueError as exc:
            issues.append(f"artifact_{exc}:{record['id'] if record['id'] is not None else 'unknown'}")
        records.append(record)
    ids = Counter(r["id"] for r in records if r["id"] is not None)
    modules = Counter(m["module_id"] for _, m in candidates)
    joined = []
    for record, module in candidates:
        if ids[record["id"]] > 1 or modules[module["module_id"]] > 1:
            record["quality"] = "invalid"
            issues.append(f"duplicate_artifact:{module['module_id']}")
        else:
            joined.append(module)
            if not module["complete"]:
                issues.append(f"partial_module:{module['module_id']}")
    missing = sorted(set(expected or {}) - {m["module_id"] for m in joined})
    issues.extend("missing_module:" + name for name in missing)
    invalid = any(r["quality"] == "invalid" for r in records)
    if invalid:
        status = "partial" if joined else "invalid"
    elif missing or any(not m["complete"] for m in joined):
        status = "partial" if joined else "missing"
    else:
        status = "complete"
    records.sort(key=lambda r: json.dumps(r, sort_keys=True))
    return sorted(joined, key=lambda m: m["module_id"]), records, {"status": status, "issues": sorted(set(issues))}
