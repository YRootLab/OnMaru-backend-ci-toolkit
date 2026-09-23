from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Module:
    id: str
    paths: tuple[str, ...]
    depends_on: tuple[str, ...]
    test_command: str
    resource_profile: str


@dataclass(frozen=True)
class ModuleCatalog:
    modules: tuple[Module, ...]
    always_full_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ids = {module.id for module in self.modules}
        if not ids or len(ids) != len(self.modules):
            raise ValueError("module ids must be unique and non-empty")
        if any(not module.paths or not module.test_command for module in self.modules):
            raise ValueError("module paths and test_command are required")
        unknown = {dependency for module in self.modules for dependency in module.depends_on if dependency not in ids}
        if unknown:
            raise ValueError(f"unknown module dependencies: {sorted(unknown)}")
        visiting: set[str] = set()
        visited: set[str] = set()
        by_id = {module.id: module for module in self.modules}

        def visit(module_id: str) -> None:
            if module_id in visiting:
                raise ValueError("module dependencies must be acyclic")
            if module_id not in visited:
                visiting.add(module_id)
                for dependency in by_id[module_id].depends_on:
                    visit(dependency)
                visiting.remove(module_id)
                visited.add(module_id)

        for module_id in by_id:
            visit(module_id)


@dataclass(frozen=True)
class ExecutionPlan:
    modules: tuple[Module, ...]
    full_suite: bool
    reason: str


def load_catalog(path: str | Path) -> ModuleCatalog:
    try:
        document = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"invalid module catalog: {error}") from error
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("module catalog version must be 1")
    raw_modules = document.get("modules")
    if not isinstance(raw_modules, list):
        raise ValueError("module catalog modules must be a list")
    try:
        modules = tuple(
            Module(
                id=item["id"],
                paths=tuple(item["paths"]),
                depends_on=tuple(item.get("depends_on", ())),
                test_command=item["test_command"],
                resource_profile=item["resource_profile"],
            )
            for item in raw_modules
        )
    except (KeyError, TypeError) as error:
        raise ValueError("module catalog has an invalid module entry") from error
    return ModuleCatalog(modules, tuple(document.get("always_full_paths", ())))


def plan_affected_modules(catalog: ModuleCatalog, changed_paths: tuple[str, ...] | None) -> ExecutionPlan:
    ordered = tuple(sorted(catalog.modules, key=lambda module: module.id))
    if not changed_paths:
        return ExecutionPlan(ordered, True, "unknown-diff")
    if any(fnmatch(path, pattern) for path in changed_paths for pattern in catalog.always_full_paths):
        return ExecutionPlan(ordered, True, "always-full-path")

    selected = {module.id for module in catalog.modules if any(fnmatch(path, pattern) for path in changed_paths for pattern in module.paths)}
    if not selected:
        return ExecutionPlan(ordered, True, "unknown-path")

    reverse: dict[str, set[str]] = {module.id: set() for module in catalog.modules}
    for module in catalog.modules:
        for dependency in module.depends_on:
            reverse[dependency].add(module.id)
    queue = list(selected)
    while queue:
        module_id = queue.pop()
        for dependent in reverse[module_id]:
            if dependent not in selected:
                selected.add(dependent)
                queue.append(dependent)
    return ExecutionPlan(tuple(module for module in ordered if module.id in selected), False, "affected")
