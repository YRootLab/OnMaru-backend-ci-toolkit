# handoff.md

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
