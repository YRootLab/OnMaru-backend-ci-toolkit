#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -s docs/prd.md
test -s docs/prd-implementation-gap-review.md
test -s AGENTS.md

python3 -c 'from pathlib import Path; files = sorted(Path("docs/decisions").glob("[0-9][0-9][0-9][0-9]-*.md")); assert files, "no ADR files found"; assert all((lambda lines: len(lines) >= 2 and lines[0] == "---" and lines[1].startswith("id: ADR-"))(p.read_text().splitlines()) for p in files), "invalid ADR frontmatter"; assert Path("docs/decisions/README.md").is_file(), "missing ADR index"'

if [ -f pyproject.toml ]; then
  python3 -m compileall -q src tests
fi

echo "Toolkit verification passed."
