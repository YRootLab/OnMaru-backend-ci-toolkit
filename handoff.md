# Handoff

Updated: 2026-10-01

## Current work

- Implementation ready for review: [Toolkit #118](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/118), branch `feature/118-actions-evidence`, isolated worktree `.worktrees/issue-118-actions-evidence`. Attempt-specific pagination, bounded versioned module joins/digests, deterministic identity, duplicate quarantine and consumer-local diagnostics are implemented with test-first coverage. The producer emits attempt identity; legacy critical-path output is declared but empty and module maximum uses `longest_module_duration_seconds`. Workflow wall-clock and DAG critical path remain unavailable.
- #118 verification: focused suite 55 tests; full `bash scripts/verify_toolkit.sh` 212 tests, 92% coverage and 4 workflow security checks on Python 3.9.6. Review follow-up adds expected detect-matrix coverage, current run/attempt/Toolkit identity validation and duplicate/stale quarantine to aggregate, plus explicit module status/exit diagnostics independent of job conclusions. Read-only OnMaruBE run `36822854010`, attempt 1: 19 jobs, 110 steps, complete timing quality, 712s observed window. No consumer raw responses committed. Consumer migration must stop coercing deprecated `critical_path_seconds` to a number and enforce ZIP/download/member bounds before passing JSON bytes; [contract](docs/telemetry/actions-timeline.md) documents the boundary. No push, merge, Issue closure or consumer changes performed.
- Wave 0 local stack: [Toolkit #119](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/119), branch `feature/119-local-observability`. Implemented pinned localhost-only Collector/Prometheus/Tempo/Grafana, capped disposable tmpfs volumes, bidirectional datasource links, configuration contracts and fixture/query smoke. Guide: `docs/telemetry/local-stack.md`.
- #119 verification: `bash scripts/verify_toolkit.sh` passed (176 tests, 91% coverage, 4 workflow security checks); 8 local contracts run without Docker. Compose `config --quiet`, four container healthchecks, readiness/provisioning smoke and metric + trace + matching exemplar query smoke passed on Docker Desktop ARM64. Docker Desktop's stalled credential helper was bypassed with an isolated empty Docker config; no user credentials/configuration were changed. Temporary fixture containers/network/volumes are cleaned after verification; no push, merge or Issue closure was performed.
- Issue: [Toolkit #115](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/115)
- Branch: `feature/115-ci-telemetry` from `origin/develop` (`f3d5f4c`)
- Scope: P0 Actions run/job/step evidence and consumer-local diagnostics, P1 bounded OTLP/Prometheus/Grafana observability, and the P3 on-demand benchmark workflow/CLI/Agent Skill contract.
- Context: policy [PR #116](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/pull/116) and three-run comparator [PR #117](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/pull/117) are merged. OnMaruBE [PR #544](https://github.com/YRootLab/OnMaru-backend/pull/544) pinned the new Toolkit SHA; release gate wiring remains [OnMaruBE #543](https://github.com/YRootLab/OnMaru-backend/issues/543).
- Done: v1 Actions run/job/step timeline normalizer and quality contract with bounded input, partial pagination, retry attempt identity, and explicit unavailable metrics. #115 was promoted to the Root control plane with nine native Sub-Issues and one cross-owner Agent Toolkit issue.
- Verification: `bash scripts/verify_toolkit.sh` passed (168 tests, 4 workflow security checks). Actual OnMaruBE Module Benchmark run `36822854010` normalized 19 jobs without quality issues; observed job window was 712s and sum job work 2158s. These are distinct from workflow elapsed time.
- Design: general CI observation does not repeat tests. Pipeline improvements use an explicit feature-vs-develop experiment with three valid runs per side. P3 provides the consumer workflow, Toolkit CLI, and Agent Toolkit `ci-benchmark-experiment` skill.
- Issue graph: Wave 0 [Toolkit #118](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/118) and [#119](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/119); Wave 1 #120; Wave 2 #121 and OnMaruBE #554; Wave 3 OnMaruBE #555; Wave 4 #122; Wave 5 OnMaruBE #556 and Agent Toolkit #58. Existing OnMaruBE #543 is the independent P2 release track.
- Next: begin Wave 0 in separate worktrees. Continue the current evidence code under #118 and build the local observability stack under #119. Do not push directly to `develop`.

## Follow-up work

- [OnMaruBE #543](https://github.com/YRootLab/OnMaru-backend/issues/543): connect the three-run release comparator and approval hold to the consumer release workflow.
- [OnMaruBE #525](https://github.com/YRootLab/OnMaru-backend/issues/525): evaluate affected modules and Gradle cache changes with comparable before/after evidence after observability is in place.

Historical implementation notes remain in Git history and the linked Issues/PRs; this file tracks the current handoff only.
