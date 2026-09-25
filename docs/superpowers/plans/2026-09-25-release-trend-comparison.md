# Release Trend Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe prior-version, explicit-version, and historical release benchmark comparisons from immutable evidence manifests.

**Architecture:** Parse versioned filesystem manifests into typed trend records, select only an immutable and comparable baseline, and reuse the existing statistical policy for result classification. Render one deterministic result model through CLI and workflow adapters; Artifact/Release retrieval remains outside the core parser.

**Tech Stack:** Python 3.9+, stdlib dataclasses/json/pathlib, existing pytest/coverage/workflow-policy checks, GitHub Actions.

## Global Constraints

- Canonical history is a manifest stored in GitHub Artifact or Release Asset; SQLite is an optional derived cache.
- Release identity requires tag, commit SHA, and image digest; tag-only identity is invalid.
- Conditions must match exactly for a performance claim: environment, suite, config hash, runner profile.
- Failed, missing, partial, invalid, or inconclusive runs never provide performance samples.
- Core commands read a supplied local `--history-root`; they do not call GitHub APIs.
- No raw benchmark data or consumer source is committed; workflow permissions are least privilege.

---

## File map

| Path | Responsibility |
| --- | --- |
| `src/pipeline_toolkit/trend/model.py` | Typed manifest, metric, selection, and result contracts |
| `src/pipeline_toolkit/trend/manifest.py` | Strict JSON validation and history-root discovery |
| `src/pipeline_toolkit/trend/selector.py` | Explicit/previous selection and comparability reasons |
| `src/pipeline_toolkit/trend/service.py` | Statistics integration and ordered historical series |
| `src/pipeline_toolkit/trend/render.py` | JSON/Markdown/HTML/Job Summary outputs |
| `src/pipeline_toolkit/cli.py` | `trend compare` and `trend history` subcommands |
| `.github/workflows/reusable-benchmark.yml` | Manifest materialization/publish convention |
| `tests/test_trend_*.py` | Unit and renderer fixtures |
| `tests/test_cli.py` | Subprocess CLI contract |
| `tests/test_reusable_benchmark_workflow.py` | Workflow fixture/security contract |

### Task 1: Add typed manifests and history discovery

**Files:** Create `src/pipeline_toolkit/trend/model.py`, `src/pipeline_toolkit/trend/manifest.py`, `src/pipeline_toolkit/trend/__init__.py`; create `tests/test_trend_manifest.py`, `tests/fixtures/trend/*.json`.

**Interfaces:** Produces `load_manifest(path: Path) -> TrendManifest` and `discover_manifests(history_root: Path) -> tuple[TrendManifest, ...]`.

- [ ] Write failing tests for a complete manifest, missing image digest, credential-bearing URI, duplicate metric, and deterministic discovery order.
- [ ] Run `PYTHONPATH=src python3 -m pytest -q tests/test_trend_manifest.py`; expect collection/import failure.
- [ ] Implement frozen dataclasses and fail-closed parser using only stdlib JSON/pathlib/math.
- [ ] Re-run the focused suite; expect all tests to pass.
- [ ] Commit `feat: add release trend manifest contracts`.

### Task 2: Add baseline selection and comparison service

**Files:** Create `src/pipeline_toolkit/trend/selector.py`, `src/pipeline_toolkit/trend/service.py`; create `tests/test_trend_selector.py`, `tests/test_trend_service.py`.

**Consumes:** `TrendManifest` from Task 1 and `compare_releases` from `pipeline_toolkit.compare.statistics`.

- [ ] Write failing tests that select the closest earlier compatible successful release, reject an incompatible explicit tag, reject duplicate tag identities, and omit failed samples.
- [ ] Run the two focused test files; expect unresolved selector/service imports.
- [ ] Implement `select_baseline(manifests, candidate_tag, baseline) -> BaselineSelection` and `compare_metric(...) -> TrendComparison` with reason codes.
- [ ] Re-run tests; expect valid delta/status and `inconclusive` reason coverage.
- [ ] Commit `feat: select comparable release trend baselines`.

### Task 3: Render trend facts deterministically

**Files:** Create `src/pipeline_toolkit/trend/render.py`; create `tests/test_trend_render.py`.

**Consumes:** `TrendComparison` and `TrendSeries` from Task 2. Produces `render_json`, `render_markdown`, `render_html`, `render_job_summary`.

- [ ] Write failing snapshot-style tests for previous, explicit-incompatible, and history output.
- [ ] Run `PYTHONPATH=src python3 -m pytest -q tests/test_trend_render.py`; expect import failure.
- [ ] Implement renderers that include immutable identity, strategy, sample counts, and reasons; do not draw a continuous trend across omitted points.
- [ ] Re-run focused tests; expect byte-stable output.
- [ ] Commit `feat: render evidence-backed release trends`.

### Task 4: Expose CLI and reusable workflow convention

**Files:** Modify `src/pipeline_toolkit/cli.py`; modify `.github/workflows/reusable-benchmark.yml`; create/modify `tests/test_cli.py`, `tests/test_reusable_benchmark_workflow.py`.

**Consumes:** Task 1–3 interfaces. Produces `pipeline-toolkit trend compare` and `pipeline-toolkit trend history`.

- [ ] Write subprocess tests for `previous`, explicit tag, unknown tag, and each output format; write workflow assertions for local history root, Artifact upload, read-only permissions, and fork-secret isolation.
- [ ] Run focused tests; expect unknown subcommand/contract failures.
- [ ] Add nested argparse commands and wire renderer output without changing existing `compare` behavior. Add a reusable workflow job that only materializes caller-provided manifest files and uploads candidate output.
- [ ] Run focused tests and `python3 scripts/verify_workflow_security.py`; expect pass.
- [ ] Commit `feat: expose release trend CLI and workflow contract`.

### Task 5: Integrate end-to-end fixture and documentation

**Files:** Modify `README.md`, `docs/reports/README.md`, `handoff.md`; create `tests/test_trend_e2e.py` and a multi-release fixture tree.

**Consumes:** all prior tasks.

- [ ] Write one end-to-end test that runs the installed module with a comparable previous manifest, an explicit incompatible manifest, and a failed intermediate run.
- [ ] Run it; expect failure before integration fixtures/wiring exist.
- [ ] Add consumer-facing usage, Artifact retention notes, and report-bundle handoff contract.
- [ ] Run `bash scripts/verify_toolkit.sh`; expect test suite, coverage, and workflow policy to pass.
- [ ] Commit `test: cover release trend end to end`.

## Execution waves

- Wave 0: Task 1.
- Wave 1: Task 2. Task 3 can be prepared from result fixtures but merges after Task 2.
- Wave 2: Task 4 follows Task 2/3; documentation fixture preparation is independent but must merge after interfaces stabilize.
- Wave 3: Task 5 integration gate.

## Plan self-review

All PRD requirements map to Tasks 1–5. The parser is the only persistence boundary, selector is the only baseline policy boundary, and renderers never receive unvalidated raw data. No task introduces a hosted store, implicit GitHub API fetch, or unbounded automated release action.
