---
id: ADR-0003
title: Consumer-configured reusable workflow로 모듈별 병렬 CI benchmark를 제공한다
status: proposed
date: 2026-09-23
locale: ko
decision_makers: []
related:
  - ADR-0002
affected_paths:
  - .github/workflows/
  - src/pipeline_toolkit/
  - docs/prd.md
  - docs/prd/
  - docs/to-be/
tags:
  - architecture
  - benchmark
  - ci
  - github-actions
  - security
retrospective: false
---

## 맥락 및 문제 설명

OnMaruBE는 Spring Gradle multi-module과 FastAPI를 함께 포함하며, 현재 단일 `verify` job에서 다수의 모듈 테스트를 순차 실행한다. 실제 service source, test command, deployment environment, secret은 consumer repository가 소유하지만, evidence 정규화, 비교, DAG 분석, report는 여러 consumer가 재사용할 수 있다. CI 가속을 위해 toolkit을 application runtime dependency로 넣거나 deployment 권한을 toolkit에 집중하면 runtime 결합과 secret 경계가 무너진다.

## 검토한 대안

* OnMaruBE repository 안에서 catalog, matrix, collector, report, comparison을 모두 구현한다.
* OnMaruBE application이 toolkit Python module을 runtime dependency로 import한다.
* Consumer가 catalog와 caller workflow를 소유하고, toolkit은 version-pinned reusable workflow, CLI, evidence/comparison/report engine을 제공한다.

## 결정 결과

선택한 대안: **consumer-configured reusable workflow**. OnMaruBE는 `.github/benchmark-modules.yml`, source-specific command, deployment environment, secret, promotion 권한을 소유한다. Toolkit은 `workflow_call` interface, catalog validation/planning, evidence normalization, comparison, DAG/critical-path analysis, report, recommendation engine을 제공한다. Consumer workflow는 toolkit release tag 또는 immutable commit SHA를 지정해 호출하며 toolkit source를 runtime dependency로 import하지 않는다.

PR mode는 read-only source access으로 affected module을 병렬 실행하고 10% 초과 회귀를 warning으로 표시한다. develop mode는 full-suite evidence를 저장한다. release mode는 동일 조건의 5회 유효 run 중앙값을 비교하고 15% 초과 회귀를 approval hold로 분류한다. 조건 불일치, artifact 누락, 표본 부족은 regression이 아니라 `inconclusive`다.

## 결과 및 영향

* 장점: consumer domain과 reusable analysis platform의 결합을 낮추고, module 증가를 catalog 변경으로 수용하며, Git Flow의 PR/develop/release 검증을 같은 engine으로 실행할 수 있다.
* 장점: PR benchmark는 deployment secret 없이 실행되고, deployment/promotion authority는 consumer repository에 남는다.
* 단점: 두 repository의 semantic version, workflow interface, artifact manifest를 호환성 있게 관리해야 한다.
* 단점: GitHub Artifact는 단기 evidence 용도이며, release comparison은 immutable GitHub Release asset/manifest 보존 규율이 필요하다.

## 구현 제약

```yaml
constraints:
  - id: consumer-owns-runtime-and-secrets
    kind: forbidden_import
    paths: ["src/pipeline_toolkit/**"]
    pattern: ["onmaru application runtime", "consumer deployment secrets"]
    severity: major
    message: "Toolkit must not contain consumer runtime or deployment-secret integration."
  - id: reusable-workflow-is-versioned
    kind: required_path
    paths: [".github/workflows/**"]
    pattern: ["workflow_call"]
    severity: major
    message: "Reusable CI integration must declare a workflow_call contract."
```

## 확인 방법

* Catalog fixture에서 direct, reverse dependency, common-path full fallback을 검증한다.
* Consumer fixture workflow가 fork PR에서 deployment secret 없이 실행되는지 검증한다.
* serial/parallel/module-failure artifact를 이용해 work, wall-clock, critical path와 result classification을 검증한다.
* OnMaruBE caller workflow가 version-pinned toolkit workflow를 호출하고 `verify` fan-in check를 유지하는지 검증한다.

## 재검토 조건

* 여러 consumer가 서로 다른 runner 또는 storage backend를 요구해 workflow interface가 안정적으로 확장되지 못한다.
* GitHub Actions의 artifact retention 또는 cross-workflow access가 release evidence 보존 요구사항을 충족하지 못한다.
* consumer runtime code가 toolkit analysis engine을 직접 필요로 하는 정당한 use case가 생긴다.
