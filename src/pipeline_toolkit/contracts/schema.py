from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

def _schema(path: str | Path) -> dict[str, Any]:
    schema_path = Path(path)
    if not schema_path.is_file(): raise FileNotFoundError(schema_path)
    return json.loads(schema_path.read_text())

def validate_document(document: Any, schema_path: str | Path) -> list[str]:
    schema = _schema(schema_path)
    errors: list[str] = []
    if not isinstance(document, dict): return ["document must be an object"]
    for field in schema.get("required", ()):
        if field not in document: errors.append(f"missing required field: {field}")
    for field, rule in schema.get("properties", {}).items():
        if field not in document: continue
        value = document[field]
        if "const" in rule and value != rule["const"]: errors.append(f"{field} must equal {rule['const']}")
        if "enum" in rule and value not in rule["enum"]: errors.append(f"{field} must be one of: {', '.join(rule['enum'])}")
        expected = rule.get("type")
        if expected and not _matches_type(value, expected): errors.append(f"{field} must be {expected}")
    return errors

def _matches_type(value: Any, expected: str | list[str]) -> bool:
    types = [expected] if isinstance(expected, str) else expected
    return any((kind == "string" and isinstance(value, str)) or (kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)) or (kind == "null" and value is None) or (kind == "array" and isinstance(value, list)) or (kind == "object" and isinstance(value, dict)) for kind in types)

def migrate_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != "0.9": return deepcopy(document)
    migrated = deepcopy(document)
    migrated["schema_version"] = "1.0"
    if "quality" not in migrated and "status" in migrated: migrated["quality"] = migrated.pop("status")
    return migrated
