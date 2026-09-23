---
id: ADR-0002
title: 파이프라인 벤치마크를 위한 버전 관리형 통합 증거 모델을 정의한다
status: proposed
date: 2026-09-23
locale: ko
decision_makers: []
related: []
affected_paths:
  - src/pipeline_toolkit/collectors/
  - src/pipeline_toolkit/normalize/
  - src/pipeline_toolkit/analysis/
  - src/pipeline_toolkit/reports/
  - schemas/
  - tests/fixtures/
tags:
  - benchmark
  - schema
  - observability
  - architecture
retrospective: false
---

## 맥락 및 문제 설명

Gradle, pytest, Docker, GitHub Actions, system metrics는 서로 다른 출력 형식과 시간·실행 의미를 가진다. raw output을 report layer에서 직접 해석하면 collector와 분석기가 결합되고 부분 수집·도구 버전·실행 환경을 추적하기 어렵다.

## 검토한 대안

* 도구별 raw output을 report layer가 직접 해석한다.
* 각 collector가 공통의 versioned unified evidence model로 정규화한다.
* 결과를 외부 observability system에 즉시 적재하고 toolkit은 query만 수행한다.

## 결정 결과

선택한 대안: **raw artifact를 보존하고 collector가 versioned unified evidence model로 정규화한다**, 그 이유는 외부 도구와 분석·시각화·보고서를 분리하고 재현 가능한 evidence chain을 제공할 수 있기 때문이다. Model은 schema version, source tool/version, execution identity, environment, timestamp/unit, measurement quality, provenance를 보존한다. 분석·시각화·보고서는 collector raw output을 직접 읽지 않는다.

## 결과 및 영향

* 장점: collector 교체와 새로운 runtime 추가가 쉬워지고 raw-to-report 추적과 결정론적 재처리가 가능하다.
* 단점: schema 설계·검증·migration 비용과 backward compatibility 규율이 필요하다.

## 구현 제약

```yaml
constraints:
  - id: unified-model-versioned
    kind: required_path
    paths: ["src/pipeline_toolkit/normalize/**"]
    pattern: ["schemas/**/*.json"]
    severity: major
    message: "Normalizer changes require a versioned schema."
  - id: reports-use-normalized-model
    kind: forbidden_import
    paths: ["src/pipeline_toolkit/reports/**"]
    pattern: ["collectors", "raw parsers"]
    severity: major
    message: "Reports must not import collector raw parsers."
```

## 확인 방법

* 동일 raw artifact 재처리 결과가 결정론적으로 동일한지 fixture로 검증한다.
* JUnit, pytest, Docker, GitHub Actions 샘플을 schema validation한다.
* missing, partial, estimated, invalid quality 상태와 schema migration을 integration test로 검증한다.

## 재검토 조건

* normalized model이 consumer runtime의 핵심 정보를 표현하지 못한다.
* 외부 observability backend의 query semantics가 toolkit의 독립 실행을 더 이상 허용하지 않는다.
