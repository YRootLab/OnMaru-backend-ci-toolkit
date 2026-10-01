# Handoff

Updated: 2026-10-01

## Current work

- Issue: [Toolkit #115](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/115)
- Branch: `feature/115-ci-telemetry` from `origin/develop` (`f3d5f4c`)
- Scope: Actions run/job/step evidence, consumer-local diagnostics, bounded OTLP transformation and CI dashboard contract. Begin with the versioned timeline normalization and missing-data quality states.
- Context: policy [PR #116](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/pull/116) and three-run comparator [PR #117](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/pull/117) are merged. OnMaruBE [PR #544](https://github.com/YRootLab/OnMaru-backend/pull/544) pinned the new Toolkit SHA; release gate wiring remains [OnMaruBE #543](https://github.com/YRootLab/OnMaru-backend/issues/543).
- Done: v1 Actions run/job/step timeline normalizer and quality contract with bounded input, partial pagination, retry attempt identity, and explicit unavailable metrics.
- Verification: `bash scripts/verify_toolkit.sh` passed (168 tests, 4 workflow security checks). Actual OnMaruBE Module Benchmark run `36822854010` normalized 19 jobs without quality issues; observed job window was 712s and sum job work 2158s. These are distinct from workflow elapsed time.
- Next: wire safe consumer-owned post-run collection and diagnostics, then idempotent bounded OTLP export and staging Grafana validation. Do not push directly to `develop`.

## Follow-up work

- [OnMaruBE #543](https://github.com/YRootLab/OnMaru-backend/issues/543): connect the three-run release comparator and approval hold to the consumer release workflow.
- [OnMaruBE #525](https://github.com/YRootLab/OnMaru-backend/issues/525): evaluate affected modules and Gradle cache changes with comparable before/after evidence after observability is in place.

Historical implementation notes remain in Git history and the linked Issues/PRs; this file tracks the current handoff only.
