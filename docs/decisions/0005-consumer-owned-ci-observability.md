---
id: ADR-0005
title: Consumer-owned CI 증적을 OpenTelemetry와 관리형 Prometheus·Grafana로 관측한다
status: proposed
date: 2026-10-01
locale: ko
decision_makers: []
related:
  - ADR-0002
  - ADR-0003
  - ADR-0004
affected_paths:
  - .github/workflows/
  - src/pipeline_toolkit/telemetry/
  - src/pipeline_toolkit/compare/
  - docs/prd/
  - docs/reports/
tags:
  - architecture
  - ci
  - observability
  - benchmark
  - prometheus
  - opentelemetry
retrospective: false
---

## 맥락 및 문제 설명

OnMaruBE의 CI·테스트·release benchmark는 GitHub Actions 실행과 Toolkit artifact로 증거를 남기지만, 여러 실행의 추세와 원인 탐색을 한 화면에서 하기 어렵다. 현재 최장 모듈 명령 시간이 workflow critical path처럼 표시될 수 있고, 관측 도구로 CI 실패의 소유권을 이전하면 consumer가 자체 실행을 진단하지 못한다. 불변 증적과 최소 권한을 유지하면서 상세 메트릭·trace·대시보드를 추가해야 한다.

## 결정 요인

* OnMaruBE가 CI trigger, 필수 `verify`, 테스트 명령, 자격 증명, 실패 진단을 계속 소유한다.
* 개별 판정은 GitHub 실행과 versioned manifest에서 재현할 수 있어야 한다.
* 추세·trace 탐색을 추가하되 자체 관측 클러스터 운영과 PR secret 노출을 피한다.

## 검토한 대안

1. 기존 artifact와 정적 보고서만 유지한다. 운영 복잡도는 작지만 실행 간 추세·경보와 trace 탐색이 약하다.
2. Toolkit이 중앙 CI 제어와 자체 Prometheus·trace 저장소·Grafana를 운영한다. 수집 제어는 쉽지만 consumer 소유권·보안 경계와 인프라 운영 부담이 커진다.
3. OnMaruBE가 CI와 전송 자격 증명을 소유하고 Toolkit이 증적 해석과 OTLP 변환 계약을 제공하며 Grafana Cloud의 관리형 Prometheus 호환 메트릭 저장소·trace 저장소·Grafana를 사용한다.

## 결정 결과

선택한 대안: **consumer-owned CI와 Toolkit의 version-pinned 분석 계약을 유지하고, 불변 증적에서 파생한 관측값을 Grafana Cloud로 보낸다.** 주된 이유는 OnMaruBE의 자체 실패 진단과 재현 가능한 판정을 보존하면서 추세·trace 탐색을 추가할 수 있기 때문이다. Grafana Cloud Metrics의 Mimir를 관리형 Prometheus 호환 저장소로 사용하고 PromQL로 조회한다. 별도 Prometheus 서버를 운영하지 않는다.

### 결과 및 영향

* 장점: CI·Gradle·release 지표를 같은 관측 화면에서 비교하고 원본 OnMaruBE 실행·manifest로 돌아갈 수 있다.
* 장점: 관측 백엔드나 exporter 장애가 필수 CI 판정과 과거 release 판정을 바꾸지 않는다.
* 단점: Grafana Cloud의 비용·보존·접근 권한을 운영해야 하고, 완료 후 수집에는 지연이 있다.
* 단점: GitHub Actions 시각에서 만든 CI trace는 사후 재구성한 시간선이며, 실제 Gradle 내부 또는 서비스 요청 trace의 연속성을 보장하지 않는다.

## 구현 제약

* OnMaruBE의 신뢰된 후처리 workflow만 관측 자격 증명을 받는다. PR head 코드 또는 fork artifact의 명령을 권한 있는 문맥에서 실행하지 않고 입력 크기·schema를 제한한다.
* Toolkit 저장소는 consumer source, raw benchmark data, Grafana 자격 증명과 deployment secret을 저장하지 않는다.
* 개별 실행·release 판정의 정본은 consumer가 보존하는 schema-versioned manifest다. Prometheus 메트릭·trace는 파생 데이터다.
* `run_id + run_attempt`를 구분해 중복·부분 수집·재처리를 표시한다. SHA, run ID, test name, 파일 경로를 Prometheus label로 사용하지 않는다.
* 일반 PR은 한 번 검증한다. 개선 실험과 release 비교는 baseline/candidate 각각 동일 조건의 성공 표본 3회를 요구한다. 기존 release 15% 중앙값 회귀의 `approval_hold`는 유지한다. 실패·누락·조건 불일치는 `inconclusive` 또는 별도 failure다. 세 표본만으로 통계적 유의성을 주장하지 않는다.
* 필수 `verify`와 실패 진단은 OnMaruBE의 로그·Job Summary·artifact만으로 수행 가능해야 한다. 관측 전송 실패는 별도 상태와 경보로 기록하고 필수 검사를 뒤집지 않는다.

## 대안별 장단점

### 기존 artifact·정적 보고서 유지

* 장점: 운영과 자격 증명 관리가 단순하다.
* 단점: 실행 간 병목 변화, 결측, 전송 장애와 장기 추세를 지속적으로 탐색하기 어렵다.

### Toolkit 중앙 제어와 자체 관측 클러스터

* 장점: 수집·저장을 세밀하게 제어할 수 있다.
* 단점: consumer의 CI 소유권을 흐리고 Prometheus·trace 저장소의 보안·보존·가용성을 직접 책임져야 한다.

### Consumer-owned CI와 관리형 관측 저장소

* 장점: 기존 ADR-0002·0003·0004의 증적·소유권 경계를 유지한다.
* 단점: 전송 상태와 비용을 감시해야 하며 원본 artifact와 Grafana 보존 기간이 다를 수 있다.

## 확인 방법

* OnMaruBE 실행 하나에서 실패한 job·step·오류 코드·원본 artifact를 Toolkit 저장소 접속 없이 찾는다.
* 재실행·누락·부분 artifact fixture에서 중복 집계와 거짓 성공이 발생하지 않는다.
* staging의 성공·실패 CI 실행을 Grafana 메트릭·CI trace에서 찾고 manifest·원본 Actions 실행으로 왕복한다.
* fork PR에는 관측 secret이 없고, Grafana 장애 중에도 기존 필수 `verify` 결과가 유지된다.
* baseline/candidate 각각 세 유효 표본의 개별 값·중앙값·제외 사유와 release approval hold를 검증한다.

## 재검토 조건

* 관리형 서비스의 비용·보존·보안 요건이 프로젝트 한도를 초과한다.
* GitHub Actions API와 artifact로 필요한 단계 시각·증적을 안정적으로 얻을 수 없다.
* 세 표본의 변동성 때문에 release 판정 오류가 반복되어 반복 횟수나 승인 규칙의 재설계가 필요하다.
