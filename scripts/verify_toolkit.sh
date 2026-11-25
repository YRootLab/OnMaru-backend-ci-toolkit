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
  test -s tests/test_consumer_performance_integration.py
  test -s tests/fixtures/consumer-performance/success.json
  PYTHONPATH=src python3 -m pytest -q tests/test_consumer_performance_integration.py
  PYTHONPATH=src python3 -m coverage run -m pytest -q
  python3 -m coverage report --include='src/pipeline_toolkit/*' --fail-under=90
fi

python3 scripts/verify_workflow_security.py

# Live docs: internal links and anchors, referenced paths, figure alt text and captions.
# The D2-to-SVG byte drift check runs only when the pinned d2 is installed (see the script header).
python3 scripts/check_pipeline_docs.py

echo "Toolkit verification passed."
