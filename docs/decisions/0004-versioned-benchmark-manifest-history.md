---
id: ADR-0004
title: 버전별 벤치마크 증적 manifest를 이력 비교의 정본으로 사용한다
status: proposed
date: 2026-09-25
locale: ko
decision_makers: []
related:
  - ADR-0002
  - ADR-0003
affected_paths:
  - src/pipeline_toolkit/contracts/
  - src/pipeline_toolkit/compare/
  - src/pipeline_toolkit/provenance/
  - src/pipeline_toolkit/reports/
  - src/pipeline_toolkit/cli.py
  - .github/workflows/
tags:
  - benchmark
  - release
  - observability
  - provenance
  - architecture
retrospective: false
---

## Context and Problem Statement

Release tags alone cannot identify the code and image actually measured. CI runs also become incomparable when environment, suite, configuration, runner profile, or cache conditions change. A historical comparison must be portable across consumer repositories and must not make a performance claim from incomplete or incompatible evidence.

## Considered Options

* Query GitHub APIs directly as the only source of release history.
* Use GitHub Artifact or Release Asset manifests as the canonical evidence, with an optional local SQLite read cache.
* Make SQLite the canonical history database.

## Decision Outcome

Chosen option: **Use versioned Artifact/Release Asset manifests as canonical evidence, with SQLite limited to a disposable derived cache**, because immutable manifest records preserve release tag, commit SHA, image digest, run conditions, samples, and artifact provenance while allowing core comparison logic to run deterministically from a materialized local directory.

The `previous` baseline selector may only choose an earlier successful manifest with matching environment, suite, configuration hash, and runner profile. An explicit baseline never silently falls back. Missing, failed, incomplete, or incompatible evidence yields `inconclusive` and named reasons.

## Consequences

* Good: results are reproducible, auditable, CI-provider-neutral, and resilient to deleting a local cache.
* Good: reports can distinguish a measured regression from an incompatible or failed execution.
* Bad: callers must retain/download manifests before comparison and establish an Artifact/Release retention policy.
* Bad: a future remote-history adapter must materialize the same manifest contract rather than bypass it.

## Confirmation

* Validate manifests, identity, safe artifact URIs, selection policy, and reason codes with fixtures.
* Run deterministic JSON/Markdown/HTML/Job Summary rendering tests and an end-to-end local history CLI fixture.
* Run `bash scripts/verify_toolkit.sh` and workflow security validation before merge.

## Revisit Triggers

* GitHub Artifact retention cannot satisfy the required historical period.
* The manifest schema cannot represent a consumer's runner or deployment identity.
* A hosted query service is required for cross-repository reporting at a scale where local manifest materialization is no longer practical.
