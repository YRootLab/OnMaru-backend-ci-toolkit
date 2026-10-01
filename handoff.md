# Handoff

Updated: 2026-10-01

## Current work

- Issue: [Toolkit #113](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/113)
- Branch: `docs/113-ci-observability-policy`
- PR: [#116](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/pull/116) → `develop`
- Scope: consumer-owned CI benchmark observability policy, three-run comparison rule, ADR-0005, and generated ADR index.
- Done: final report, ADR, PRD, rollout guidance, and work graph aligned to three valid comparable runs. Toolkit [PR #117](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/pull/117) has since merged the comparison code into `develop`.
- Verification: after merging `origin/develop`, `bash scripts/verify_toolkit.sh` passed (164 tests, 4 workflow security checks); ADR validation passed (5/5), the ADR index was regenerated, JSON parsed, and `git diff --check` passed. PR CI must pass on the updated head.
- Next: complete review of #116 and merge through a PR. No direct push to `develop`.

## Follow-up work

- [Toolkit #114](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/114): code is merged; [OnMaruBE #542](https://github.com/YRootLab/OnMaru-backend/issues/542) must pin the new immutable Toolkit SHA and verify the consumer workflow before declaring the three-run policy operational there.
- [Toolkit #115](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/115): collect Actions timeline evidence, export bounded OpenTelemetry signals, and verify Prometheus/Grafana dashboards without changing the consumer's required CI verdict.
- [OnMaruBE #525](https://github.com/YRootLab/OnMaru-backend/issues/525): evaluate affected modules and Gradle cache changes with comparable before/after evidence after observability is in place.

Historical implementation notes remain in Git history and the linked Issues/PRs; this file tracks the current handoff only.
