#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -s docs/prd.md
test -s docs/prd-implementation-gap-review.md
test -s AGENTS.md

python3 /Users/yangseunghyeon/.agents/skills/adr-toolkit/scripts/adr.py validate --dir docs/decisions --json
python3 /Users/yangseunghyeon/.agents/skills/adr-toolkit/scripts/adr.py index --dir docs/decisions --json >/dev/null

if [ -f pyproject.toml ]; then
  python3 -m compileall -q src tests
fi

echo "Toolkit verification passed."
