# handoff.md

Current work:
- Summary: Implement release/deployment identity and digest matching contracts.
- Issue/PR: #4 / next PR pending
- Branch: feature/issue-4-release-evidence-contracts

Touched files:
- Deployment contract, release identity comparison, digest/tag validation, and tests

Next step:
- Merge the W2 PR after CI and verify Issue #4 closes automatically.
- Continue remaining comparison and consumer integration after merge.

Open risk or decision:
- GitHub branch protection is not configured yet.
- Full external tool execution is optional; collectors must preserve missing/invalid evidence explicitly.
- GitHub disallows the PR author from approving their own PR; use an independent maintainer or configured bot identity.

Ad hoc requests captured this session:
- [x] Extend `scripts/verify_toolkit.sh` when the Python toolkit implementation lands.
