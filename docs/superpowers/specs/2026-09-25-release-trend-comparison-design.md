# Release trend comparison design

Status: approved by the requester on 2026-09-25.  
Related PRD: `docs/prd/release-trend-comparison.md`
Tracking: #61

## Decision

Release evidence manifests are the canonical historical input. GitHub Artifacts and Release Assets preserve those manifests; a local SQLite index is optional, disposable acceleration. Comparisons resolve release tags to immutable tag, commit SHA, and image digest before evaluating samples.

## Components

| Component | Responsibility | Does not do |
| --- | --- | --- |
| `trend.manifest` | Parse and validate versioned manifest files | Fetch GitHub data or write a database |
| `trend.catalog` | Discover manifest files below a supplied history root | Treat filenames as release identity |
| `trend.selector` | Resolve candidate, explicit baseline, and safe `previous` baseline | Change a requested baseline silently |
| `trend.service` | Produce comparison/trend facts from comparable samples | Infer success from a failed run |
| `trend.render` | Render JSON/Markdown/HTML/Job Summary deterministically | Invent explanatory claims |
| CLI/workflow adapter | Materialize manifests, call the service, publish outputs | Hold consumer deployment credentials |

## Flow

```text
GitHub Artifact / Release Asset -> local history root -> manifest validation
-> identity + comparability selection -> statistics -> deterministic renderers
-> report-bundle facts / Job Summary
```

## Failure model

Invalid history is surfaced as a named rejected record. Missing, failed, or incompatible data produces `inconclusive`; it does not become an empty successful comparison. The only valid performance labels are the existing comparison statuses and only when both sides have comparable, sufficient samples.

## Test boundaries

Manifest parsing, baseline selection, rendering, and CLI/workflow wiring have separate fixtures and tests. The final end-to-end fixture covers a candidate, a comparable previous version, a requested incompatible version, and an omitted failed run.
