# OnMaruBE 모듈별 병렬 CI·Benchmark Control Plane PRD

상태: Proposed
소유: `YRootLab/OnMaru-backend-ci-toolkit`
Consumer: `YRootLab/OnMaru-backend`
관련: ADR-0003, ADR-0005, Toolkit #113, Toolkit #115, OnMaruBE #543

## 1. 문제와 목표

OnMaruBE의 현재 CI는 Gradle multi-module 및 FastAPI 검증을 단일 `verify` job에서 순차 실행한다. 모듈이 늘수록 개발자가 기다리는 wall-clock time, GitHub Actions 비용, 병목 원인의 불투명성이 함께 증가한다.

이 기능은 OnMaruBE가 소유한 모듈 catalog와 실행 명령을 읽어 affected module을 계산하고, 안전한 병렬 matrix로 테스트·측정을 실행하며, 결과를 baseline과 비교해 회귀·병목·개선 효과를 증명한다.

성공 기준은 다음과 같다.

- runtime service에 toolkit을 import하지 않고 OnMaruBE GitHub Actions가 version-pinned toolkit workflow를 호출한다.
- 새로운 backend module은 catalog 한 항목 추가만으로 affected calculation, parallel test, evidence, report에 포함된다.
- 각 결과는 commit SHA, run ID, module ID, command, artifact URI, config hash까지 추적 가능하다.
- 일반 PR과 push는 기존 필수 CI를 한 번 실행하고 그 결과를 관측한다. 추가 반복 benchmark는 파이프라인 개선 실험이나 release 판정에서만 명시적으로 수행한다.
- benchmark failure, artifact missing, 조건 불일치, 표본 부족은 성능 regression으로 오인하지 않는다.

## 2. 소유권과 경계

| 책임 | OnMaruBE | Pipeline Toolkit |
|---|---|---|
| module path·dependency·test command | 소유 | 검증·해석 |
| source checkout·GitHub token·deployment secret | 소유 | 요구하지 않음 |
| Gradle/pytest/Testcontainers 실행 | caller runner에서 실행 | execution plan 제공 |
| evidence schema·collector·DAG·comparison·report | 소비 | 소유 |
| staging/prod promotion | 소유 | gate result 제공 |
| CI/catalog/cache 자동 PR | 적용·승인 | 제한된 draft 제안 |

Toolkit은 consumer application source 또는 deployment credential을 보관하지 않는다. PR benchmark는 `contents: read`만으로 동작하며, PR comment job에만 `pull-requests: write`를 부여한다. Fork PR에는 release, storage, deployment secret을 전달하지 않는다.

## 3. ModuleCatalog v1

Consumer는 `.github/benchmark-modules.yml`에 다음 모델을 선언한다.

```yaml
version: 1
defaults:
  max_parallel: 4
  fallback: full-suite
modules:
  - id: catalog
    kind: gradle
    paths: [modules/catalog/**]
    depends_on: [shared-web, persistence-jdbc]
    test_command: ./gradlew :modules:catalog:test --no-daemon
    tier: pr-and-release
    resource_profile: medium
  - id: spring-api
    kind: gradle
    paths: [apps/spring-api/**]
    depends_on: [catalog, audio, community, identity, insights, journey, operations, persistence-jdbc]
    test_command: ./gradlew :apps:spring-api:test --no-daemon
    tier: full-suite
    resource_profile: heavy
  - id: ai
    kind: pytest
    paths: [ai/**]
    depends_on: []
    test_command: uv run pytest
    tier: pr-and-release
    resource_profile: medium
always_full_paths:
  - settings.gradle.kts
  - build.gradle.kts
  - build-logic/**
  - gradle/**
  - .github/workflows/**
```

Validation rules:

- `id`는 고유하고 dependency graph는 acyclic이어야 한다.
- `paths`, `test_command`, `tier`, `resource_profile`은 필수다.
- 변경된 module의 reverse dependency도 실행 대상이다.
- `always_full_paths` 변경, unknown path, catalog validation failure, diff acquisition failure는 전체 suite로 fallback한다.
- `heavy`는 `max_parallel`을 공유하지 않고 별도 concurrency group으로 실행한다.

## 4. GitHub Actions Interface

Toolkit은 다음 reusable workflow를 제공한다.

```yaml
jobs:
  verify:
    uses: YRootLab/OnMaru-backend-ci-toolkit/.github/workflows/module-benchmark.yml@<immutable-release>
    with:
      catalog_path: .github/benchmark-modules.yml
      mode: pr
      max_parallel: 4
      baseline_ref: develop
      comment_mode: summary
    permissions:
      contents: read
      pull-requests: write
```

`workflow_call` inputs:

| Input | Type | 설명 |
|---|---|---|
| `catalog_path` | string | caller repository의 catalog 경로 |
| `mode` | enum | `pr`, `develop`, `nightly`, `release` |
| `max_parallel` | number | light/medium matrix의 최대 병렬 수 |
| `baseline_ref` | string | baseline lookup branch/tag |
| `comment_mode` | enum | `none`, `summary`, `full` |

workflow outputs:

| Output | 설명 |
|---|---|
| `result` | `improved`, `unchanged`, `regressed`, `inconclusive`, `failed` |
| `comparison_id` | baseline/candidate comparison 식별자 |
| `manifest_uri` | evidence manifest artifact URI |
| `report_artifact` | report artifact 이름 |
| `critical_path_seconds` | 분석된 critical path |

Workflow는 `detect → matrix test → aggregate → verify fan-in` 구조다. matrix는 `fail-fast: false`여야 하며, 최종 `verify` job은 기존 branch ruleset의 required check 이름을 유지한다.

## 5. Mode별 실행과 baseline

| Mode | 대상 | 반복 | 판정 | 보존 |
|---|---|---:|---|---|
| PR 기본 경로 | 기존 필수 CI 결과 관측 | 추가 반복 없음 | 성능 판정 없음 | GitHub Artifact + telemetry |
| develop | full suite | 1 | evidence only | GitHub Artifact |
| nightly | full suite | 3 | flaky/변동성 분석 | GitHub Artifact |
| experiment | 고정한 develop baseline과 feature candidate | baseline/candidate 각 3 | 중앙값·범위·실패율 비교 | GitHub Artifact |
| release | full suite, 동일 조건 | baseline/candidate 각 3 | 중앙값 15% 초과는 approval hold | GitHub Release asset + manifest |

Comparability key는 `repository`, `suite`, `catalog/config hash`, runner image, Java/Python version, cache state, database fixture, CPU/memory profile, dependency mode를 포함한다. 하나라도 불일치하면 `inconclusive`다. `commit SHA`는 각 표본의 불변 실행 신원으로 보존한다. 개선 실험에서는 애플리케이션 source SHA를 같게 유지하고 의도적으로 바꾼 workflow/cache 설정을 기록한다. 서로 다른 release의 SHA를 서로 같아야 하는 조건으로 사용하지 않는다.

`develop` artifact는 빠른 비교를 위한 단기 baseline이다. release 비교의 durable source of truth는 tag, commit SHA, image digest, config hash, report checksum을 포함한 GitHub Release asset이다.

### 상시 관측과 반복 실험의 분리

상시 관측은 기존 `CI`, `Module Benchmark`, release workflow가 이미 실행한 결과를 완료 후 수집한다. 이 경로는 테스트를 다시 실행하지 않으며 OpenTelemetry metric·trace와 consumer-local 진단 증적만 만든다. 모든 PR에 baseline/candidate 3회 측정을 추가하지 않는다.

반복 실험은 CI, test, CD 구조·cache·runner·matrix·배포 절차를 의도적으로 바꿨을 때만 `Pipeline Benchmark Experiment`의 `workflow_dispatch`로 시작한다. label과 PR 생성은 실행 조건이 아니다. v1은 같은 OnMaruBE 저장소의 커밋된 `feature/*` 브랜치만 허용하며 fork와 dirty working tree는 대상에서 제외한다.

실험 시작 시 `origin/develop`을 resolve한 immutable SHA를 baseline으로, 현재 feature branch의 immutable SHA를 candidate로 고정한다. 두 SHA의 suite, config hash, runner, dependency, cache와 fixture 조건을 manifest에 기록하고 각각 서로 다른 성공 실행 3회를 요구한다. 실패·취소·누락과 조건 불일치는 `inconclusive`이며 자동으로 추가 실행하거나 성공 표본으로 바꾸지 않는다.

Consumer workflow의 수동 입력 계약은 다음과 같다.

| Input | 값 | 규칙 |
|---|---|---|
| `candidate_ref` | feature branch 또는 40자 SHA | 실행 전에 immutable SHA로 resolve |
| `baseline_ref` | 기본값 `develop` | 실행 전에 remote SHA로 resolve |
| `scope` | `ci`, `test`, `cd` | v1은 `ci`와 `test`; `cd`는 격리된 staging 준비 후 활성화 |
| `reason` | 변경 목적 요약 | manifest와 보고서에 기록, metric label에는 사용하지 않음 |

반복 횟수 3은 사용자가 바꾸는 workflow input이 아니라 비교 정책 버전의 일부다. 측정 도중 branch가 이동해도 고정된 SHA를 계속 사용한다. 실험 결과는 일반 PR required check나 자동 배포 조건으로 등록하지 않고 검토 증거로 제공한다.

## 6. Evidence와 분석

각 module execution은 다음 raw evidence를 artifact로 보존한다.

- JUnit XML 또는 pytest result/duration output
- command stdout/stderr와 종료 상태
- `/usr/bin/time -v` 기반 CPU·memory evidence
- Gradle cache/build result metadata
- module catalog/config hash와 environment identity

Toolkit은 raw evidence를 existing unified evidence model로 정규화하고 다음을 계산한다.

| Metric | 목적 |
|---|---|
| wall-clock | 개발자 대기 시간 |
| work | 전체 runner 사용량·비용 |
| critical path | 병목 의존 경로 |
| queue / idle | runner 부족·병렬 효율 문제 |
| module duration | 느린 모듈 식별 |
| CPU/memory peak | 과도한 병렬화 탐지 |
| cache hit/miss | cache 개선 판단 |
| flaky rate | 반복 실행 안정성 |

모든 renderer는 normalized report model만 사용한다. 결과는 JSON, Markdown, HTML, Job Summary와 optional PNG artifact로 생성한다.

## 7. Regression과 remediation 정책

- `failed`: test, command, deployment, collection이 실패했다. 성능 비교를 수행하지 않는다.
- `inconclusive`: baseline 없음, 조건 불일치, artifact 누락, 유효 sample 부족이다. PR은 warning, release는 명시적 승인 필요다.
- `regressed`: comparable run의 중앙값이 threshold를 넘었다.
- `improved`/`unchanged`: evidence와 sample count를 함께 표시한다.

Recommendation engine은 critical path, cache miss, resource contention, flaky module, repeated slow test를 typed recommendation으로 기록한다. 자동 Issue 생성은 허용한다. draft PR은 catalog, matrix, cache, concurrency, path filter에 한정한다. application test code, deployment workflow, secret, production promotion은 자동으로 바꾸지 않는다.

## 8. 수용 기준과 검증

- Catalog parser test는 direct/reverse dependency, cycle rejection, full-suite fallback을 포함한다.
- Consumer fixture workflow는 docs-only, catalog module, common module, resolver failure, matrix partial failure를 검증한다.
- `verify` fan-in check는 모든 required child job의 결과를 통합하고 기존 branch protection 이름을 유지한다.
- Testcontainers/heavy module은 configured concurrency를 넘지 않으며 resource evidence를 남긴다.
- S1 순차 baseline, S2 job parallel, S3 Gradle tuning, S4 pytest parallel, S5 affected execution을 동일 commit에서 비교한다.
- release mode는 baseline/candidate 각 3회 valid run, baseline comparability, image digest/smoke evidence를 검증한다. 개별 값과 변동폭을 보고하며 세 표본만으로 통계적 유의성을 주장하지 않는다.
- workflow security test는 fork PR secret isolation과 최소 권한을 검증한다.

## 9. 구현 우선순위

| 우선순위 | 제목 | 구현 결과 |
|---|---|---|
| P0 | 신뢰 가능한 CI 시간선·증적과 consumer-local 진단 | run/attempt와 모든 job·step을 수집하고 결측·부분·중복·실패를 명시한다. 확인할 수 없는 workflow 시간, queue와 DAG critical path를 추정하지 않는다. |
| P1 | OpenTelemetry·Prometheus 호환 저장소·Grafana 관측 | 증적을 bounded low-cardinality OTLP metric과 사후 재구성 trace로 변환한다. 로컬 Collector·Prometheus·Tempo·Grafana와 운영 Grafana Cloud Mimir·Tempo 경로에서 대시보드와 원본 실행 왕복을 검증한다. |
| P2 | release 3회 비교와 승인 판정 연결 | baseline/candidate 각 3회 비교, 15% approval hold, manifest 보존을 OnMaruBE release workflow에 연결하고 기존 release gate와 이중 판정을 제거한다. |
| P3 | 필요할 때만 실행하는 Pipeline Benchmark Experiment CLI·Agent Skill | 수동 workflow, Toolkit CLI와 `ci-benchmark-experiment` skill로 feature SHA와 develop SHA의 3회 비교를 실행·대기·요약한다. 일반 PR·push·CD에 반복 측정을 추가하지 않는다. |

P0와 P1이 먼저다. P3는 P0 증적과 P1 관측 경로를 소비하며 자체 측정 정의를 만들지 않는다.

### P3 CLI·Agent Skill 계약

Toolkit CLI는 dry-run에서 repository, baseline SHA, candidate SHA, scope, 반복 정책과 예상 workflow dispatch payload를 출력한다. 실제 실행에서는 `gh workflow run`으로 consumer-owned workflow를 시작하고 run ID를 수집한 뒤 완료를 기다려 manifest와 비교 보고서 링크를 반환한다.

Agent Toolkit의 `ci-benchmark-experiment` skill은 CLI를 감싸며 저장소·`gh` 인증·remote·branch·clean tree·workflow 존재를 먼저 검사한다. 기본 기준선은 `origin/develop`, 기본 후보는 현재 `feature/*` HEAD다. 사용자가 명시한 다른 SHA를 조용히 대체하지 않는다. 실행 결과는 baseline/candidate 개별 값, 중앙값, 범위, 제외 사유, verdict, Actions·manifest·Grafana 링크를 보여 준다.

CLI와 skill은 관측 자격 증명을 읽거나 출력하지 않는다. Grafana Cloud 전송은 OnMaruBE의 신뢰된 후처리 workflow가 담당한다. skill 테스트는 기본적으로 dry-run과 fixture를 사용하며 실제 runner 비용을 발생시키는 dispatch는 명시적 실행 요청에서만 허용한다.

## 10. 범위 밖

- OnMaru application runtime에 toolkit library import
- external object storage provisioning
- automatic production promotion/rollback
- benchmark 결과만으로 application source/test를 자동 수정
- PR label만으로 유료 반복 benchmark 자동 실행
- 격리된 staging이 준비되기 전 production 대상 CD 부하·배포 benchmark

## 11. Open-source References

- GitHub reusable workflows: https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows
- Gradle GitHub Actions: https://github.com/gradle/actions/tree/main/setup-gradle
- dorny/paths-filter (MIT): https://github.com/dorny/paths-filter
