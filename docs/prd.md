# onmaru-modular-backend-pipeline-toolkit 설계 및 구현

당신은 Senior Build Infrastructure / Developer Productivity / CI/CD Platform Engineer다.

새로운 GitHub Repository를 설계하고 구현한다.

```text
YRootLab/onmaru-modular-backend-pipeline-toolkit

```

이 repository는 단순한 CI 실험용 Lab이 아니다.

Spring Boot + Gradle Multi-Module + FastAPI와 같이 여러 runtime과 module이 결합된 backend repository에서 CI/CD pipeline을 **측정하고, 분석하고, 최적화하고, 시각화하고, 개선 효과를 보고서로 증명하기 위한 reusable toolkit**이다.

OnMaruBE consumer의 모듈별 병렬 CI, baseline benchmark, release gate, remediation 정책의 canonical 상세 요구사항은 [OnMaruBE 모듈별 병렬 CI·Benchmark Control Plane PRD](prd/onmarube-parallel-ci-benchmark.md)에 둔다.

---

# 프로젝트의 핵심 철학

이 프로젝트의 핵심 흐름은 다음과 같다.

```text
Inspect
  ↓
Measure
  ↓
Collect
  ↓
Normalize
  ↓
Analyze
  ↓
Compare
  ↓
Visualize
  ↓
Report
  ↓
Optimize

```

단순히 CI를 빠르게 실행하는 것이 목적이 아니다.

```text
Before
↓
정확하게 측정

Bottleneck
↓
병목 분석

Change
↓
병렬화 / selective testing / cache 최적화

After
↓
동일 조건 재측정

Evidence
↓
시각화 + 정량 보고서

```

까지 하나의 lifecycle로 제공하는 것이 목적이다.

---

# Consumer와 Toolkit의 경계

실제 서비스 repository:

```text
OnMaru-backend

```

가 보유하는 것은:

```text
실제 Spring code
실제 FastAPI code
실제 test
실제 Testcontainers
실제 Dockerfile
실제 Gradle dependency graph
실제 CI/CD pipeline

```

이다.

Toolkit은 이를 복사하지 않는다.

Toolkit이 담당하는 것은:

```text
repository inspection
dependency graph analysis
affected test detection
benchmark orchestration
metrics collection
metrics normalization
statistical comparison
pipeline DAG analysis
critical path analysis
visualization
report generation
regression detection

```

이다.

---

# Open Source First

이미 잘 만들어진 benchmark/test 도구를 재구현하지 않는다.

Toolkit은 각 도구를 실행하고 결과를 수집하여 하나의 model로 통합한다.

## Java / Spring / Gradle

```text
JUnit XML
Gradle Profiler
Testcontainers
JMH

```

## Python / FastAPI

```text
pytest
pytest --durations
pytest-xdist
pytest-benchmark

```

## Runtime / Load

```text
k6

```

## System

```text
/usr/bin/time -v

```

## CI/CD

```text
GitHub Actions API
Docker BuildKit metadata

```

Toolkit의 핵심 가치는 이 도구들을 대체하는 것이 아니다.

```text
External Tool
      ↓
Collector
      ↓
Normalizer
      ↓
Unified Benchmark Model

```

을 제공하는 것이다.

---

# 전체 Architecture

```text
                  Consumer Repository
                    OnMaru-backend
                           │
             ┌─────────────┼─────────────┐
             │             │             │
          Gradle         pytest        Docker
             │             │             │
       JUnit XML      JUnit XML      BuildKit
             │             │             │
       Gradle Profiler  durations         │
             │             │             │
             └─────────────┼─────────────┘
                           │
                           ▼
                  Pipeline Toolkit
                           │
                     Collectors
                           │
                           ▼
                     Normalizer
                           │
                           ▼
                Unified Metric Model
                           │
              ┌────────────┼────────────┐
              │            │            │
          Analyzer      Comparator    DAG Engine
              │            │            │
              └────────────┼────────────┘
                           │
                           ▼
                    Visualization
                           │
                           ▼
                       Reports

```

---

# 권장 Directory Structure

```text
onmaru-modular-backend-pipeline-toolkit/
│
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
│
├── src/
│   └── pipeline_toolkit/
│       │
│       ├── cli.py
│       │
│       ├── config/
│       │   ├── loader.py
│       │   ├── model.py
│       │   └── validation.py
│       │
│       ├── inspect/
│       │   ├── repository.py
│       │   ├── gradle.py
│       │   └── python.py
│       │
│       ├── git/
│       │   ├── diff.py
│       │   └── changed_files.py
│       │
│       ├── graph/
│       │   ├── model.py
│       │   ├── gradle.py
│       │   └── reverse_dependencies.py
│       │
│       ├── affected/
│       │   ├── engine.py
│       │   ├── spring.py
│       │   ├── python.py
│       │   └── fallback.py
│       │
│       ├── runners/
│       │   ├── command.py
│       │   ├── gradle.py
│       │   ├── pytest.py
│       │   ├── docker.py
│       │   └── k6.py
│       │
│       ├── collectors/
│       │   ├── junit.py
│       │   ├── pytest.py
│       │   ├── gradle_profiler.py
│       │   ├── system.py
│       │   ├── github_actions.py
│       │   ├── docker.py
│       │   └── k6.py
│       │
│       ├── normalize/
│       │   ├── benchmark.py
│       │   ├── tests.py
│       │   └── pipeline.py
│       │
│       ├── analysis/
│       │   ├── bottleneck.py
│       │   ├── statistics.py
│       │   ├── regression.py
│       │   ├── efficiency.py
│       │   └── recommendations.py
│       │
│       ├── pipeline/
│       │   ├── dag.py
│       │   ├── critical_path.py
│       │   └── concurrency.py
│       │
│       ├── compare/
│       │   ├── benchmark.py
│       │   ├── baseline.py
│       │   └── delta.py
│       │
│       ├── visualization/
│       │   ├── timeline.py
│       │   ├── waterfall.py
│       │   ├── bars.py
│       │   ├── trend.py
│       │   ├── heatmap.py
│       │   ├── dependency_graph.py
│       │   ├── critical_path.py
│       │   └── dashboard.py
│       │
│       ├── reports/
│       │   ├── model.py
│       │   ├── markdown.py
│       │   ├── html.py
│       │   ├── github_summary.py
│       │   └── json_report.py
│       │
│       └── github/
│           ├── api.py
│           └── workflow_metrics.py
│
├── resources/
│   ├── gradle/
│   │   └── export-project-graph.init.gradle.kts
│   │
│   └── report/
│       └── templates/
│
├── schemas/
│   ├── pipeline-config.schema.json
│   ├── benchmark.schema.json
│   └── report.schema.json
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── examples/
│   ├── onmaru/
│   └── generic-spring-fastapi/
│
├── docs/
│   ├── architecture.md
│   ├── benchmarking.md
│   ├── visualization.md
│   ├── reports.md
│   ├── affected-testing.md
│   └── adoption.md
│
└── .github/
    ├── actions/
    └── workflows/

```

---

# Unified Benchmark Model

모든 benchmark 결과를 하나의 공통 model로 변환한다.

예:

```json
{
  "schemaVersion": 1,

  "stage": "test",
  "runtime": "jvm",
  "scope": "integration",

  "name": "spring-api",

  "startedAt": "...",
  "endedAt": "...",

  "durationMs": 153220,

  "cpu": {
    "userMs": 120000,
    "systemMs": 19000
  },

  "memory": {
    "maxRssKb": 1843200
  },

  "tests": {
    "executed": 64,
    "failed": 0,
    "skipped": 0
  },

  "exitCode": 0
}

```

---

# Pipeline Stage Model

다음을 기본 stage type으로 지원한다.

```text
checkout

setup

compile

unit-test

integration-test

contract-test

evaluation

lint

typecheck

package

docker-build

security-scan

migration

deploy

smoke-test

load-test

```

사용자 정의 stage도 지원할 수 있도록 설계한다.

---

# Benchmark CLI

최소 다음 command를 지원한다.

```bash
pipeline-toolkit inspect

```

```bash
pipeline-toolkit affected

```

```bash
pipeline-toolkit benchmark

```

```bash
pipeline-toolkit benchmark suite

```

```bash
pipeline-toolkit compare

```

```bash
pipeline-toolkit analyze

```

```bash
pipeline-toolkit visualize

```

```bash
pipeline-toolkit report

```

최종적으로:

```bash
pipeline-toolkit benchmark suite \
  --config .pipeline/pipeline.yml

```

하나로 전체 benchmark pipeline을 수행할 수 있어야 한다.

---

# Benchmark Suite

전체 benchmark는 예를 들어 다음을 수행한다.

```text
Spring Unit Test
        ↓
Spring Integration Test

FastAPI Unit Test
        ↓
FastAPI Integration Test

Contract Validation

AI Evaluation

Docker Spring Build

Docker FastAPI Build

Container Security Scan

Migration Gate

Deployment

Smoke Test

```

이들이 실제 CI에서는 serial인지 parallel인지도 기록한다.

---

# 중요한 개념: Work Duration vs Wall-clock

반드시 다음 둘을 구분한다.

```text
Work Duration

```

각 작업 시간을 단순 합한 값.

그리고:

```text
Pipeline Wall-clock

```

실제 개발자가 기다린 시간.

예:

```text
Spring Test      180 sec
Python Test      120 sec
Contract Test     60 sec

```

동시에 실행되었다면:

```text
Total Work
=
360 sec

```

이지만:

```text
Wall-clock
≈
180 sec

```

일 수 있다.

보고서에 반드시 둘을 별도로 표시한다.

---

# Critical Path Analysis

CI/CD 최적화에서 가장 중요한 분석 중 하나다.

Pipeline DAG:

```text
             Spring Test
            /
Detect ────┼── Python Test
            \
             Contract
                 │
                 ▼
                Gate
                 │
                 ▼
               Build
                 │
                 ▼
               Deploy

```

각 node에:

```text
start
end
duration
dependency

```

를 기록한다.

DAG longest-path를 이용해 critical path를 계산한다.

예:

```text
Critical Path

detect
→ spring-test
→ gate
→ spring-build
→ deploy
→ smoke

Total: 483 seconds

```

---

# Visualization은 핵심 기능이다

Visualization을 report의 장식으로 생각하지 않는다.

성능 병목을 사람이 빠르게 이해하기 위한 분석 도구로 설계한다.

최소 다음 visualization을 제공한다.

---

# Visualization 1 — Pipeline Timeline

가장 중요한 visualization이다.

GitHub Actions 실행 흐름을 시간축으로 표현한다.

예:

```text
0s                                                    500s

Spring Test     ██████████████████████
Python Test     ███████████████
Contract        ██████

                              Build Spring ██████████
                              Build AI     ███████

                                           Deploy █████

```

이를 통해 다음을 바로 확인할 수 있다.

```text
어떤 작업이 병렬인지

어디에서 기다리고 있는지

어떤 job이 critical path인지

idle gap이 있는지

```

HTML report에서는 interactive tooltip을 제공하는 것을 고려한다.

---

# Visualization 2 — Before / After Comparison

Baseline과 optimized pipeline을 나란히 비교한다.

예:

```text
Pipeline Wall-clock

Baseline       █████████████████████████ 831s

Parallel       ███████████████           501s

Affected       ██████                    181s

```

각 개선 단계의:

```text
absolute difference

percentage reduction

```

를 표시한다.

---

# Visualization 3 — Stage Breakdown

전체 pipeline 시간이 어디에서 소비되는지 보여준다.

예:

```text
Testing          46%
Docker Build     24%
Setup            12%
Deployment       10%
Other             8%

```

단 parallel pipeline에서는 stage duration 합계와 wall-clock이 다르므로 명확하게 표시한다.

---

# Visualization 4 — Slowest Modules

Spring:

```text
spring-api      █████████████ 153s

journey         █████          61s

catalog         ███            33s

```

FastAPI:

```text
retrieval       █████████      91s

screenhanok     █████          51s

```

---

# Visualization 5 — Slowest Tests

JUnit XML과 pytest report를 통해:

```text
Top 20 Slowest Tests

```

를 출력한다.

예:

```text
MigrationIntegrationTest       32.1s

JourneyRunTest                 18.4s

ScreenHanokResearchTest        16.9s

```

---

# Visualization 6 — CPU vs Wall-clock

병렬화를 하면 CPU 사용량이 증가할 수 있다.

따라서 다음 관계를 시각화한다.

```text
           Wall-clock       CPU Time

Serial       500s             430s

Parallel     280s             690s

```

즉:

```text
더 많은 CPU를 사용했지만

개발자가 기다리는 시간은 크게 감소

```

했는지 볼 수 있게 한다.

---

# Visualization 7 — Memory Peak

병렬화 단계별:

```text
Serial

Gradle Parallel

pytest xdist

Full Parallel

```

의 peak RSS를 비교한다.

목적은:

```text
성능 개선

vs

runner resource exhaustion

```

trade-off 분석이다.

---

# Visualization 8 — Test Distribution

test duration 분포를 시각화한다.

예:

```text
0-100ms

100-500ms

500ms-1s

1-5s

5s+

```

slow test가 일부 테스트에 집중되는지 판단할 수 있다.

---

# Visualization 9 — Dependency Graph

Gradle project graph를 시각화한다.

예:

```text
catalog
   ↑
 audio
   ↑
spring-api

```

변경된 project를 표시하고 affected project를 강조할 수 있도록 한다.

목적:

```text
왜 이 module의 테스트가 실행되는지

```

설명 가능하게 하는 것이다.

---

# Visualization 10 — Affected Testing Result

예:

```text
Changed

modules/catalog

↓

Affected

modules/catalog
modules/audio
apps/spring-api

↓

Skipped

identity
community
journey
operations

```

를 report에 표시한다.

---

# Visualization 11 — Cache Effectiveness

Gradle / uv / Docker cache의 효과를 보여준다.

예:

```text
Cold

Gradle       180s
Docker       140s

Warm

Gradle        61s
Docker        39s

```

---

# Visualization 12 — Historical Trend

여러 CI run의 결과를 저장하면 다음 trend를 제공한다.

```text
Pipeline Duration

Sep 20     810s

Sep 21     790s

Sep 22     530s

Sep 23     491s

```

단 Git repository 자체에 모든 raw result를 영구 저장하지 않는다.

artifact 또는 별도 benchmark storage 활용을 고려한다.

---

# Visualization 구현 기술

초기 버전에서는 Python 기반 rendering을 사용한다.

추천:

```text
matplotlib

```

optional:

```text
Plotly

```

HTML interactive report가 필요하면 Plotly 사용을 검토한다.

원칙:

```text
PNG
=
GitHub artifact / README / Markdown

HTML
=
interactive detailed report

```

두 output을 분리할 수 있도록 한다.

---

# Dashboard Report

최종 HTML report는 다음 구조를 권장한다.

```text
Pipeline Benchmark Report

Executive Summary

│
├── Wall-clock
├── Improvement
├── Critical Path
└── Regression Status


Pipeline Timeline


Before / After


Stage Breakdown


Test Performance

├── Spring modules
├── FastAPI modules
└── Slow tests


Resource Usage

├── CPU
└── Memory


Affected Testing

├── changed
├── affected
└── skipped


Cache Analysis


Historical Trend


Recommendations

```

---

# Executive Summary

보고서 첫 화면은 엔지니어가 10초 안에 이해할 수 있어야 한다.

예:

```text
Pipeline Benchmark Summary

Baseline
13m 51s

Current
8m 21s

Improvement
39.7%

Critical Path
Spring Integration Test → Docker Build → Deploy

Slowest Stage
Spring Integration Test — 3m 14s

Peak Memory
3.1 GB

Affected Projects
3 / 11

```

---

# Automated Analysis

Toolkit은 단순 수치만 나열하지 않는다.

명확하게 증명 가능한 범위에서 자동 분석한다.

예:

```text
Spring integration tests account for
38% of the critical path.

```

```text
Python tests use only 22% of pipeline
wall-clock because they overlap with
Spring tests.

```

```text
Docker builds account for 31% of
post-test critical path.

```

추측을 하지 않는다.

수집된 metric으로 계산 가능한 것만 출력한다.

---

# Regression Detection

baseline과 비교하여 다음 조건을 지원한다.

예:

```yaml
regression:

  pipeline:
    threshold_percent: 10

  spring_test:
    threshold_percent: 15

```

candidate가 threshold를 초과하면:

```text
Performance Regression Detected

```

를 report에 표시한다.

처음부터 CI fail gate로 강제하지 않는다.

초기 버전은 warning/report만 제공하고 안정화 후 gate 사용을 지원한다.

---

# Performance Efficiency Metric

단순히 wall-clock만 비교하지 않는다.

예를 들어:

```text
Wall-clock

500s → 250s

```

가 되었지만:

```text
CPU

400s → 1600s

```

가 될 수도 있다.

따라서 다음을 함께 보고한다.

```text
Latency improvement

Resource increase

Parallel efficiency

```

특정 하나의 custom score로 지나치게 단순화하지 않는다.

원시 지표도 항상 같이 보여준다.

---

# Artifact Structure

한 실행의 산출물:

```text
pipeline-benchmark/

├── raw/
│   ├── junit/
│   ├── pytest/
│   ├── gradle-profiler/
│   ├── github/
│   ├── docker/
│   └── k6/
│
├── normalized/
│   ├── stages.json
│   ├── tests.json
│   └── pipeline.json
│
├── charts/
│   ├── timeline.png
│   ├── comparison.png
│   ├── stages.png
│   ├── modules.png
│   ├── resources.png
│   └── cache.png
│
└── report/
    ├── report.md
    └── report.html

```

---

# GitHub Job Summary

HTML report만 만들지 않는다.

PR에서는 GitHub Actions 화면에서 바로 볼 수 있도록:

```text
$GITHUB_STEP_SUMMARY

```

에 요약을 출력한다.

포함:

```text
Baseline vs Current

Pipeline Duration

Critical Path

Slowest Stages

Affected Projects

Regression Status

Artifact Link

```

---

# 보고서는 Evidence여야 한다

보고서에 다음과 같은 표현을 사용하지 않는다.

```text
"훨씬 빨라졌다"

"최적화되었다"

"효율적이다"

```

대신:

```text
Pipeline wall-clock decreased
from 831s to 501s (-39.7%).

Peak RSS increased
from 1.9GB to 2.8GB (+47.4%).

```

처럼 evidence 기반으로 작성한다.

---

# 향후 Observability 연동

Toolkit 내부 metric model은 추후 다음으로 export할 수 있도록 설계한다.

```text
OpenTelemetry

Prometheus

Grafana

```

예:

```text
ci.pipeline.duration

ci.stage.duration

ci.test.duration

ci.affected.count

ci.cache.hit

```

단 high-cardinality 값을 metric label로 남발하지 않는다.

다음과 같은 값은 artifact/report에서 다룬다.

```text
commit SHA

individual test name

full file path

```

---

# CLI 최종 목표

예:

```bash
pipeline-toolkit benchmark suite \
  --config .pipeline/pipeline.yml \
  --output ./benchmark

```

이 한 명령으로:

```text
inspect

run

collect

normalize

analyze

visualize

report

```

까지 완료할 수 있게 한다.

또는 각 단계를 독립적으로 실행할 수도 있어야 한다.

```bash
pipeline-toolkit collect

pipeline-toolkit analyze

pipeline-toolkit visualize

pipeline-toolkit report

```

---

# Development Priority

다음 순서로 개발한다.

```text
Phase 1

Unified Metric Model
Command Runner
JUnit Collector
pytest Collector

```

```text
Phase 2

Benchmark Suite
Gradle Profiler
System Metrics

```

```text
Phase 3

Visualization Core
Markdown Report
HTML Report

```

```text
Phase 4

Gradle Dependency Graph
Affected Testing

```

```text
Phase 5

GitHub Actions Collector
DAG Analysis
Critical Path

```

```text
Phase 6

Baseline Comparison
Regression Detection
Historical Trend

```

```text
Phase 7

Reusable GitHub Workflow
OnMaru Adoption
v0.1.0

```

---

# Acceptance Criteria

다음 조건을 만족해야 한다.

```text
[ ] 실제 consumer tests를 benchmark한다.

[ ] JUnit 결과를 분석한다.

[ ] pytest 결과를 분석한다.

[ ] Gradle Profiler를 연동한다.

[ ] CPU/memory를 측정한다.

[ ] Pipeline wall-clock을 계산한다.

[ ] Job DAG를 재구성한다.

[ ] Critical path를 계산한다.

[ ] Baseline/Candidate 비교가 가능하다.

[ ] Slowest stages를 식별한다.

[ ] Slowest tests를 식별한다.

[ ] Affected modules를 시각화한다.

[ ] Pipeline timeline을 생성한다.

[ ] Before/After chart를 생성한다.

[ ] CPU/Memory chart를 생성한다.

[ ] Cache comparison chart를 생성한다.

[ ] Markdown report를 만든다.

[ ] HTML report를 만든다.

[ ] GitHub Job Summary를 만든다.

[ ] Benchmark artifact를 만든다.

[ ] Regression detection을 지원한다.

[ ] OnMaru source/test code를 복제하지 않는다.

```

---

# 프로젝트가 최종적으로 대답할 수 있어야 하는 질문

Toolkit을 사용한 개발자는 다음 질문에 수치로 답할 수 있어야 한다.

```text
현재 CI는 정확히 몇 분 걸리는가?

어디에서 가장 많은 시간을 쓰는가?

실제 critical path는 무엇인가?

Spring에서 가장 느린 module은 무엇인가?

가장 느린 test는 무엇인가?

FastAPI에서 가장 느린 test group은 무엇인가?

CPU를 얼마나 사용하고 있는가?

메모리는 얼마나 필요한가?

병렬화를 했을 때 얼마나 빨라졌는가?

그 대신 CPU와 memory는 얼마나 증가했는가?

Cache는 실제로 얼마나 효과가 있는가?

이번 변경에서 왜 이 module tests가 실행되었는가?

몇 개 module을 skip했는가?

최적화 전과 후의 차이는 정확히 얼마인가?

최근 pipeline 성능이 다시 느려지고 있는가?

```

이 질문들에 추측이 아니라 **수집된 데이터 + 시각화 + 보고서**로 답하는 것이 이 Toolkit의 최종 목적이다.

---

# Production Hardening 요구사항

앞의 기능 목록만 구현한 상태는 benchmark demo로는 충분하지만, 재사용 가능한 CI/CD toolkit으로 운영하기에는 부족하다. 이 장에서는 실행 신뢰성, 데이터 신뢰도, DAG 정확성, 보안, 통계적 검증을 제품 요구사항으로 고정한다.

## 요구사항 우선순위

| 우선순위 | 의미 | 출시 조건 |
|---|---|---|
| P0 | 없으면 결과를 신뢰하거나 안전하게 실행할 수 없음 | v0.1.0 전에 반드시 구현 |
| P1 | 분석·비교 품질과 운영성을 크게 좌우함 | v0.1.x에서 구현 |
| P2 | 확장성과 장기 운영을 개선함 | v0.2 이후 구현 가능 |

P0 요구사항은 다음과 같다.

```text
P0-1  Versioned Unified Evidence Model
P0-2  Reliable Command Execution
P0-3  Accurate Pipeline DAG and Critical Path
P0-4  Untrusted Input and Secret Boundary
P0-5  Deterministic Artifact and Report Generation
```

---

# Versioned Unified Evidence Model

## 원칙

모든 분석은 collector의 raw output을 직접 읽지 않는다.

```text
External Tool
      ↓
Raw Artifact (immutable)
      ↓
Source Record
      ↓
Normalizer
      ↓
Versioned Unified Evidence Model
      ↓
Analysis / Visualization / Report
```

raw artifact는 재처리와 사후 검증을 위해 보존한다. normalized 결과에는 원본 위치와 collector를 추적할 수 있는 provenance를 포함한다.

## 필수 공통 필드

모든 stage/test/pipeline evidence는 최소한 다음 필드를 가져야 한다.

```json
{
  "schemaVersion": 1,
  "recordId": "uuid-or-stable-hash",
  "kind": "stage",
  "status": "success",
  "measurementQuality": "observed",
  "source": {
    "collector": "junit",
    "collectorVersion": "0.1.0",
    "tool": "junit",
    "toolVersion": "5.x"
  },
  "execution": {
    "benchmarkId": "...",
    "repository": "YRootLab/OnMaru-backend",
    "commitSha": "...",
    "workflowRunId": "...",
    "jobId": "...",
    "attempt": 1
  },
  "environment": {
    "runner": "ubuntu-24.04",
    "architecture": "amd64",
    "cpuLimit": 4,
    "memoryLimitMb": 8192,
    "cacheState": "warm"
  },
  "time": {
    "startedAt": "ISO-8601",
    "endedAt": "ISO-8601",
    "durationMs": 153220,
    "durationClock": "monotonic"
  },
  "provenance": {
    "rawArtifact": "raw/junit/spring-api.xml",
    "parserWarnings": []
  }
}
```

## 상태와 데이터 품질

`exitCode`만으로 결과를 판단하지 않는다. 다음 상태를 구분한다.

```text
success      정상 실행 및 정상 수집
failed       실행은 끝났으나 명령 또는 테스트 실패
cancelled    외부 취소로 종료
timeout      실행 제한 시간 초과
partial      일부 결과만 수집
missing      기대한 artifact가 없음
invalid      artifact가 존재하지만 schema/파싱 실패
inconclusive 비교에 필요한 데이터가 부족함
```

`measurementQuality`는 다음 값만 허용한다.

```text
observed     원본에서 직접 관찰
estimated    명시된 계산 규칙으로 추정
partial      일부 필드 또는 일부 node만 존재
missing      해당 값을 수집하지 못함
invalid      신뢰할 수 없는 값
```

분석기는 `missing`, `invalid`, `partial` 값을 정상 관측값처럼 집계하지 않는다. 보고서에는 제외 이유를 표시한다.

## Schema 호환성

- 모든 normalized schema는 `schemaVersion`을 선언한다.
- 하위 호환이 깨지는 변경은 major version 또는 명시적 migration을 사용한다.
- collector는 지원하지 않는 schema를 조용히 무시하지 않고 명시적인 오류를 낸다.
- raw artifact는 normalized schema가 변경되어도 삭제하지 않는다.
- schema fixture와 migration test를 함께 유지한다.

---

# Reliable Command Execution

## Command Runner 계약

모든 외부 명령은 공통 `CommandResult`로 반환한다.

```json
{
  "command": "./gradlew",
  "arguments": ["test"],
  "workingDirectory": "consumer-repository",
  "startedAt": "ISO-8601",
  "endedAt": "ISO-8601",
  "exitCode": 0,
  "termination": "exited",
  "timedOut": false,
  "stdoutArtifact": "raw/commands/001.stdout",
  "stderrArtifact": "raw/commands/001.stderr",
  "redactions": 0
}
```

## 실행 규칙

- shell 문자열 조합을 금지하고 executable과 arguments를 분리한다.
- config에 정의된 allowlist command만 실행한다.
- 모든 command는 timeout을 가지며 기본값과 stage별 override를 명시한다.
- timeout 시 process group 전체에 종료 signal을 전달한다.
- stdout/stderr는 분리 보존하고 report에는 redacted 요약만 표시한다.
- retry는 네트워크·일시적 GitHub API 오류처럼 재시도 가능한 경우에만 허용한다.
- 테스트 실패, parser 실패, timeout, resource exhaustion을 서로 다른 failure reason으로 기록한다.
- 일부 출력이 생성된 뒤 실패하면 raw output을 보존하고 `partial` 또는 `failed`로 기록한다.
- command 환경변수와 arguments에 포함된 secret은 저장 전에 redaction한다.

---

# Pipeline DAG와 Critical Path 정확성

## 실행 계층

GitHub Actions pipeline은 다음 계층을 보존한다.

```text
Workflow
  └── Job
        └── Matrix Execution
              └── Attempt
                    └── Step
```

logical DAG와 실제 execution DAG를 별도로 계산한다.

## DAG 처리 정책

| 상황 | 처리 규칙 |
|---|---|
| matrix job | logical job과 각 matrix execution을 모두 기록 |
| skipped job | node는 보존하고 duration은 0이 아닌 `missing`으로 표시 |
| retry | attempt별 node를 보존하고 최종 결과와 retry 비용을 분리 |
| cancelled job | downstream 영향과 취소 원인을 기록 |
| failed dependency | downstream이 실행되지 않은 경우 `blocked`로 기록 |
| timestamp 누락 | critical path에서 추정하지 않고 `inconclusive` 가능성을 표시 |
| reusable workflow | workflow boundary와 호출 관계를 보존 |
| conditional job | 조건식 원문과 최종 실행 여부를 보존 |

## 시간 정의

```text
queueDuration
= runner 할당을 기다린 시간

executionDuration
= runner에서 실제 실행된 시간

workDuration
= 선택한 node duration의 합

pipelineWallClock
= root 시작부터 terminal node 종료까지의 실제 시간

criticalPathDuration
= execution DAG에서 longest path의 시간
```

`workDuration`은 병렬화 비용 분석에 사용하고, `pipelineWallClock`과 `criticalPathDuration`은 개발자 대기 시간 분석에 사용한다. 세 값을 하나의 custom score로 합치지 않는다.

## Critical Path 검증

다음 fixture를 반드시 제공한다.

```text
serial DAG
fully parallel DAG
diamond DAG
parallel jobs with idle gap
skipped node
failed dependency
retried node
missing timestamp
matrix job
```

각 fixture는 기대하는 `workDuration`, `pipelineWallClock`, `criticalPathDuration`, overlap을 선언하고 자동 검증한다.

---

# Benchmark 통계와 비교 신뢰성

## 실행 조건

benchmark suite는 다음 실행 조건을 기록한다.

```yaml
benchmark:
  warmupRuns: 1
  measuredRuns: 5
  cacheState: warm
  parallelism: 4
  failOnInsufficientEvidence: false
```

- cold cache와 warm cache를 동일 baseline으로 섞지 않는다.
- baseline과 candidate는 동일 runner image, architecture, resource limit을 우선 사용한다.
- benchmark run 수와 제외된 run 수를 report에 표시한다.
- timeout, cancellation, runner outage는 성능 sample에서 제외하되 제외 사유를 보존한다.

## 비교 결과

비교 결과는 다음 중 하나다.

```text
improved
regressed
unchanged
inconclusive
```

`inconclusive`는 sample 부족, 환경 불일치, missing artifact, 높은 변동성으로 통계적 판단을 할 수 없는 경우다. 이 결과를 regression 또는 improvement로 단정하지 않는다.

최소 report 항목:

```text
sample count
excluded count
median
p95 (sample이 충분한 경우)
absolute delta
relative delta
variance 또는 confidence interval
baseline/candidate environment
```

Regression threshold는 상대 변화율만 사용하지 않는다.

```yaml
regression:
  pipeline:
    thresholdPercent: 10
    minimumAbsoluteDeltaMs: 30000
    minimumSamples: 3
  spring-test:
    thresholdPercent: 15
    minimumAbsoluteDeltaMs: 10000
```

초기 버전은 `warning/report-only`로 동작한다. CI fail gate는 false-positive 비율과 최소 baseline 수가 확인된 뒤 opt-in으로 활성화한다.

---

# 보안과 실행 격리

Toolkit은 consumer repository와 PR 변경사항을 실행하므로 입력을 기본적으로 untrusted로 취급한다.

## 권한 규칙

- GitHub token은 workflow metadata와 artifact 조회에 필요한 최소 read 권한만 사용한다.
- fork PR에서는 secrets가 필요한 단계와 benchmark 단계를 분리한다.
- `migration`, `deploy`, production smoke test는 기본 비활성화한다.
- 배포·마이그레이션 실행은 명시적인 allowlist와 environment approval이 있어야 한다.
- Docker socket, cloud credential, deployment credential은 benchmark 기본 컨텍스트에 주입하지 않는다.
- arbitrary shell command는 config allowlist와 trusted runner 조건을 만족할 때만 실행한다.

## 데이터 보호

- stdout, stderr, environment, HTML, Markdown, GitHub Summary에 대해 secret/PII redaction을 수행한다.
- commit SHA, individual test name, full file path는 Prometheus label로 사용하지 않는다.
- HTML report는 escaping하고 artifact path는 repository output directory 내부로 제한한다.
- raw artifact retention과 접근 권한을 config로 명시한다.
- security scan, SBOM, Docker metadata는 source tool/version과 함께 보존한다.

---

# Toolkit 자체 Observability

향후 Prometheus/OpenTelemetry export만 고려하지 않고, toolkit 실행 자체의 실패와 데이터 품질을 관측한다.

## 권장 metric

```text
toolkit_collection_duration_seconds
toolkit_collection_failures_total{collector,reason}
toolkit_normalization_records_total{source,status}
toolkit_report_generation_duration_seconds
toolkit_missing_artifacts_total{artifact_type}
toolkit_benchmark_runs_total{result}
```

label은 `collector`, `source`, `status`, `result`, `runtime`처럼 제한된 값만 허용한다. repository, commit SHA, test name, full path는 artifact와 report의 구조화 필드로 둔다.

모든 structured log는 다음 correlation 정보를 포함할 수 있어야 한다.

```text
benchmarkId
workflowRunId
jobId
collector
stage
```

---

# Artifact와 Report Provenance

한 결과를 사람이 재현하고 검증할 수 있도록 다음 연결을 보장한다.

```text
Report value
  → analysis record
    → normalized record
      → source record
        → raw artifact
          → command / workflow run
```

모든 표와 시각화는 다음 metadata를 표시하거나 링크한다.

```text
commit SHA
workflow/run/job/attempt
runner image and resource limit
tool and collector version
cache state
sample count
missing/partial/estimated flag
calculation rule
raw artifact link
```

PNG, HTML, Markdown, JSON은 동일한 report model에서 생성한다. 각 renderer가 raw collector output을 독립적으로 해석하지 않는다.

---

# Determinism과 Failure Matrix

## 결정론적 처리

- 동일한 raw artifact와 동일한 config는 동일한 normalized JSON을 생성해야 한다.
- map/directory iteration 순서에 의존하지 않고 안정적인 sort key를 사용한다.
- timestamp 표시 timezone과 rounding 규칙을 고정한다.
- chart 색상, top-N tie-break, report section 순서를 고정한다.
- report 생성 시 현재 시각이나 실행 host의 임의 정보가 결과를 오염시키지 않도록 한다.

## 필수 failure fixture

```text
missing artifact
malformed JUnit XML
malformed pytest XML
command timeout
non-zero command exit
SIGTERM/SIGKILL
GitHub API 401/403/404/429/5xx
rate limit and pagination
Docker daemon unavailable
Gradle dependency graph export failure
partial workflow timestamps
schema version mismatch
secret-like log content
```

각 failure는 process exit code, artifact 보존 여부, normalized status, report 표시, CI gate 동작을 정의해야 한다.

---

# 보완된 Directory Structure

기존 구조에 다음 모듈과 fixture를 추가한다.

```text
src/pipeline_toolkit/
├── contracts/
│   ├── evidence.py
│   ├── command.py
│   └── status.py
├── security/
│   ├── allowlist.py
│   └── redaction.py
├── provenance/
│   ├── execution.py
│   └── artifacts.py
└── telemetry/
    ├── metrics.py
    └── logging.py

tests/fixtures/
├── commands/
├── junit/
├── pytest/
├── github-actions/
├── dag/
├── schemas/
└── security/
```

---

# 보완된 Development Priority

```text
Phase 0 — Contracts and Fixtures
Unified evidence schema
CommandResult contract
status/quality enum
DAG/statistics/security fixture
```

```text
Phase 1 — Reliable Execution
Timeout and process-tree cancellation
stdout/stderr artifact
redaction
retry policy
partial failure handling
```

```text
Phase 2 — Collect and Normalize
JUnit/pytest/system/Gradle/Docker collector
schema validation
provenance
deterministic normalization
```

```text
Phase 3 — DAG and Affected Analysis
Workflow/Job/Matrix/Attempt/Step model
serial/parallel/diamond validation
critical path
affected module explanation
```

```text
Phase 4 — Statistical Comparison
warm-up and repeated runs
baseline selection
median/p95/variance
inconclusive result
regression warning
```

```text
Phase 5 — Visualization and Report
timeline
before/after
resource trade-off
provenance and missing-data indicators
Markdown/HTML/Job Summary consistency
```

```text
Phase 6 — Secure GitHub Adoption
least-privilege workflow
fork PR isolation
artifact retention
optional deployment boundary
reusable workflow
```

```text
Phase 7 — Historical Observability
OpenTelemetry/Prometheus export
trend storage
schema migration
opt-in CI fail gate
```

---

# 보완된 Acceptance Criteria

## P0 — 신뢰성과 안전성

```text
[ ] 모든 외부 command가 timeout, process-tree cancellation, exit reason을 기록한다.
[ ] stdout/stderr와 raw artifact가 immutable output으로 보존된다.
[ ] secret, PII, token이 report와 artifact에 평문으로 남지 않는다.
[ ] fork PR과 deployment/migration 단계가 안전하게 격리된다.
[ ] normalized model이 schemaVersion, provenance, environment, quality를 포함한다.
[ ] collector raw output을 report/visualization이 직접 참조하지 않는다.
[ ] 동일 input을 재처리하면 deterministic output이 생성된다.
```

## P1 — 분석 정확성

```text
[ ] matrix, skipped, retry, cancelled, failed dependency를 DAG에 보존한다.
[ ] work duration, pipeline wall-clock, critical path를 분리 계산한다.
[ ] serial, parallel, diamond DAG fixture가 기대값과 일치한다.
[ ] queue, execution, retry, idle gap을 구분한다.
[ ] cold/warm cache와 runner 환경을 비교 조건에 포함한다.
[ ] sample 부족 또는 환경 불일치 결과를 inconclusive로 표시한다.
[ ] median, p95, variance 또는 confidence interval을 제공한다.
```

## P1 — Evidence report

```text
[ ] 모든 결과가 commit/run/tool version/raw artifact로 추적된다.
[ ] missing, partial, estimated, invalid 값이 정상 관측값과 구분된다.
[ ] HTML, Markdown, JSON, Job Summary가 동일 report model을 사용한다.
[ ] 차트가 대규모 module/test 수와 tie를 결정론적으로 처리한다.
[ ] report에 baseline/candidate 정의와 sample count가 표시된다.
```

## P2 — 운영 확장

```text
[ ] toolkit 자체 collection/normalization/report metric을 export한다.
[ ] metric label cardinality 정책이 자동 검사된다.
[ ] historical trend storage와 retention 정책이 동작한다.
[ ] schema migration과 backward compatibility test가 존재한다.
[ ] regression CI fail gate가 opt-in으로 동작한다.
```

---

# 업데이트된 최종 질문

Toolkit은 기존 질문에 더해 다음 질문에도 답할 수 있어야 한다.

```text
이 수치는 실제 관측값인가, 추정값인가, 부분 결과인가?

어떤 command와 tool version에서 생성되었는가?

실패한 benchmark를 성능 저하로 잘못 해석하지 않았는가?

queue time과 실제 execution time을 구분했는가?

matrix/retry/skipped job이 critical path를 왜곡하지 않았는가?

이번 비교는 통계적으로 충분한 sample을 가지고 있는가?

fork PR이나 untrusted code가 secret 또는 deployment 권한에 접근했는가?

이 report의 숫자를 raw artifact까지 재현할 수 있는가?
```

---

# Release 연계 Benchmark 비교

Benchmark 결과는 단순한 CI 실행 결과가 아니라 특정 OnMaru 배포 버전에 귀속된 성능 증거여야 한다. 따라서 이전 tag와 현재 tag의 성능을 비교할 수 있도록 `Release`, `BenchmarkRun`, `Comparison`을 분리해서 모델링한다.

## 핵심 식별 관계

```text
OnMaru Release Tag
        ↓
Release Commit SHA
        ↓
Container Image Digest
        ↓
Deployment
        ↓
Benchmark Run
        ↓
Comparison
```

tag는 사람이 검색하는 release 식별자이며, 실제 동일성을 보장하는 값은 commit SHA와 image digest다. 같은 tag가 다른 환경에 배포되거나 재실행될 수 있으므로 tag 하나만 benchmark 결과의 primary identity로 사용하지 않는다.

## Release Model

```json
{
  "id": "release-123",
  "repository": "YRootLab/OnMaru-backend",
  "version": "v1.4.0",
  "tag": "v1.4.0",
  "commitSha": "abc123...",
  "image": {
    "repository": "ghcr.io/yrootlab/onmaru-backend",
    "digest": "sha256:..."
  },
  "createdAt": "ISO-8601"
}
```

필수 규칙:

- `version`, `tag`, `commitSha`, image digest를 함께 저장한다.
- tag가 이동되거나 재생성되어도 기존 benchmark evidence를 덮어쓰지 않는다.
- release 등록 시 repository, commit SHA, image digest를 검증한다.
- production과 staging의 동일 version 배포는 별도의 deployment로 관리한다.

## BenchmarkRun Model

`BenchmarkRun`은 하나의 release에 대해 특정 환경·suite·실행 조건으로 수행한 한 번의 측정이다.

```json
{
  "id": "run-20260923-001",
  "releaseId": "release-123",
  "environment": "staging",
  "suite": "default-backend",
  "runnerProfile": "ubuntu-24.04-4cpu-8gb",
  "cacheState": "warm",
  "toolkitVersion": "v0.1.0",
  "configHash": "sha256:...",
  "workflowRunId": "987654",
  "status": "success",
  "startedAt": "ISO-8601",
  "endedAt": "ISO-8601",
  "artifactsUri": "..."
}
```

한 번의 benchmark result만으로 release 성능을 대표하지 않는다. 같은 조건의 여러 `BenchmarkRun`을 저장하고 비교 단계에서 aggregation한다.

## Comparison Model

`Comparison`은 baseline release와 candidate release에 속한 여러 run을 비교한 immutable 분석 결과다.

```json
{
  "id": "comparison-001",
  "baselineReleaseId": "release-previous",
  "candidateReleaseId": "release-current",
  "environment": "staging",
  "suite": "default-backend",
  "baselineRunIds": ["run-001", "run-002", "run-003"],
  "candidateRunIds": ["run-101", "run-102", "run-103"],
  "statisticalMethod": "median_and_p95",
  "result": "improved",
  "metrics": {
    "pipelineWallClock": {
      "baselineMedianMs": 831000,
      "candidateMedianMs": 501000,
      "deltaMs": -330000,
      "deltaPercent": -39.71
    }
  },
  "inconclusiveReasons": [],
  "reportUri": "..."
}
```

최종 delta만 저장하지 않고 비교에 사용한 모든 run ID와 artifact URI를 보존한다.

## Tag 간 비교 CLI

최소 다음 명령을 지원한다.

```bash
pipeline-toolkit release register \
  --repository YRootLab/OnMaru-backend \
  --version v1.4.0 \
  --tag v1.4.0 \
  --commit-sha abc123 \
  --image-digest sha256:...
```

```bash
pipeline-toolkit benchmark compare \
  --baseline v1.3.2 \
  --candidate v1.4.0 \
  --environment staging \
  --suite default-backend \
  --repetitions 5 \
  --cache-state warm \
  --output ./benchmark/comparison
```

```bash
pipeline-toolkit publish \
  --input ./benchmark/comparison \
  --storage github-artifact
```

`benchmark compare`는 다음 순서로 실행한다.

```text
resolve baseline/candidate tag
        ↓
verify commit SHA and image digest
        ↓
validate comparable environment/config
        ↓
run identical benchmark suite repeatedly
        ↓
collect raw artifacts
        ↓
normalize baseline/candidate runs
        ↓
aggregate median/p95/resource metrics
        ↓
classify result
        ↓
generate comparison report
```

## 비교 가능성 검증

다음 조건이 다르면 성능 비교를 자동으로 확정하지 않고 `inconclusive`로 처리한다.

```text
environment
runner image
architecture
CPU limit
memory limit
benchmark suite
config hash
toolkit version
cache state
database fixture version
external dependency mode
```

예를 들어 다음 비교는 유효하지 않다.

```text
v1.3.2: staging / 4 CPU / warm cache
v1.4.0: production / 8 CPU / cold cache
```

이 경우 성능 수치를 계산하더라도 최종 상태는 다음과 같이 기록한다.

```json
{
  "result": "inconclusive",
  "inconclusiveReasons": [
    "runner resource mismatch",
    "cache state mismatch"
  ]
}
```

## Baseline 선택 정책

사용자가 baseline을 지정하지 않은 경우 다음 순서로 선택한다.

```text
1. 같은 production 환경의 직전 성공 release
2. 같은 major/minor 계열의 직전 성공 release
3. target branch의 가장 최근 성공 benchmark
4. 명시된 repository policy의 기준 release
5. 선택 가능한 baseline 없음 → inconclusive
```

baseline 선택 결과는 report에 반드시 표시한다. baseline이 없으면 regression 또는 improvement를 단정하지 않는다.

## 반복 실행과 통계 정책

초기 기본값은 다음과 같다.

```yaml
comparison:
  warmupRuns: 1
  repetitions: 5
  minimumValidRuns: 3
  aggregation: median
  includeP95: true
  regressionThresholdPercent: 10
```

- baseline과 candidate는 동일 runner profile과 resource limit에서 실행한다.
- cold cache와 warm cache 실행은 별도의 비교 그룹으로 나눈다.
- timeout, cancellation, runner outage는 성능 sample에서 제외하고 제외 사유를 보존한다.
- 유효 sample 수가 `minimumValidRuns`보다 작으면 `inconclusive`다.
- median, p95, variance 또는 confidence interval, sample count를 함께 표시한다.

결과 상태는 다음 네 가지를 기본으로 한다.

```text
improved
regressed
unchanged
inconclusive
```

CPU와 memory가 증가한 경우 wall-clock 결과와 분리해서 표시한다.

```text
pipeline wall-clock: -39.7%
CPU time: +21.4%
peak RSS: +47.4%
result: improved_with_resource_increase
```

## Release별 저장 구조

초기에는 GitHub Artifact와 GitHub Release Asset을 사용할 수 있다. 장기 trend와 검색이 필요해지면 Object Storage와 PostgreSQL metadata index로 확장한다.

```text
benchmark-storage/
└── onmaru-backend/
    ├── releases/
    │   ├── v1.3.2/
    │   │   ├── release.json
    │   │   └── runs/
    │   │       ├── run-001/
    │   │       └── run-002/
    │   └── v1.4.0/
    │       ├── release.json
    │       └── runs/
    │           ├── run-101/
    │           └── run-102/
    └── comparisons/
        └── v1.3.2__v1.4.0/
            ├── comparison.json
            ├── report.md
            ├── report.html
            └── charts/
```

각 run의 artifact 구조:

```text
run-101/
├── manifest.json
├── raw/
├── normalized/
│   ├── pipeline.json
│   ├── stages.json
│   └── tests.json
├── charts/
├── report/
│   ├── report.md
│   ├── report.html
│   └── report.json
└── checksums.txt
```

`manifest.json`은 release, commit, image digest, environment, run ID, schema version, artifact checksum을 연결하는 entry point다.

## OnMaru-backend Release Workflow 연동

OnMaru-backend의 release pipeline은 다음 순서를 따른다.

```text
release tag 생성
    ↓
release metadata 등록
    ↓
Docker image build 및 digest 확정
    ↓
staging deploy
    ↓
이전 성공 release 조회
    ↓
benchmark compare 실행
    ↓
comparison report/artifact publish
    ↓
regression warning 또는 승인 gate
    ↓
production promotion
    ↓
production benchmark run 저장
```

예시 workflow 단계:

```yaml
- name: Register release metadata
  run: |
    pipeline-toolkit release register \
      --repository "${{ github.repository }}" \
      --version "${{ github.ref_name }}" \
      --tag "${{ github.ref_name }}" \
      --commit-sha "${{ github.sha }}" \
      --image-digest "${IMAGE_DIGEST}"

- name: Compare with previous release
  run: |
    pipeline-toolkit benchmark compare \
      --baseline "${PREVIOUS_RELEASE}" \
      --candidate "${{ github.ref_name }}" \
      --environment staging \
      --suite default-backend \
      --repetitions 5 \
      --publish
```

Toolkit은 OnMaru-backend의 서비스 DB에 benchmark 상세 데이터를 저장하지 않는다. 서비스 운영 데이터와 성능 evidence의 수명주기·접근 패턴이 다르므로 별도의 Benchmark Evidence Store에 저장한다.

## Database Metadata Schema 방향

Object Storage에는 raw/normalized/report를 저장하고, 검색·비교에 필요한 metadata만 relational store에 저장한다.

```text
releases
  id, repository, version, tag, commit_sha, image_digest, created_at

deployments
  id, release_id, environment, namespace, cluster,
  deployed_image_digest, deployed_at, status

benchmark_runs
  id, release_id, deployment_id, environment, suite,
  workflow_run_id, config_hash, toolkit_version, baseline_run_id,
  status, started_at, ended_at, artifact_uri

benchmark_metrics
  id, benchmark_run_id, stage_name, metric_name,
  metric_value, unit, aggregation, measurement_quality,
  source_artifact_uri

comparisons
  id, baseline_release_id, candidate_release_id,
  environment, suite, statistical_method, result,
  report_uri, created_at
```

## Prometheus와 Release Evidence Store의 역할 분리

Prometheus에는 현재 상태와 alert에 필요한 저카디널리티 metric만 export한다.

```text
ci_pipeline_duration_seconds{service="onmaru-backend",environment="staging"}
ci_pipeline_regressions_total{service="onmaru-backend",environment="staging"}
ci_benchmark_runs_total{service="onmaru-backend",environment="staging"}
```

다음 값은 Benchmark Evidence Store와 report에 둔다.

```text
releaseVersion
commitSha
imageDigest
workflowRunId
testName
moduleName
fullPath
raw artifact URI
```

```text
Prometheus
  → 현재 상태·alert·운영 dashboard

Benchmark Evidence Store
  → release별 상세 비교·historical analysis·재현 artifact
```

## Release 비교 Acceptance Criteria

```text
[ ] 이전 tag와 현재 tag를 commit SHA와 image digest까지 resolve한다.
[ ] baseline/candidate의 동일 suite와 config hash를 검증한다.
[ ] 동일 environment, runner, resource, cache 조건을 비교한다.
[ ] baseline/candidate를 최소 3회 이상 유효하게 반복 실행할 수 있다.
[ ] baseline과 candidate의 모든 BenchmarkRun ID를 Comparison에 저장한다.
[ ] median, p95, absolute delta, relative delta, resource delta를 제공한다.
[ ] sample 부족·환경 불일치·artifact 누락을 inconclusive로 표시한다.
[ ] release tag, commit SHA, image digest, workflow run, raw artifact를 추적한다.
[ ] release별 raw/normalized/report artifact를 immutable하게 저장한다.
[ ] GitHub Job Summary와 Release Asset에 비교 요약을 연결한다.
[ ] OnMaru-backend 서비스 DB와 Benchmark Evidence Store를 분리한다.
[ ] Prometheus label에 commit SHA, test name, full path를 사용하지 않는다.
[ ] production promotion 전에 staging tag comparison 결과를 확인할 수 있다.
```
