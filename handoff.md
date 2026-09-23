# handoff.md

Current work:
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
