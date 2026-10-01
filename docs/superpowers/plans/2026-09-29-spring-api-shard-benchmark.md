# Spring API Shard Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Issue #465의 Spring API serial CI 병목을 검증 가능한 shard 병렬 실행으로 전환하고, 동일 실행 조건의 변경 전·후 benchmark evidence와 시각화 가능한 상세 보고서를 남긴다.

**Architecture:** OnMaru-backend가 테스트 분류·명령·caller workflow를 소유하고, OnMaru-backend-ci-toolkit이 immutable reusable workflow의 matrix/fan-in, artifact manifest, 비교 지표를 제공한다. 기준선과 후보는 동일 SHA·runner·Java·cache·명령 identity를 가진 성공 표본만 비교하며, 실패·취소·artifact 누락은 성능 개선으로 해석하지 않는다.

**Tech Stack:** GitHub Actions, Gradle Kotlin DSL, JUnit 5, Testcontainers/PostgreSQL, Node.js benchmark scripts, Python toolkit CLI, Markdown/Mermaid report.

## Global Constraints

- Related issue: `YRootLab/OnMaru-backend#465`; branch: `fix/465-spring-api-shard-benchmark` in both repositories.
- Existing user changes in the parent checkouts must remain untouched; all implementation happens in the isolated worktrees.
- No test deletion, reduced verification scope, `continue-on-error`, deployment secret, or CD permission may be introduced.
- Baseline and candidate evidence require three successful samples under matching commit, runner, cache, toolchain, command, and catalog/config identities.
- Report raw logs, credentials, consumer source, and database payloads are excluded; only sanitized links, counts, timings, and hashes are recorded.
- A measured improvement is reported only when the comparison is `comparable`; otherwise status is `inconclusive`/`측정 중`.

---

### Task 1: Record issue scope and establish reproducible baseline

**Files:**
- Modify: `/Users/yangseunghyeon/Development/OnMaru/.worktrees/onmaru-backend-465/handoff.md`
- Modify: `/Users/yangseunghyeon/Development/OnMaru/OnMaru-BE-pipeline-toolkit/.worktrees/issue-465-toolkit/handoff.md`
- Inspect: `OnMaru-backend/.github/workflows/collect-ci-baseline.yml`, `scripts/benchmark/ci-run-collector.mjs`, `scripts/benchmark/serial-baseline.mjs`

**Interfaces:**
- Consumes: three successful serial CI run IDs and their Actions job metadata.
- Produces: a recorded baseline identity, run links, sanitized `serial-baseline.json`, and a per-step/test inventory.

- [ ] **Step 1: Write the failing contract test for baseline identity completeness**

  Add a Node test under `OnMaru-backend/scripts/test/` that rejects a baseline manifest unless it has exactly three successful runs, commit SHA, runner image, cache state, Java version, command hash, and serial wall-clock samples.

- [ ] **Step 2: Run the focused test to verify the contract fails**

  Run `node --test scripts/test/ci-baseline-workflow.test.mjs` from the backend worktree and confirm the new assertion fails against the current incomplete fixture/contract.

- [ ] **Step 3: Implement only the missing evidence contract**

  Extend the collector/normalizer and workflow summary so the baseline artifact carries sanitized run identity, test command hash, module/test inventory, wall-clock, work time when available, queue time when available, and explicit `resourceEvidence` availability.

- [ ] **Step 4: Run the focused test and collect three real baseline samples**

  Run the backend contract test, then dispatch/observe the existing CI workflow at the selected baseline SHA until three successful, comparable serial runs exist. Use `collect-ci-baseline.yml` to produce the artifact; do not substitute the historical 400–454 second observations as the official baseline.

- [ ] **Step 5: Record the baseline in both handoffs**

  Add the selected SHA, run URLs, runner/toolchain/cache identity, sample count, median, p95, and known exclusions to each worktree's handoff without copying raw logs or secrets.

---

### Task 2: Build and test the Spring API suite inventory

**Files:**
- Create: `OnMaru-backend/scripts/benchmark/spring-api-test-inventory.mjs`
- Create: `OnMaru-backend/scripts/test/spring-api-test-inventory.test.mjs`
- Modify: `OnMaru-backend/.github/benchmark-modules.yml`
- Inspect: `OnMaru-backend/apps/spring-api/src/test/**`, `OnMaru-backend/apps/spring-api/build.gradle.kts`

**Interfaces:**
- Consumes: Spring API test source paths and explicit class/package classification rules.
- Produces: deterministic inventory JSON with `unit-contract`, `postgres-catalog`, `postgres-audio`, and `postgres-other` suites; every existing test class appears exactly once.

- [ ] **Step 1: Add inventory tests before implementation**

  Assert that the inventory has the four required shard IDs, each shard has a non-empty Gradle test filter, all discovered test classes are covered exactly once, PostgreSQL/Testcontainers/Flyway classes are not placed in the unit shard, and a missing classification fails closed.

- [ ] **Step 2: Run the inventory tests and verify RED**

  Run `node --test scripts/test/spring-api-test-inventory.test.mjs`; confirm failure because the inventory generator and shard contract do not yet exist.

- [ ] **Step 3: Implement deterministic classification and inventory output**

  Classify by package/class ownership and PostgreSQL/Testcontainers/Flyway markers, keep contract/web tests in the unit/contract shard when they do not require PostgreSQL, and emit sorted class names plus an explicit unclassified list.

- [ ] **Step 4: Add catalog entries for the four Spring API shards**

  Replace the single `spring-api` heavy command with four consumer-owned commands using Gradle `--tests` filters or a checked-in inventory file. Preserve the existing full-suite fallback for broad Gradle/workflow changes and keep the original full Spring API command as an inventory/coverage verification command.

- [ ] **Step 5: Run inventory and catalog validation**

  Run `node --test scripts/test/spring-api-test-inventory.test.mjs scripts/test/benchmark-contract.test.mjs` and `PYTHONPATH=src python -m pipeline_toolkit.cli module-plan --catalog ../OnMaru/.worktrees/onmaru-backend-465/.github/benchmark-modules.yml` from the toolkit worktree.

---

### Task 3: Connect bounded shard fan-out/fan-in and monitoring evidence

**Files:**
- Modify: `OnMaru-backend/.github/workflows/ci.yml`
- Modify: `OnMaru-backend/.github/workflows/module-benchmark.yml`
- Modify: `OnMaru-backend/.github/workflows/benchmark-release.yml` only if its artifact contract requires the new evidence fields
- Modify: `OnMaru-backend-ci-toolkit/.github/workflows/module-benchmark.yml`
- Modify: `OnMaru-backend-ci-toolkit/tests/test_module_benchmark_workflow.py`
- Create/modify: `OnMaru-backend/scripts/test/spring-api-shard-workflow.test.mjs`

**Interfaces:**
- Consumes: four shard commands and the existing module evidence schema.
- Produces: bounded matrix execution, fail-closed final `verify`, per-shard wall-clock/queue/work/RSS evidence when available, and aggregate critical path plus total workflow wall-clock.

- [ ] **Step 1: Add failing workflow contract tests**

  Assert that all four shards are matrix entries, `max_parallel` remains bounded, aggregate depends on every shard, missing/failed artifacts fail `verify`, and the aggregate report includes shard table, critical path, queue/work/resource availability, and comparison status.

- [ ] **Step 2: Run focused workflow tests and verify RED**

  Run the backend and toolkit focused workflow tests; confirm the new fields and shard topology are absent or incomplete.

- [ ] **Step 3: Implement the minimal fan-out/fan-in changes**

  Keep credentials disabled and permissions read-only, preserve `fail-fast: false`, include run/attempt in concurrency, publish sanitized evidence per shard, and make the aggregate fail when any required shard or artifact is missing.

- [ ] **Step 4: Add monitoring-oriented evidence fields**

  Capture workflow start/end, queue duration if GitHub job timestamps expose it, command wall-clock, critical path, sum of shard work, max RSS where available, test count, failure count, and a `resourceEvidence` flag instead of inventing unavailable CPU/memory values.

- [ ] **Step 5: Run focused toolkit and backend tests**

  Run `pytest -q tests/test_module_benchmark_workflow.py` in the toolkit worktree and `node --test scripts/test/spring-api-shard-workflow.test.mjs scripts/test/module-benchmark-caller.test.mjs` in the backend worktree.

---

### Task 4: Execute candidate benchmark and verify coverage

**Files:**
- Modify: `OnMaru-backend/handoff.md`
- Create: `OnMaru-backend/docs/benchmark/evidence/issue-465/` only with sanitized manifests/summaries permitted by repository policy

**Interfaces:**
- Consumes: the shard implementation and the baseline identity from Task 1.
- Produces: three successful candidate runs, test inventory comparison, shard evidence, and a comparable before/after dataset.

- [ ] **Step 1: Run local RED/GREEN verification before Actions**

  Execute the full affected Gradle test inventory locally with Postgres/Testcontainers available; first confirm the new shard verification fails when a shard is omitted, then confirm all four shards and the original full test command pass.

- [ ] **Step 2: Push the branch and run the benchmark workflow**

  Use the immutable toolkit SHA and the same runner/toolchain/cache policy as the baseline. Collect three successful candidate runs; exclude failed, cancelled, timeout, incomplete, or identity-mismatched runs.

- [ ] **Step 3: Compare test inventory and execution evidence**

  Verify no test class disappeared, no shard silently overlaps another, and PostGIS/Flyway setup cost is visible per shard. Record queue time and resource metrics only when the platform actually exposes them.

- [ ] **Step 4: Run all repository verification**

  Run `bash scripts/verify_toolkit.sh` in the toolkit worktree and the backend's CI-equivalent Java, contract, benchmark, and hygiene verification commands. Capture exit codes and test counts.

---

### Task 5: Produce the detailed visual benchmark and monitoring report

**Files:**
- Create: `OnMaru-backend/docs/reports/2026-09-29-issue-465-spring-api-shard-benchmark.md`
- Modify: `OnMaru-backend/docs/reports/README.md` if the repository index requires it
- Reference: `OnMaru-backend-ci-toolkit/docs/reports/prompts/detailed-technical-report.md`

**Interfaces:**
- Consumes: sanitized baseline/candidate manifests, run URLs, inventory diff, workflow evidence, and verification results.
- Produces: Korean Markdown report with evidence tables, Mermaid before/after topology, shard timing bar chart in Mermaid or a compact table, monitoring metric definitions, improvement calculation, and explicit inconclusive limits.

- [ ] **Step 1: Add report acceptance tests**

  Assert that the report contains conclusion vs uncertainty, evidence-quality table, before/after Mermaid with at most seven nodes, shard/critical-path/wall-clock/queue/resource fields, failure exclusions, reproducible commands, and no secret/raw log patterns.

- [ ] **Step 2: Run the report contract test and verify RED**

  Confirm the report is absent or missing the required evidence sections.

- [ ] **Step 3: Write the report from measured facts only**

  Calculate median and p95 only from comparable successful samples, show `delta_seconds = after - before` and `improvement_percent = (before - after) / before * 100`, distinguish measurement from interpretation, and mark absent CPU/memory data as unavailable.

- [ ] **Step 4: Add visualizations**

  Include a serial-to-shard Mermaid flow, a compact before/after timing table with proportional bars, and a monitoring timeline showing queue → setup → shard execution → aggregate → verify. Use labels and units so the visual remains accessible without color.

- [ ] **Step 5: Run report and security verification**

  Run the report contract test, `git diff --check`, secret/raw-log scans, and the complete repository verification suites. Only then state the measured improvement or `inconclusive` result.

---

## Self-review checklist

- [ ] Baseline has three comparable successful samples.
- [ ] Four Spring API shards are explicit and inventory-complete.
- [ ] Postgres/Testcontainers/Flyway costs are measured rather than hidden.
- [ ] Matrix fan-out is bounded and final `verify` is fail-closed.
- [ ] Queue/work/wall-clock/critical-path/resource availability are distinguished.
- [ ] Candidate has three comparable successful samples or the report says `inconclusive`.
- [ ] Report follows `docs/reports/prompts/detailed-technical-report.md` and contains visualizations.
- [ ] No secrets, raw consumer source, or unsupported performance claims are committed.
