# Release Trend Comparison PRD

Status: Proposed
Owner: `YRootLab/OnMaru-backend-ci-toolkit`
Related: ADR-0002, ADR-0003
Tracking: #61 (root), #62 (documentation foundation)

## 1. Problem and goal

A single CI run cannot prove that a pipeline became faster. A release tag can also be moved or rebuilt, while a runner, cache state, suite, or resource limit can change between runs. The toolkit therefore needs a release-to-release comparison that retains enough immutable evidence to answer three different questions safely:

1. Is the candidate faster or slower than the comparable previous release?
2. How does the candidate compare with an explicitly selected version?
3. What direction has a metric taken over several comparable releases?

The feature shall expose deterministic JSON, Markdown, HTML, and GitHub Job Summary facts. It shall feed `report-bundle` with validated facts; it shall not let a natural-language renderer infer a performance claim.

## 2. Scope and ownership

The toolkit owns evidence contracts, local manifest reading, baseline selection, comparison, trend rendering, CLI commands, and reusable workflow conventions. A consumer repository owns its release tags, commands, credentials, Artifact retention, deployments, and promotion policy.

GitHub Artifact or Release Asset stores the canonical, immutable manifest and report. A local SQLite file is an optional derived read cache only: deleting it must not lose history and it must never be required by a consumer CI run.

Out of scope for this increment: a hosted database, a dashboard service, automatic production promotion, raw benchmark data committed to Git, or an API token passed from fork pull requests.

## 3. Immutable evidence contract

Each published manifest has `schema_version: "1.0"` and contains a `release`, a `run`, and one or more metrics.

```json
{
  "schema_version": "1.0",
  "release": {
    "repository": "YRootLab/OnMaru-backend",
    "tag": "v1.4.0",
    "commit_sha": "40-lowercase-hex-sha",
    "image_digest": "sha256:..."
  },
  "run": {
    "run_id": "github-12345-attempt-1",
    "status": "success",
    "environment": "staging",
    "suite": "default-backend",
    "config_hash": "sha256:...",
    "runner_profile": "ubuntu-24.04-amd64-4cpu-8192mb-warm",
    "toolkit_version": "0.1.0",
    "artifact_uri": "https://github.com/..."
  },
  "metrics": [{"id": "pipeline.wall_clock", "unit": "seconds", "samples": [491.0, 486.0, 489.0]}]
}
```

The parser rejects an incomplete release identity, duplicate `(run_id, metric.id)` values, non-finite samples, unsupported status, or an Artifact URI with embedded credentials. A failed, cancelled, timeout, partial, missing, invalid, or inconclusive run remains visible in history but contributes no performance samples.

## 4. Comparable baseline policy

`previous` is not simply the nearest version string. The selector sorts successful manifests by release timestamp/version order and selects the latest earlier release whose `environment`, `suite`, `config_hash`, and `runner_profile` exactly equal the candidate. The candidate and baseline must also have distinct immutable release identities.

`--baseline <tag>` resolves that tag exactly. It does not silently fall back to another version. A requested but incompatible baseline produces `inconclusive` with every mismatch reason. No baseline, duplicate tags with conflicting immutable identities, missing metric, or insufficient valid samples is likewise `inconclusive`.

Comparisons use the existing median/delta/threshold policy after the selector has established compatibility. Status is one of `improved`, `regressed`, `unchanged`, or `inconclusive`; failed collection/deployment data is represented separately and never recast as a regression.

## 5. Interfaces

```bash
# Read manifests in a local directory (including downloaded GitHub Artifacts).
pipeline-toolkit trend compare \
  --history-root .pipeline-history \
  --candidate v1.4.0 \
  --baseline previous \
  --metric pipeline.wall_clock \
  --format markdown

# Compare with one specific release, retaining incompatibility evidence.
pipeline-toolkit trend compare \
  --history-root .pipeline-history \
  --candidate v1.4.0 \
  --baseline v1.2.0 \
  --metric pipeline.wall_clock \
  --format json

# Show at most ten comparable historical points ending at the candidate.
pipeline-toolkit trend history \
  --history-root .pipeline-history \
  --candidate v1.4.0 \
  --metric pipeline.wall_clock \
  --last 10 \
  --format job-summary
```

The initial `--history-root` is deliberately filesystem-only. GitHub Actions downloads known release/manifests before invoking the CLI. This makes parsing deterministic and lets any CI provider use the same contract. A later adapter may fetch GitHub data, but it must materialize the same manifest files before selection.

## 6. Output requirements

Every comparison output includes candidate and baseline tag, commit SHA, image digest, run IDs, metric/unit, sample counts, median, absolute delta, relative delta where defined, and status. It names `baseline_strategy` (`previous` or `explicit`) and lists exclusion/incompatibility reasons.

The trend output lists ordered comparable observations only, explicitly reports omitted runs, and does not draw a visual line across a comparability boundary. Markdown and Job Summary use a compact table; HTML uses the same source facts. `report-bundle` receives a `comparable: true` fact only for a non-inconclusive comparison with valid samples.

## 7. GitHub Actions lifecycle

Release mode produces a manifest after the release identity and deployed image digest have been verified. It uploads the manifest and normalized report as an Artifact; a durable release run also attaches them to the Release. Before comparison, the workflow downloads candidate and eligible historical manifests into `history-root` and runs the CLI without secrets beyond the read-only Artifact/Release token required by the caller.

PR mode may compare against a caller-provided local baseline but does not publish durable release history. Fork PRs receive no deployment or publishing credentials. Workflows use minimal permissions and must not auto-commit, auto-approve, or auto-promote.

## 8. Acceptance criteria

- A valid manifest round-trips deterministically; unsafe or incomplete input fails closed.
- `previous` chooses the nearest earlier successful comparable release, never merely the preceding tag.
- Explicit baseline selection preserves an incompatible request as `inconclusive` with reasons.
- Trend output separates comparable points from omitted/incompatible runs and is deterministic across JSON, Markdown, HTML, and Job Summary formats.
- The reusable workflow fixture downloads/uses local manifests, publishes candidate evidence, and passes workflow-security validation.
- CLI, unit tests, end-to-end fixture, and `bash scripts/verify_toolkit.sh` pass before merge.
