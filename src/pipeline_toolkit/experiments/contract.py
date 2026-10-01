from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

REPOSITORY = "YRootLab/OnMaru-backend"
WORKFLOW = "pipeline-benchmark-experiment.yml"
WORKFLOW_PATH = ".github/workflows/" + WORKFLOW
POLICY_VERSION = "pipeline-experiment/1"
MAX_BYTES = 1024 * 1024


class ExperimentError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ExperimentError(code)


def sha(value) -> str:
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None, "invalid_ref")
    return value


def positive_id(value) -> int:
    require(type(value) is int and 0 < value < 2 ** 63, "invalid_run_identity")
    return value


def scope(value: str) -> str:
    require(value in ("ci", "test"), "unsupported_scope")
    return value


def run_url(run_id: int) -> str:
    return f"https://github.com/{REPOSITORY}/actions/runs/{positive_id(run_id)}"


def safe_link(value, *, artifact_run=None, grafana=False) -> str:
    require(isinstance(value, str) and len(value) <= 2048, "invalid_link")
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
        require(parsed.hostname.endswith(".grafana.net") and parsed.path.startswith("/d/"), "invalid_link")
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
