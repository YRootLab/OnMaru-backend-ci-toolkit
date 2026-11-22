#!/usr/bin/env python3
"""Documentation drift check for the live Toolkit guides and architecture diagrams.

Checks, in order:

1. Every internal Markdown link and anchor in the live documents resolves.
2. Every backticked repository path in the live documents exists.
3. Every image has non-empty alt text, and every architecture figure section
   has caption, alt text, legend and evidence labels.
4. Every ``link:`` in a D2 source points at an existing repository path.
5. Every D2 source has a committed SVG that is byte-identical to a fresh render
   with the pinned D2 version. When ``d2`` is not installed or is a different
   version, this step is reported as SKIPPED. ``--require-d2`` turns the skip
   into a failure. ``--render`` rewrites the committed SVGs instead of checking.

Standard library only; runs on Python 3.9.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

D2_PIN = "0.8.1"
D2_FLAGS = ["--theme=0", "--pad=24", "--layout=dagre"]

LIVE_DOC_GLOBS = ("README.md", "docs/architecture/*.md", "docs/telemetry/*.md")
DIAGRAM_DIR = "docs/diagrams"
FIGURES_DOC = "docs/architecture/figures.md"
FIGURE_LABELS = ("캡션", "대체 텍스트", "범례", "근거")
REPO_PATH_PREFIXES = ("src/", "scripts/", "tests/", "schemas/", "observability/", "docs/", ".github/")

LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
FENCE = re.compile(r"^(```|~~~)")
D2_LINK = re.compile(r"(?:^|[\s{;])link:\s*([^\s}]+)")
EXTERNAL = ("http://", "https://", "mailto:")


def slugify(heading: str) -> str:
    """GitHub-style heading anchor: lowercase, drop punctuation, spaces to hyphens. Hangul is kept."""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def strip_fences(lines: List[str]) -> List[Tuple[int, str]]:
    """Return (line number, text) pairs outside fenced code blocks."""
    kept: List[Tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(lines, 1):
        if FENCE.match(line.strip()):
            in_fence = not in_fence
            continue
        if not in_fence:
            kept.append((number, line))
    return kept


def anchors_of(path: Path) -> set:
    anchors = set()
    seen: dict = {}
    for _, line in strip_fences(path.read_text(encoding="utf-8").splitlines()):
        match = HEADING.match(line)
        if not match:
            continue
        slug = slugify(match.group(2))
        count = seen.get(slug, 0)
        anchors.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return anchors


def check_markdown(root: Path, doc: Path, errors: List[str]) -> None:
    rel = doc.relative_to(root).as_posix()
    lines = doc.read_text(encoding="utf-8").splitlines()
    for number, line in strip_fences(lines):
        for is_image, alt, target in LINK.findall(line):
            if target.startswith(EXTERNAL):
                continue
            if is_image and not alt.strip():
                errors.append(f"{rel}:{number}: image without alt text: {target}")
            path_part, _, anchor = target.partition("#")
            if path_part:
                resolved = (doc.parent / path_part).resolve()
                if not resolved.exists():
                    errors.append(f"{rel}:{number}: broken link: {target}")
                    continue
                if anchor and resolved.suffix == ".md" and anchor not in anchors_of(resolved):
                    errors.append(f"{rel}:{number}: missing anchor: {target}")
            elif anchor and anchor not in anchors_of(doc):
                errors.append(f"{rel}:{number}: missing anchor: #{anchor}")
        for token in CODE_SPAN.findall(line):
            candidate = token.strip().rstrip(",.;:)")
            if not candidate.startswith(REPO_PATH_PREFIXES):
                continue
            if any(ch in candidate for ch in "*<>{} "):
                continue
            if not (root / candidate).exists():
                errors.append(f"{rel}:{number}: referenced path does not exist: {candidate}")


def check_figures(root: Path, errors: List[str]) -> List[str]:
    doc = root / FIGURES_DOC
    if not doc.is_file():
        errors.append(f"missing figure index: {FIGURES_DOC}")
        return []
    sections = re.split(r"^## ", doc.read_text(encoding="utf-8"), flags=re.MULTILINE)
    figures = [s for s in sections if s.startswith("그림")]
    if not figures:
        errors.append(f"{FIGURES_DOC}: no figure sections found")
    for section in figures:
        title = section.splitlines()[0]
        for label in FIGURE_LABELS:
            if label not in section:
                errors.append(f"{FIGURES_DOC}: figure '{title}' lacks {label}")
        if not re.search(r"!\[[^\]]+\]\(\.\./diagrams/[^)]+\.svg\)", section):
            errors.append(f"{FIGURES_DOC}: figure '{title}' does not embed an SVG with alt text")
    return [m for m in re.findall(r"\(\.\./diagrams/([^)\s]+\.svg)\)", doc.read_text(encoding="utf-8"))]


def check_d2_links(root: Path, source: Path, errors: List[str]) -> None:
    text = source.read_text(encoding="utf-8")
    for target in D2_LINK.findall(text):
        if target.startswith(EXTERNAL):
            continue
        if not (source.parent / target).resolve().exists():
            errors.append(f"{source.relative_to(root).as_posix()}: link target missing: {target}")


def d2_version(d2: str) -> Optional[str]:
    try:
        out = subprocess.run([d2, "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"v(\d+\.\d+\.\d+)", out.stdout + out.stderr)
    return match.group(1) if match else None


def render(d2: str, source: Path, target: Path) -> None:
    subprocess.run([d2, *D2_FLAGS, str(source), str(target)], check=True, capture_output=True, timeout=120)


def check_svgs(root: Path, render_only: bool, require_d2: bool, errors: List[str], notes: List[str]) -> None:
    sources = sorted((root / DIAGRAM_DIR).glob("*.d2"))
    if not sources:
        errors.append(f"no D2 sources under {DIAGRAM_DIR}")
        return
    d2 = shutil.which("d2")
    version = d2_version(d2) if d2 else None
    if render_only:
        if not d2 or version != D2_PIN:
            errors.append(f"--render needs d2 {D2_PIN}; found {version or 'none'}")
            return
        for source in sources:
            render(d2, source, source.with_suffix(".svg"))
            notes.append(f"rendered {source.relative_to(root).as_posix()}")
        return
    if not d2 or version != D2_PIN:
        message = f"SVG drift check SKIPPED: need d2 {D2_PIN}, found {version or 'none'}"
        (errors if require_d2 else notes).append(message)
        return
    for source in sources:
        committed = source.with_suffix(".svg")
        rel = source.relative_to(root).as_posix()
        if not committed.is_file():
            errors.append(f"{rel}: committed SVG missing; run --render")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / "fresh.svg"
            render(d2, source, fresh)
            if fresh.read_bytes() != committed.read_bytes():
                errors.append(f"{committed.relative_to(root).as_posix()} is stale; run --render")
            else:
                notes.append(f"SVG up to date: {committed.relative_to(root).as_posix()}")


def check_all(root: Path, require_d2: bool = False, render_only: bool = False) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    notes: List[str] = []
    docs = sorted({p for pattern in LIVE_DOC_GLOBS for p in root.glob(pattern)})
    for doc in docs:
        check_markdown(root, doc, errors)
    referenced = check_figures(root, errors)
    for source in sorted((root / DIAGRAM_DIR).glob("*.d2")):
        check_d2_links(root, source, errors)
        svg = f"{source.stem}.svg"
        if svg not in referenced:
            errors.append(f"{source.relative_to(root).as_posix()}: no figure embeds {svg}")
    check_svgs(root, render_only, require_d2, errors, notes)
    notes.insert(0, f"checked {len(docs)} live documents")
    return errors, notes


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--require-d2", action="store_true", help="fail instead of skipping the SVG drift check")
    parser.add_argument("--render", action="store_true", help="regenerate committed SVGs from the D2 sources")
    args = parser.parse_args(argv)
    errors, notes = check_all(args.root.resolve(), args.require_d2, args.render)
    for note in notes:
        print(f"note: {note}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        print(f"Pipeline documentation check failed with {len(errors)} error(s).", file=sys.stderr)
        return 1
    print("Pipeline documentation check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
