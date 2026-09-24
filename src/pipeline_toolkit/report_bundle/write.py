"""Safe planning and atomic writing for dual-audience report bundles."""

from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping, Optional, Tuple


_AUDIENCES = frozenset({"developer", "easy", "both"})
_SLUG = re.compile(r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?$")


@dataclass(frozen=True)
class OutputPlan:
    """Root-bounded destinations for rendered reports and prompt packets."""

    root: Path
    developer_markdown: Optional[Path]
    developer_prompt: Optional[Path]
    easy_markdown: Optional[Path]
    easy_prompt: Optional[Path]


def plan_outputs(
    root: Path,
    observed_at: str,
    slug: str,
    audience: str,
    easy_output: Optional[Path],
) -> OutputPlan:
    """Plan report destinations without creating files or directories."""
    resolved_root = root.resolve()
    if not resolved_root.is_dir():
        raise ValueError("report root must be an existing directory")
    _validate_date(observed_at)
    if not _SLUG.fullmatch(slug):
        raise ValueError("report slug must contain only lowercase letters, digits, and hyphens")
    if audience not in _AUDIENCES:
        raise ValueError("audience must be developer, easy, or both")

    developer_root = resolved_root / "docs/reports"
    default_easy_root = developer_root / "easy"
    if easy_output is None:
        easy_root = default_easy_root
    else:
        easy_root = easy_output if easy_output.is_absolute() else resolved_root / easy_output
    _require_inside(resolved_root, developer_root)
    _require_inside(default_easy_root, easy_root)

    developer_markdown = developer_root / f"{observed_at}-{slug}-detailed.md"
    developer_prompt = developer_root / "prompts/generated" / f"{observed_at}-{slug}-detailed-prompt.md"
    easy_markdown = easy_root / f"{observed_at}-{slug}-easy.md"
    easy_prompt = easy_root / "prompts/generated" / f"{observed_at}-{slug}-easy-prompt.md"

    return OutputPlan(
        root=resolved_root,
        developer_markdown=developer_markdown if audience in {"developer", "both"} else None,
        developer_prompt=developer_prompt if audience in {"developer", "both"} else None,
        easy_markdown=easy_markdown if audience in {"easy", "both"} else None,
        easy_prompt=easy_prompt if audience in {"easy", "both"} else None,
    )


def write_outputs(
    plan: OutputPlan,
    contents: Mapping[Path, str],
    overwrite: bool,
) -> Tuple[Path, ...]:
    """Atomically write UTF-8 outputs after revalidating their root boundary."""
    destinations = tuple(contents)
    for destination in destinations:
        _require_inside(plan.root, destination)
        if destination.resolve() not in _planned_destinations(plan):
            raise ValueError("report output must be a destination in the output plan")
        if destination.exists() and not overwrite:
            raise FileExistsError(destination)

    written = []
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        _require_inside(plan.root, destination)
        _atomic_write(destination, contents[destination])
        written.append(destination)
    return tuple(written)


def _inside(root: Path, candidate: Path) -> bool:
    """Return whether a resolved candidate stays within the resolved root on Python 3.9."""
    try:
        return os.path.commonpath((str(root.resolve()), str(candidate.resolve()))) == str(root.resolve())
    except ValueError:
        return False


def _planned_destinations(plan: OutputPlan) -> frozenset[Path]:
    return frozenset(
        destination.resolve()
        for destination in (
            plan.developer_markdown,
            plan.developer_prompt,
            plan.easy_markdown,
            plan.easy_prompt,
        )
        if destination is not None
    )


def _require_inside(root: Path, candidate: Path) -> None:
    if not _inside(root, candidate):
        raise ValueError("report output must remain within the repository root")


def _validate_date(value: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("observed_at must be an ISO date") from error


def _atomic_write(destination: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(destination.parent), prefix=f".{destination.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file_handle:
            file_handle.write(content)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
