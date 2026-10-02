from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

REPOSITORY = "YRootLab/OnMaru-backend"
WORKFLOW = "pipeline-benchmark-experiment.yml"
WORKFLOW_PATH = ".github/workflows/" + WORKFLOW
POLICY_VERSION = "pipeline-experiment/2"
TEST_PLAN_PATH = ".github/pipeline-benchmark-test-plan.json"
SOURCE_FIELDS = ("application_source_commit", "application_source_tree", "test_plan_sha256")
MAX_BYTES = 1024 * 1024


class ExperimentError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ExperimentError(code)


def source_identity(value):
    require(isinstance(value, dict), "source_identity_unavailable")
    require(all(isinstance(value.get(key), str) and re.fullmatch(r"[0-9a-f]{40}" if key != "test_plan_sha256" else r"[0-9a-f]{64}", value[key]) for key in SOURCE_FIELDS), "source_identity_unavailable")
    return {key: value[key] for key in SOURCE_FIELDS}


def sha(value) -> str:
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None, "invalid_ref")
    return value


def positive_id(value) -> int:
    require(type(value) is int and 0 < value < 2 ** 63, "invalid_run_identity")
    return value


def scope(value: str) -> str:
    require(value in ("ci", "test"), "unsupported_scope")
    return value


def select_test_plan_scope(plan: dict, selected_scope: str) -> dict:
    """Validate a committed plan and return its complete selected scope entry.

    Version 1 uses ``{"version": 1, "scopes": {"ci": {...}, "test": {...}}}``.
    Unversioned legacy ``scope``/``suite`` plans remain accepted only when
    neither version nor scopes is present. Mixed formats never fall back.
    Execution-specific fields are preserved, not interpreted or executed;
    consumers must validate them under their trusted worker policy.
    """
    code = "source_identity_unverified"
    require(isinstance(plan, dict) and selected_scope in ("ci", "test"), code)
    if "version" in plan or "scopes" in plan:
        require(type(plan.get("version")) is int and plan["version"] == 1, code)
        require("scope" not in plan and "suite" not in plan, code)
        entries = plan.get("scopes")
        require(isinstance(entries, dict) and bool(entries), code)
        require(all(key in ("ci", "test") for key in entries), code)
    else:
        require(plan.get("scope") in ("ci", "test"), code)
        entries = {plan["scope"]: plan}
    for entry in entries.values():
        require(isinstance(entry, dict) and isinstance(entry.get("suite"), str) and bool(entry["suite"].strip()), code)
    require(selected_scope in entries, code)
    return entries[selected_scope]


def run_url(run_id: int) -> str:
    return f"https://github.com/{REPOSITORY}/actions/runs/{positive_id(run_id)}"


def safe_link(value, *, artifact_run=None, grafana=False) -> str:
    require(isinstance(value, str) and len(value) <= 2048, "invalid_link")
    # urlparse strips some leading controls and embedded CR/LF/TAB. Validate
    # the original string before parsing so it can never become Markdown.
    require(not any(char.isspace() or unicodedata.category(char).startswith("C") or char in "<>[]()\"'`\\" for char in value), "invalid_link")
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise ExperimentError("invalid_link") from exc
    require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment, "invalid_link")
    require(port in (None, 443), "invalid_link")
    if artifact_run is not None:
        require(re.fullmatch(re.escape(run_url(artifact_run)) + r"/artifacts/[1-9][0-9]*", value) is not None, "invalid_link")
    if grafana:
        require(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.grafana\.net", parsed.hostname) is not None and re.fullmatch(r"/d/[A-Za-z0-9_-]{1,128}(?:/[A-Za-z0-9_-]{1,128})?", parsed.path) is not None, "invalid_link")
    return value


def load_json_bytes(raw: bytes) -> dict:
    require(len(raw) <= MAX_BYTES, "input_too_large")
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ExperimentError("invalid_json") from exc
    require(isinstance(document, dict), "invalid_json")
    return document


def load_document(path: Path) -> dict:
    try:
        with path.open("rb") as source:
            return load_json_bytes(source.read(MAX_BYTES + 1))
    except OSError as exc:
        raise ExperimentError("input_unavailable") from exc


def validate_header(document: dict) -> None:
    require(type(document.get("version")) is int and document["version"] == 1 and document.get("policy_version") == POLICY_VERSION, "policy_mismatch")
    require(document.get("repository") == REPOSITORY, "wrong_repository")
    sha(document.get("baseline_ref")); sha(document.get("candidate_ref"))
    require(document["baseline_ref"] != document["candidate_ref"], "equal_refs")
    scope(document.get("scope"))
