# handoff.md

Current work:
- Summary: Implement W7 secure reusable workflow and OnMaru adoption contract.
- Issue/PR: #9 / next PR pending
- Branch: feature/issue-9-secure-workflow

Touched files:
- Workflow policy checker, image digest verification, adoption contract documentation, fixtures, and tests

Next step:
- Obtain an independent maintainer review for the W7 PR.
- Continue remaining production consumer integration after review.

Open risk or decision:
- GitHub branch protection is not configured yet.
- Full external tool execution is optional; collectors must preserve missing/invalid evidence explicitly.
- GitHub disallows the PR author from approving their own PR; use an independent maintainer or configured bot identity.

Ad hoc requests captured this session:
- [x] Extend `scripts/verify_toolkit.sh` when the Python toolkit implementation lands.
