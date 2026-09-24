"""Fail-closed validation for report-bundle fact inputs."""

from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit


ALLOWED_STATUSES = frozenset({"success", "failed", "cancelled", "timeout", "missing"})

_TOP_LEVEL_FIELDS = frozenset({"title", "observed_at", "summary", "facts", "limitations", "next_steps"})
_FACT_FIELDS = frozenset({"name", "value", "unit", "status", "source_url", "comparable"})
_SECRET_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "credential",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "access_key",
    "client_secret",
)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ReportBundleValidationError(ValueError):
    """Raised when report facts are unsafe or do not meet the contract."""


@dataclass(frozen=True)
class ReportFact:
    name: str
    value: float
    unit: str
    status: str
    source_url: str
    comparable: bool


@dataclass(frozen=True)
class ReportBundleInput:
    title: str
    observed_at: str
    summary: str
    facts: tuple[ReportFact, ...]
    limitations: tuple[str, ...]
    next_steps: tuple[str, ...]


def is_performance_eligible(fact: ReportFact) -> bool:
    """Return whether a fact may support performance-improvement wording."""
    return fact.status == "success" and fact.comparable


def load_report_bundle(path: Path) -> ReportBundleInput:
    """Load a UTF-8 report-facts JSON file after validating its full contract."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReportBundleValidationError("report facts must be readable UTF-8 JSON") from error

    _reject_secret_like_keys(payload)
    document = _mapping(payload, "report facts")
    _require_exact_fields(document, _TOP_LEVEL_FIELDS, "report facts")

    observed_at = _required_string(document, "observed_at")
    _validate_iso_date(observed_at)
    facts = _facts(document["facts"])
    return ReportBundleInput(
        title=_required_string(document, "title"),
        observed_at=observed_at,
        summary=_required_string(document, "summary"),
        facts=facts,
        limitations=_non_empty_string_list(document, "limitations"),
        next_steps=_non_empty_string_list(document, "next_steps"),
    )


def _facts(value: Any) -> tuple[ReportFact, ...]:
    if not isinstance(value, list) or not value:
        raise ReportBundleValidationError("facts must be a non-empty list")
    return tuple(_fact(item) for item in value)


def _fact(value: Any) -> ReportFact:
    fact = _mapping(value, "fact")
    _require_exact_fields(fact, _FACT_FIELDS, "fact")
    numeric_value = fact["value"]
    if isinstance(numeric_value, bool) or not isinstance(numeric_value, (int, float)):
        raise ReportBundleValidationError("fact value must be a finite number")
    if not math.isfinite(numeric_value):
        raise ReportBundleValidationError("fact value must be a finite number")

    status = _required_string(fact, "status")
    if status not in ALLOWED_STATUSES:
        raise ReportBundleValidationError("fact status is not allowed")
    comparable = fact["comparable"]
    if not isinstance(comparable, bool):
        raise ReportBundleValidationError("fact comparable must be boolean")

    return ReportFact(
        name=_required_string(fact, "name"),
        value=float(numeric_value),
        unit=_required_string(fact, "unit"),
        status=status,
        source_url=_safe_https_url(_required_string(fact, "source_url")),
        comparable=comparable,
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ReportBundleValidationError(f"{name} must be an object")
    return value


def _require_exact_fields(value: Mapping[str, Any], expected: frozenset[str], name: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise ReportBundleValidationError(f"{name} fields do not match the canonical contract")


def _required_string(value: Mapping[str, Any], field: str) -> str:
    field_value = value.get(field)
    if not isinstance(field_value, str) or not field_value.strip():
        raise ReportBundleValidationError(f"{field} must be a non-empty string")
    return field_value


def _non_empty_string_list(value: Mapping[str, Any], field: str) -> tuple[str, ...]:
    entries = value.get(field)
    if not isinstance(entries, list) or not entries:
        raise ReportBundleValidationError(f"{field} must be a non-empty list")
    if any(not isinstance(entry, str) or not entry.strip() for entry in entries):
        raise ReportBundleValidationError(f"{field} must contain non-empty strings")
    return tuple(entries)


def _validate_iso_date(value: str) -> None:
    if not _ISO_DATE.fullmatch(value):
        raise ReportBundleValidationError("observed_at must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ReportBundleValidationError("observed_at must be an ISO date") from error


def _safe_https_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise ReportBundleValidationError("source_url must be a safe HTTPS URL") from error
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None and not 0 < port <= 65535
        or parsed.fragment
        or ";" in parsed.query
        or any(character.isspace() for character in value)
        or any(_is_secret_like_key(key) for key, _ in parse_qsl(parsed.query, keep_blank_values=True))
    ):
        raise ReportBundleValidationError("source_url must be a safe HTTPS URL")
    return value


def _reject_secret_like_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if not isinstance(key, str) or _is_secret_like_key(key):
                raise ReportBundleValidationError("secret-like keys are not allowed in report facts")
            _reject_secret_like_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _reject_secret_like_keys(nested_value)


def _is_secret_like_key(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(part in normalized for part in _SECRET_KEY_PARTS)
