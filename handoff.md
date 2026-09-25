# handoff.md

- **Date**: 2026-09-26 Release Please bootstrap failure 수정 시작
- **Branch**: `fix/87-release-please-bootstrap`
- **Related Issue**: #87 (unblocks #84)
- **Root cause**: master Release Please run 36157571570 ran `verify_toolkit.sh` without the Python/coverage dependencies that regular CI installs from `requirements-ci.txt`.
- **Scope**: release workflow에 CI와 같은 Python bootstrap만 추가하고, setup → install → verify 순서를 contract test로 고정한다.
- **Verification**: RED `PYTHONPATH=src python3 -m pytest -q tests/test_ci_hardening.py` (1 failed); GREEN focused 3 passed; `bash scripts/verify_toolkit.sh` (154 passed, 91% coverage, workflow security 4 workflows passed).

- **Date**: 2026-09-26 develop 누적 Toolkit release 준비
- **Branch**: `release/develop-sync`
- **Related Issue**: #84
- **Scope**: 검증된 develop 누적 변경을 release PR로 master에 승격하고, master의 Release Please 및 develop back-merge 상태를 확인한다. release version/tag는 Release Please가 결정한다.
- **Verification**: release branch에서 `bash scripts/verify_toolkit.sh`, PR `ci`, master push 후 Release Please 상태를 순서대로 확인한다.

- **Date**: 2026-09-26 Toolkit consumer adoption guide 시작
- **Branch**: `docs/82-consumer-adoption-guide`
- **Related Issue**: #82 (extends #31; coordinates OnMaruBE #390)
- **Scope**: Toolkit reusable workflow·CLI와 consumer-owned serial baseline 수집/비교의 책임 경계, immutable SHA caller 예시, evidence 보관 원칙을 README에 기록한다. Consumer source, credential, runtime dependency, CI topology는 변경하지 않는다.
- **Verification**: RED `PYTHONPATH=src python3 -m pytest -q tests/test_readme_adoption.py` (2 failed); GREEN focused 2 passed; `bash scripts/verify_toolkit.sh` (153 passed, 91% coverage, workflow security 4 workflows passed).

- **Date**: 2026-09-25 reusable caller-event guard 수정 시작
- **Branch**: `fix/80-reusable-caller-event`
- **Related Issue**: #80
- **Scope**: caller event와 무관하게 workflow_call 경로의 release trend benchmark가 실행되도록 contract guard를 제거하고 테스트한다.

- **Date**: 2026-09-25 release trend end-to-end validation
- **Branch**: `test/67-release-trend-e2e`
- **Related Issue**: #67 (root #61)
- **Scope**: Verify `previous`, explicit incompatible baseline, failed intermediate evidence, JSON/Markdown/HTML/Job Summary CLI formats, and the read-only reusable workflow convention as one lifecycle.
- **Verification**: `PYTHONPATH=src python3 -m pytest -q tests/test_trend_e2e.py tests/test_trend_cli.py tests/test_trend_render.py` (4 passed); `bash scripts/verify_toolkit.sh` (148 passed, 91% coverage, workflow security passed).


- **Date**: 2026-09-25 release trend comparison foundation
- **Branch**: `docs/release-trend-comparison`
- **Related Issue**: #62 (root #61)
- **Scope**: Record the canonical immutable-manifest storage decision, release trend PRD, approved design, implementation plan, and validated six-issue execution graph. The graph opens #63 → #64 → (#65, #66 in parallel) → #67.
- **Verification**: ADR Toolkit significance score 14/14 (`recommended`); `adr.py validate` checked 4 ADRs with no errors; generated ADR index; work graph validation reported 6 issues with zero errors/warnings; baseline toolkit tests passed (130 tests).


- **Date**: 2026-09-25 report-bundle E2E and CI smoke
- **Branch**: `test/59-report-bundle-e2e-smoke`
- **Related Issue**: #59
- **Scope**: Add a safe report-facts fixture, end-to-end dual-audience CLI test, and GitHub Actions smoke/artifact verification without an AI call or automatic git mutation.
- **Verification**: `python3 -m pytest tests/test_cli.py -q` (7 passed); `bash scripts/verify_toolkit.sh` (130 passed, 90% coverage, workflow security passed); manual runner-equivalent smoke with `PYTHONPATH=src`.

- **Date**: 2026-09-24 report bundle design
- **Branch**: `docs/56-report-bundle-design`
- **Related Issue**: #56
- **Scope**: Define a single-input report bundle that creates deterministic developer and easy-reader drafts/prompts, with an opt-in AI adapter and strict `docs/reports` versus external inbox boundary.
- **Verification**: design placeholder scan and `git diff --check` passed; implementation plan written at `docs/superpowers/plans/2026-09-24-report-bundle-implementation.md`.

- **Date**: 2026-09-24 report publication boundary
- **Branch**: `docs/54-publish-ci-observation-report`
- **Related Issue**: #54
- **Scope**: Publish the evidence-based OnMaru Backend CI observation report and its detailed-report prompt under `docs/reports`. Keep the easy, portfolio-oriented version outside the repository at `OnMaru/inbox/reports`.
- **Verification**: pending `git diff --check` and `bash scripts/verify_toolkit.sh`.

- **Date**: 2026-09-24 matrix concurrency repair
- **Branch**: `fix/52-module-matrix-concurrency`
- **Related Issue**: #52 (blocks OnMaruBE #365)
- **Scope**: module-test concurrency key and its workflow contract test only
- **Verification**: changing the contract from resource profile to module ID reproduced the failure; full toolkit verification required before merge

- **Date**: 2026-09-24 toolkit repository-name migration
- **Branch**: `docs/50-repository-name-migration`
- **Related Issue**: #50 (unblocks OnMaruBE #365)
- **Scope**: reusable workflow internal checkout, active workflow references, PRD/adoption documentation, and work-graph repository metadata only
- **Verification**: contract test changed first and failed against the former checkout name; full toolkit verification is required before merge

Current work:
- Summary: Fix reusable benchmark checkout so a cross-repository caller explicitly supplies the immutable toolkit commit SHA instead of leaking its caller workflow SHA into toolkit checkout.
- Issue/PR: #48 / PR pending
- Branch: fix/48-caller-toolkit-ref

Touched files:
- `.github/workflows/module-benchmark.yml`, `tests/test_module_benchmark_workflow.py`, and this handoff entry only.

Verification:
- RED: `python3 -m pytest tests/test_module_benchmark_workflow.py -q` failed with the missing `toolkit_ref` input and missing `TOOLKIT_REF` validation environment contract.
- GREEN: focused cross-repository workflow fixture suite passed (4 tests).
- Full: pending `bash scripts/verify_toolkit.sh`.

Next step:
- Open a Korean #48 corrective PR into `develop`; do not merge it in this task. OnMaruBE #365 must pass the same immutable SHA through the new required input after this PR merges.

Open risk or decision:
- The reusable workflow rejects anything but a 40-character lowercase hexadecimal Git commit SHA before network checkout. It intentionally does not accept mutable branches or tags.

-
- Summary: Add evidence-linked recommendations that can produce only a restricted, auditable draft-PR payload or an Issue-only payload.
- Issue/PR: #36 / PR pending
- Branch: feature/36-restricted-recommendations

Touched files:
- `src/pipeline_toolkit/recommendations/`, `tests/test_recommendations.py`, and this handoff entry only.

Verification:
- RED: `PYTHONPATH=src python3 -m pytest -q tests/test_recommendations.py` failed with `ModuleNotFoundError` because the recommendations contract did not exist.
- GREEN: focused recommendation contract suite passed (13 tests).
- Full: `bash scripts/verify_toolkit.sh` passed (86 tests, 92% coverage, workflow security verification).

Next step:
- Open a Korean #36 PR into `develop`; do not merge it in this task.

Open risk or decision:
- This package creates declarative payloads only. It never creates, approves, or merges an Issue or PR; all draft remediation requires human review.

- Summary: Correct module benchmark comparability so every performance-eligible sample carries a typed environment/configuration identity.
- Issue/PR: #44 / PR pending
- Branch: fix/44-evidence-environment-identity

Touched files:
- `src/pipeline_toolkit/contracts/module_evidence.py`, `src/pipeline_toolkit/compare/module_benchmark.py`, `tests/test_module_evidence.py`, `tests/test_module_benchmark_comparison.py`, and this handoff entry only.

Verification:
- RED: focused tests failed because `EnvironmentIdentity` and `pipeline_toolkit.compare.module_benchmark` did not exist.
- GREEN: focused environment-identity contract/comparison suite passed (16 tests).
- Full: `bash scripts/verify_toolkit.sh` passed (69 tests, 91% coverage, workflow security verification).

Next step:
- Open a Korean #44 corrective PR into `develop`; do not merge it. #43 must rebase onto this contract before its blocked comparison/report work proceeds.

Open risk or decision:
- Environment identity is required only for complete successful evidence; failed or incomplete evidence remains valid but is never performance eligible.

- Summary: Add deterministic `module-plan` CLI JSON output from the #33 catalog planner.
- Issue/PR: #39 / PR pending
- Branch: feature/39-cli-module-plan

Touched files:
- `src/pipeline_toolkit/cli.py`, `tests/test_cli_module_plan.py`, and this handoff entry only.

Verification:
- RED: `PYTHONPATH=src python3 -m pytest -q tests/test_cli_module_plan.py` failed because `module-plan` was not a recognized command.
- GREEN: the focused subprocess contract suite passed (4 tests).
- Full: `bash scripts/verify_toolkit.sh` passed (53 tests, 91% coverage, workflow security verification).

Next step:
- Open the #39 Korean PR into `develop`; do not merge it in this task.

Open risk or decision:
- Invalid catalogs return exit code 2 with diagnostics only on stderr; unavailable or unmapped diffs safely select the full suite.
- Summary: Compare validated module benchmark samples and render PR warning/release approval-hold reports.
- Issue/PR: #40 / pending
- Branch: feature/40-module-benchmark-reporting
- Verification: focused comparison tests (6 passed); `./scripts/verify_toolkit.sh` (60 passed, 92% coverage, workflow security passed).

- Summary: Define typed module benchmark evidence manifest for comparison-ready provenance.
- Issue/PR: #34 / pending
- Branch: feature/34-module-evidence-manifest

- Summary: Add installable CLI commands and non-root runtime image for consumer adoption.
- Issue/PR: #25 / next PR pending
- Branch: feature/issue-25-cli-runtime

Touched files:
- CLI entrypoint, validate/compare/report commands, console script, Docker runtime, and CLI tests

Next step:
- Merge the P1 CLI/runtime PR after CI.
- Continue operational baseline documentation and dashboard/alert integration.

Open risk or decision:
- GitHub branch protection is not configured yet.
- Full external tool execution is optional; collectors must preserve missing/invalid evidence explicitly.
- GitHub disallows the PR author from approving their own PR; use an independent maintainer or configured bot identity.

Ad hoc requests captured this session:
- [x] Extend `scripts/verify_toolkit.sh` when the Python toolkit implementation lands.
# Issue #35 — reusable module benchmark workflow

- Branch: `feature/35-reusable-module-benchmark`
- Scope owner: `.github/workflows/module-benchmark.yml`, its fixture test, and workflow security validation only.
- Status: fixture contract, workflow security validation, and toolkit verification passed; ready for PR review.
