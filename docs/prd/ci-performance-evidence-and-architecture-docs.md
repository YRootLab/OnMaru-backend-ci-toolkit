# PRD: OnMaru CI 계층별 성능 evidence와 Toolkit 문서 체계 (#139 → #140)

- 상태: Draft
- 출처: GitHub Issue #139, #140 본문과 댓글 전체 (YRootLab/OnMaru-backend-ci-toolkit)
- 구현 순서: #139 → #140 (#140 문서와 이름 migration은 #139의 schema 이름에 의존)
- 충돌 규칙: 댓글의 최신 결정을 본문보다 우선했다. 아래 "본문 대비 정정 사항" 참고.

---

## 1. Problem Statement

OnMaru Backend는 Toolkit을 애플리케이션 runtime 의존성이 아니라 **SHA 고정 reusable workflow와 SHA 고정 checkout의 Python CLI**로 사용한다. 현재 Toolkit은 job 단위 timeline, 모듈 benchmark, 비교 가능성 판정, OTLP/Grafana 출력을 제공하지만 다음이 부족하다.

- Gradle configuration·task·cache, JUnit 선택·실행 수, Spring Context, Testcontainers, Flyway 시간이 공통 schema에 없다.
- 일반 CI job catalog가 비어 있어 대부분의 job이 `ci_job="other"`로 합쳐진다. "Java job이 느리다"는 관측은 가능해도 critical path 병목은 설명하기 어렵다.
- Build Cache 상태가 `cache_state: str` 자유 문자열이라 `fresh runner`와 `cold cache`를 구분하지 못하고, dependency cache와 Build Cache가 섞인다.
- README와 문서가 Toolkit의 역할, 소비 방식, 신뢰 경계, 데이터 흐름을 한 번에 설명하지 못한다.

비용: OnMaru Backend #867의 affected-test/Build Cache 최적화 효과를 근거 있게 측정·승격할 수 없다. 문서가 없으면 신규 기여자와 운영자가 소유 경계를 잘못 이해한다.

## 2. Solution

두 단계로 진행한다.

- **#139 (구현):** `ci-performance-evidence/1.0` 계약을 도입하고, consumer가 만든 계층별 evidence를 검증·정규화·비교·OTLP 변환·Grafana까지 연결한다. Cache는 구조화된 identity vector로 바꾸고, 전환 기간 동안 v1 문자열과 v2 구조를 모두 읽는다.
- **#140 (문서):** README는 큰 그림과 소비 방식을, 상세 architecture 문서는 단계별 동작을 설명한다. 상세 다이어그램의 source는 D2, README overview는 Mermaid다. 과거 문서는 보존하고 migration note만 추가한다.

### 2.5 상위 문서와의 관계

이 PRD는 Toolkit 쪽 구현·문서 범위만 다룬다. 상위 목표와 성공 기준은 OnMaru Backend `feature/867-affected-ci-optimization`의 `docs/planning/ci-affected-test-optimization/product-prd.md`가 정본이다. 이 PRD는 그 문서의 측정 계약(evidence, cache identity, job ID, metric 이름)을 구현하는 역할이다. 상위 문서와 충돌하면 상위 문서를 따른다. 상위 문서는 아직 feature 브랜치에 있으며 develop에 병합되지 않았다.

## 3. User Stories

1. **Backend 성능 담당자**로서, Gradle·cache·테스트·Spring Context·Testcontainers·Flyway 시간을 계층별로 보고 싶다. 그래야 affected-test 최적화의 실제 병목을 찾을 수 있다.
2. **Backend 성능 담당자**로서, fresh runner와 cold cache, warm cache를 구분해 보고 싶다. 그래야 "빨라졌다"는 주장이 실험 조건 차이가 아닌지 확인할 수 있다.
3. **Toolkit 운영자**로서, 기존 `cache_state` 문자열 데이터를 잃지 않고 새 schema로 옮기고 싶다. 그래야 과거 Grafana 시계열이 끊기지 않는다.
4. **Grafana 사용자**로서, 한국어 Actions 표시 이름이 바뀌어도 같은 job 시계열을 보고 싶다.
5. **Grafana 사용자**로서, 느린 run을 찾은 뒤 Tempo trace와 원본 Actions artifact까지 이동하고 싶다.
6. **신규 기여자**로서, Toolkit이 plugin인지 Python package인지 reusable workflow인지 1분 안에 알고 싶다.
7. **Backend 개발자**로서, Toolkit exporter가 실패해도 내 PR의 required check 판정이 바뀌지 않는다는 것을 알고 싶다.
8. **보안 담당자**로서, 다이어그램과 문서에 secret, signed URL, private endpoint가 들어가지 않음을 검증하고 싶다.

## 3.5 성공 지표

Toolkit이 직접 책임지는 지표와, 상위 Backend 목표를 측정 가능하게 만드는 지표를 나눈다.

**Toolkit 자체 완료 지표**
- 계층별 evidence가 누락 없이 수집되고, 누락 값은 0이 아닌 `unavailable`로 표시된다.
- instrumentation on/off 비교에서 수집 overhead가 workflow 중앙값의 3% 또는 15초 중 **작은 값** 이하다.
- baseline과 candidate의 cache identity, schema version, profile이 다르면 비교 결과가 `incomparable`이다.
- 기존 Actions·OTLP·Grafana 경로가 그대로 동작하고, 새 metric이 label 허용 목록을 벗어나지 않는다.

**상위 Backend 목표 (참조, Toolkit 데이터로 측정)**
- 단일 모듈 feature PR required CI 중앙값: 기준 대비 40% 이상 감소
- feature PR required CI p95: 8분 이내 (안정화 후 3~5분)
- 문서 전용 변경: 90초 이내
- warm 대상 task의 Build Cache hit ratio: 60% 이상
- 단일 모듈 변경 시 무관 모듈 test 실행 수: 70% 이상 감소
- affected selection false negative: 0
- 전체 회귀의 실패율과 flaky 재시도 비율: 악화 없음

## 4. 구현 결정

### 4.1 Module 경계 (#139)

- **Evidence contract:** `ci-performance-evidence/1.0` 정의, 제한 검증, valid/invalid/boundary fixture. 누락값은 `unavailable` 또는 quality 상태로 보존하고 0으로 바꾸지 않는다.
- **Job catalog:** consumer가 제공하는 bounded logical ID. 표시 이름과 logical ID를 분리한다. 매핑되지 않은 job은 `other`로 두되 수량과 mapping quality를 노출한다.
- **Cache identity:** 구조화 identity. v1 문자열과 v2 구조를 모두 읽고, writer는 v2만 생성한다.
- **Normalization/merge:** Actions timeline, module evidence, performance evidence를 identity와 clock 경계를 검증해 병합한다.
- **Comparison:** baseline/candidate comparability, critical path, serial sum. 중첩 구간을 이중 계산하지 않는다.
- **OTLP/Grafana transform:** bounded metric·trace 변환. 고카디널리티 label과 원문을 거부한다.

기존 `cache_state` 소비자는 v1/v2 reader seam을 통해 옮긴다.

### 4.1.1 Metric 계약 (상위 Backend PRD 기준)

| Metric | 의미 |
|---|---|
| `onmaru_ci_workflow_duration_seconds` | queue 포함·제외 wall time을 명시적으로 구분 |
| `onmaru_ci_job_duration_seconds` | logical job별 실행 시간 |
| `onmaru_ci_gradle_task_duration_seconds` | Gradle task 유형별 시간 |
| `onmaru_ci_gradle_tasks_total` | 실행, cache hit, up-to-date, skipped task 수 |
| `onmaru_ci_build_cache_operations_total` | cache load/store/hit/miss/error 수 |
| `onmaru_ci_build_cache_bytes` | cache restore/upload byte |
| `onmaru_ci_tests_selected_total` | planner가 선택한 test 수 |
| `onmaru_ci_tests_executed_total` | 실제 실행된 test 수 |
| `onmaru_ci_spring_context_loads_total` | Spring Context 생성 횟수 |
| `onmaru_ci_testcontainers_startup_seconds` | container 준비 시간 |
| `onmaru_ci_affected_fallback_total` | 전체 검증 fallback 횟수와 유형 |
| `onmaru_ci_selection_mismatch_total` | affected 성공 후 full 실패 등 선택 불일치 수 |

- **허용 label:** `workflow`, `lane`, `test_type`, `cache_result`, `module`, `event`, `result` (집합 크기가 제한된 값만)
- **금지 label:** commit SHA, PR 번호, run URL, test class 이름, container image digest. 이 값은 구조화 log나 evidence artifact에 두고 trace correlation으로 연결한다.
- `lane`(metric)과 `ci_job`(telemetry 표) 중 어느 이름을 label로 쓸지 Open Question 6에서 정한다.

### 4.1.2 측정 수집 지점 (계층별 hook, AOP 주 수집기 사용 안 함)

| 영역 | 수집 지점 | 비고 |
|---|---|---|
| Gradle 구성 | init script의 공개 lifecycle event | cache hit 경로에서 생략될 수 있으므로 Gradle 9.7.1에서 검증 |
| Gradle task | BuildService와 OperationCompletionListener 기반 completion event | configuration-time callback만 쓰면 cache reuse 실행에서 event가 빠질 수 있음 |
| Build Cache | task result와 setup-gradle summary | 원문 key, signed URL 저장 금지 |
| JUnit | JUnit Platform listener와 XML 결과 요약 | module·test type별 수 |
| Spring Context | TestContext listener, ApplicationStartup 또는 동등 hook | class 이름이 아니라 허용된 profile category |
| Testcontainers | 공통 container factory 또는 JUnit extension | `postgres`, `postgis`처럼 승인된 category만 |
| Flyway | migration callback과 validation 경계 | validate, migrate, fixture 분리 |

금지: Gradle 비공개 build operation API나 console log 정규식에 핵심 계약을 의존하지 않는다. 공개 event가 주지 않는 값(cache byte 등)은 setup action의 구조화 출력이나 별도 artifact에서 받고, 없으면 `unavailable`.

### 4.2 Cache identity vector (댓글 기준 확정)

`cache_state: str`을 즉시 삭제하지 않는다. 새 schema version에 다음 구조를 추가한다.

```json
{
  "cacheIdentity": {
    "workspace": "fresh",
    "dependencyCache": "warm",
    "gradleBuildCache": "cold",
    "gradleConfigurationCache": "disabled",
    "containerImageCache": "unknown",
    "namespace": "bounded-config-digest",
    "seedProvenance": { "status": "verified", "trustedWriter": "develop", "inputDigest": "sha256:..." }
  }
}
```

각 layer의 enum:

| 값 | 의미 |
|---|---|
| `disabled` | 기능이 꺼져 있거나 저장·복원 경로가 없음 |
| `cold` | restore를 시도했지만 동일 identity entry가 없고 miss가 증명됨 |
| `warm` | 동일 immutable input identity의 entry를 측정 전에 성공적으로 복원함 |
| `partial` | 같은 layer에 hit와 miss가 함께 있음 |
| `invalidated` | entry는 있었지만 입력·format·toolchain 변경으로 사용 불가 |
| `unknown` | API 또는 evidence 부족으로 판정 불가 |

규칙:
- `fresh runner`는 `cold cache`와 같지 않다.
- `warm`은 cache action step 성공이 아니라 matching key/digest restore와 실제 hit evidence가 있어야 한다.
- 첫 seed 실행은 warm 성능 표본에서 제외한다.

### 4.3 비교 profile (댓글 기준 확정)

| Profile | 목적 | 조건 |
|---|---|---|
| `controlled-cold` | 순수 실행 비용(최악) | 격리 namespace 또는 cache 비활성, 관련 layer의 miss/disabled 증명 |
| `controlled-warm` | 재사용 출력의 최대 효과 | trusted seed 완료 후 동일 input digest restore, seed 제외 |
| `realistic-pr` | 실제 feature PR 경험 | 운영 cache 정책 그대로, layer별 hit/miss 관측 |

- 다른 profile끼리 개선율을 계산하지 않는다. `controlled-cold` baseline과 `controlled-warm` candidate 비교는 `incomparable`이다.
- baseline/candidate는 layer별 state, namespace, input digest, writer trust, restore policy가 같을 때만 직접 비교한다.
- 기존 입력은 `legacy-limited`로 두고, 다른 schema/profile 표본과 직접 비교하지 않는다.

### 4.4 측정 정책 (2026-11-20 재검증 댓글 기준)

- 3~5회는 **초기 중앙값·범위 비교**다. p95는 `insufficient-samples`로 표시하고, 같은 cohort의 **rolling 14일 window 안 유효 실행 100건 이상**일 때만 표시한다. 표본 수와 window를 함께 보여준다. 초기 정책이며 통계적 보장이 아니다. histogram quantile은 bucket 추정임을 명시하고 원시 duration 분위수와 구분한다.
- 각 baseline/candidate 실행은 AB/BA 사전 등록 순서로 교차하고, 자동 재시도나 추가 표집은 하지 않는다. 실패·취소는 분모에 남긴다.
- 대표 workload 일곱 종류(문서 전용, leaf 비즈니스 규칙, shared/domain, controller, persistence, Flyway, root build)를 feature PR 변경 빈도로 가중한 피드백 시간도 함께 보고한다.
- affected 실험은 **전체 test universe digest**와 **selected plan digest**를 분리한다. 선택 목록 변화는 실험 변수라서 허용한다.
- cache 정책과 실제 outcome을 분리한다. cache 도입 실험에서는 disabled/enabled 차이를 사전 선언된 변수로 허용한다.
- cache로 복원된 검증은 실제 JVM test 실행과 별도로 집계한다.
- graph가 없으면 정확한 critical path를 주장하지 않는다. 중첩 Context/container/Flyway 시간은 test duration에 재합산하지 않는다.
- collector는 Gradle wrapper 9.7.1에서 Configuration Cache store/reuse 경로를 검증한다.
- release 승격은 승격 대상의 정확한 SHA/workflow/attempt에서 full regression 성공을 확인한다.
- workload cohort, AB/BA 교차 반복, 실패·취소, runner-minutes, artifact/cache 비용을 함께 보고한다.

### 4.5 Job catalog 이름 (댓글 기준 정정)

Backend 내부 YAML job ID `java`는 호환용으로 유지하고, 표시 이름과 Toolkit logical ID를 분리한다.

| 용도 | Logical ID | 표시 이름 |
|---|---|---|
| 변경 영향 검증 | `spring-affected` | Spring Boot 백엔드 변경 영향 검증 |
| 전체 회귀 검증 | `spring-full` | Spring Boot 백엔드 전체 회귀 검증 |
| 기타 OnMaru job | `change-plan`, `repository-hygiene`, `contract-validation`, `ai-quality`, `required-verdict` | 기존 표시 이름 |

본문의 `java-affected`/`java-full`은 폐기한다. 최상위 `CI`, `Module Benchmark`, `CI Observability` workflow 이름은 completed-run allowlist와 provenance 검증에 쓰이므로 이번에 바꾸지 않는다.

### 4.6 문서 구조 (#140)

- **README:** Toolkit 목적과 비범위, Backend → Toolkit → Grafana primary path, 소비 방식, ownership 표, 일반 CI observability·module benchmark·release benchmark 차이, failure 원칙, 상세 문서 링크. GitHub에서 렌더링되는 Mermaid overview는 8~12개 component와 하나의 primary path만 포함한다.
- **상세 architecture 문서** (`docs/architecture/`): 배포·실행 경계, 호출 흐름, module plan의 fail-closed 동작, evidence 생성·검증·정규화, comparability와 critical path, completed-run 후처리, OTLP·replay·duplicate suppression, Mimir–Tempo identity 연결, Grafana → Tempo → Actions artifact drill-down, credential·fork PR·cardinality·retention 경계, partial/unavailable/inconclusive/failure의 차이, #139 이후 evidence가 합류할 위치.
- **다이어그램 4종:** 시스템 컨텍스트(소유권·신뢰 경계), PR→Grafana sequence, 데이터 lineage(변환마다 schema version·digest·label·unavailable 처리 표시), failure/replay lifecycle(CI 실패와 telemetry export 실패는 별도 상태 머신).
- **소비 방식 비교:**

| 방식 | 현재 사용 | 역할 |
|---|---|---|
| SHA-pinned reusable workflow | 사용 | GitHub Actions orchestration |
| SHA-pinned repository checkout + Python CLI/module | 사용 | collector adapter, validation, transform |
| PyPI package | 사용하지 않음 | 향후 release packaging 후보 |
| GitHub Marketplace Action | 사용하지 않음 | 별도 composite/container Action을 설계할 때만 후보 |
| Backend application runtime dependency | 금지 | 서비스 코드와 Toolkit 격리 |

- **소스 정책:** README 요약은 Mermaid. 상세 다이어그램은 D2 source가 정본이며 SVG를 생성한다. D2 source와 SVG가 어긋나면 CI가 실패하는 check mode를 둔다. Archify는 선택 도구다. 쓰면 typed source·evidence SHA·생성 명령을 commit하고, 독립 HTML은 README 정본을 대체하지 않는다. 미채택이어도 D2 + Mermaid 산출물은 완료해야 한다.

### 4.7 Legacy 이름·schema migration (#140 댓글 기준)

- **Live 문서·test·fixture·dashboard query:** 같은 PR에서 새 logical ID와 schema version으로 갱신한다.
- **Historical 보고서:** 수치와 당시 identity를 바꾸지 않고, 상단에 migration note와 새 architecture 문서 링크만 추가한다. ADR과 승인 기록은 원문을 보존하고 superseded 관계만 기록한다.
- **Cache schema:** 새 version에 structured identity를 추가하고 reader/comparator는 v1과 v2를 모두 읽는다. legacy `cold/warm/unknown`은 layer를 추론하지 않고 `quality=legacy-limited`로 변환한다. writer와 새 fixture는 v2만 생성한다. v1 reader 제거는 retention과 consumer upgrade가 끝난 뒤 별도 breaking release에서 결정한다.
- **전환 순서:** (1) 전체 legacy terminology/schema inventory 생성 → (2) stable logical ID와 compatibility alias 추가 → (3) 새 writer·schema·fixture·display name 적용 → (4) 구·신 reader와 비교 거부 검증 → (5) README·architecture·runbook·dashboard selector 전환 → (6) OnMaru Backend를 같은 immutable Toolkit SHA로 upgrade → (7) baseline/candidate와 Cloud round-trip 확인 → (8) retention 이후 alias 제거 판단.

### 4.8 측정 기능의 비용과 실행 순서

- **Stage 0 (이 PRD 범위의 첫 단계):** 최적화 없이 collector만 추가한다. 같은 commit에서 `instrumentation-off`와 `instrumentation-on`을 각 3회 비교한다.
- **Overhead 예산:** 수집 overhead가 workflow 중앙값의 3% 또는 15초 중 **작은 값**을 넘으면 event 수를 줄이거나 후처리 방식으로 바꾼다. collector가 Gradle cacheability, Spring Context cache key, container lifecycle을 바꾸면 채택하지 않는다.
- **Baseline 선행 조건:** 구현 시작 전에 현재 workflow를 현재 Toolkit ref(`7ecbb89aae771604d9c1c532cf123f239e279110`)로 고정 commit에서 최소 3회(가능하면 5회) 실행해 baseline manifest를 만든다. runner image, JDK, Gradle wrapper, dependency lock, test plan digest, cache 상태가 다른 표본은 합치지 않는다.
- **Toolkit 고정 ref 정책:** 실험 도중 Toolkit ref를 올리지 않는다. Toolkit 변경과 CI 최적화 후보를 동시에 바꾸면 효과를 분리할 수 없다. 새 Toolkit 기능은 별도 PR로 검증하고, baseline과 candidate에 같은 ref를 적용한다.
- **Shadow 비교:** affected와 full을 같은 commit에서 실행해 자동 비교한다. affected 성공·full 실패는 `selection_mismatch`로 기록하고 해당 변경 유형을 즉시 fail-closed 목록에 추가한다. 원인 규명 전에는 재실행으로 flaky 처리하지 않는다.
- **병목 판단:** 병목 순위는 required job의 critical-path 기여도로 판단한다. task duration을 단순 합산하지 않는다.
- **단계 구분 실험:** Gradle invocation을 세 의미 영역(모듈 테스트, 애플리케이션 통합, JAR 생성)으로 나눈 step 분리가 단일 invocation보다 느리면 단일 invocation과 구조화된 Job Summary를 쓴다. 두 후보는 같은 조건에서 3회 이상 비교한다.

## 5. 테스트 결정

| 대상 | 검증 방식 |
|---|---|
| evidence schema | valid, invalid, boundary fixture 단위 테스트 |
| unavailable vs 0 | 누락 필드가 0이 아닌 quality 상태로 보존되는지 테스트 |
| fresh runner vs cold cache | fixture로 구분 확인 |
| mixed cache (dependency warm + build cold, build warm + configuration disabled) | fixture 각각 판정 확인 |
| seed run 제외 | warm 표본에서 seed가 빠지는지 확인 |
| cache identity 불일치 비교 | baseline/candidate가 `incomparable`인지 확인 |
| v1/v2 reader | v1 문자열과 v2 구조 fixture 모두 읽기 |
| serial sum vs critical path | 중첩 구간이 이중 계산되지 않는지 테스트 |
| OTLP transform | 고카디널리티 label과 원문 거부 테스트 |
| histogram/query | p95 요구 충족 또는 unavailable 사유 명시 확인 |
| collector/exporter | local Prometheus·Tempo·Grafana smoke, exporter outage와 replay 테스트 |
| dashboard | dashboard contract test |
| 문서 | Mermaid parse/render, D2 render와 SVG drift, 내부 링크·anchor, 경로 존재 여부, 민감정보 scan, light/dark 대비 확인 |
| 측정 | 3~5회 중앙값·범위, p95는 cohort 조건 충족 전 미표시 |

## 5.5 위험과 의존성

| 위험 | 영향 | 완화 |
|---|---|---|
| Gradle 9.7.1 cache hit 경로에서 event 누락 | 수집값이 조용히 줄어듦 | hit 경로 포함 검증, 누락 시 `unavailable` |
| 고카디널리티 label 추가 | 시계열 폭증, 비용 증가 | label 허용 목록과 회귀 테스트 |
| Spring Context cache key 분화 | Context 재사용 감소, 측정 왜곡 | profile category 정규화, unique Context 수 노출 |
| remote Build Cache backend 미확정 (GitHub Actions cache vs 전용) | artifact 크기·보존·권한 설계 불확실 | 예상 크기, restore latency, 권한 모델 비교 후 결정 |
| runner 변동성 | 3~5회로 결론이 흔들림 | AB/BA 교차, 중앙값·범위 함께 보고, 불충분하면 inconclusive |
| Cache v1/v2 dual reader 복잡도 | 비교 로직 오류 | 구·신 fixture 병행 테스트, 다른 schema 직접 비교 거부 |
| Mimir·Tempo 비용 증가 | Cloud 비용 | 수집량 예산, exporter 비용을 metric으로 보고 |
| 상위 Backend PRD 미병합 | 정본 변경 시 Toolkit 계약 불일치 | 정본 확인을 Open Question으로 관리, 변경 시 이 PRD 갱신 |
| 문서 도구(D2·Archify) 공급망 | 재현성 저하 | repository-local pinned renderer 사용 |

## 6. 비범위

- OnMaru production runtime에 Toolkit library 추가
- consumer 쪽 Gradle/Spring/Testcontainers collector 구현 자체 (consumer 소유)
- 배포 credential 또는 raw service log 수집
- Marketplace 공개 또는 PyPI 배포를 완료 조건으로 강제 (향후 검토)
- 측정 결과만으로 자동 production promotion 승인
- #140 범위의 CI 실행 로직과 telemetry schema 변경 (#139 소유)
- diagram만으로 runtime 정확성을 증명했다고 간주하는 것

## 7. Further Notes

- **보안:** cache backend의 원문 key, credential, signed URL은 artifact나 metric label에 저장하지 않는다. SHA·run ID·상세 provenance는 trace/manifest에 두고, metric은 bounded profile/layer/result만 쓴다. 다이어그램 source에도 secret, token, private endpoint, signed URL을 넣지 않는다.
- **Cardinality:** test class, task path 원문, SHA, PR, run URL은 metric label이 될 수 없다. label budget과 Cloud 비용 제한을 회귀 테스트로 유지한다.
- **신뢰 경계:** reusable workflow는 40자리 commit SHA로 호출한다. baseline과 candidate는 같은 immutable Toolkit identity를 써야 한다.
- **실패 의미:** Toolkit export 실패는 원본 CI conclusion을 바꾸지 않는다. source CI 판정과 telemetry 상태를 분리해 기록한다.
- **Backend 측 정본:** 댓글은 OnMaru Backend `feature/867-affected-ci-optimization` 브랜치의 `docs/planning/ci-affected-test-optimization/product-prd.md`를 정본으로 가리킨다. 이 PRD 작성 시 해당 문서는 열어보지 않았다.

## 8. Open Questions

1. **Backend PRD 정본 확인:** 댓글이 가리키는 feature 브랜치 문서가 이 PRD와 같은 최신 결정인지 확인이 필요하다.
2. **Archify 채택 여부:** 선택 도구다. 채택할지 D2 + Mermaid만으로 갈지 결정이 필요하다.
3. **Cache v1 reader 제거 시점:** retention window와 consumer upgrade 완료 기준을 정해야 한다.
4. ~~p95 공개 기준~~ → 상위 Backend PRD가 "rolling 14일 window 안 유효 실행 100건 이상"으로 정했다. 이 PRD는 그 기준을 따른다. 이번 결정 목록에서 제외한다.
5. **D2/Mermaid drift check 위치:** required check로 둘지 advisory로 둘지 결정이 필요하다.
6. **Metric label 이름 통일:** Backend PRD의 metric label은 `lane`이고 telemetry 표의 필드는 `ci_job`이다. 둘 중 하나로 통일해야 한다.
7. **Archify 채택 시 Backend 측 영향:** 문서 도구 결정이 Backend 문서 정책에도 영향을 주는지 확인이 필요하다.

## 9. 구현 순서

1. **#139-A:** `ci-performance-evidence/1.0` schema, fixture, unavailable 처리
2. **#139-B:** bounded job catalog, `spring-*` logical ID, 표시 이름 분리
3. **#139-C:** cache identity v2 writer + v1/v2 dual reader, `legacy-limited` 변환
4. **#139-D:** 병합, comparability, critical path, serial sum 분리
5. **#139-E:** OTLP transform, histogram, Grafana panel, smoke와 replay 테스트
6. **#140-A:** legacy inventory, glossary, live 문서·fixture·query 갱신
7. **#140-B:** README overview, 상세 architecture 문서, D2 source와 SVG, drift check
8. **#140-C:** historical 보고서 migration note, ADR superseded 기록, 링크·민감정보 검증
9. **통합:** Backend를 같은 immutable Toolkit SHA로 upgrade하고 baseline/candidate와 Cloud round-trip 확인

---

## 9.5 완료 조건 (이슈 체크리스트 통합)

#139 체크리스트
- [ ] `ci-performance-evidence/1.0` schema와 valid/invalid/boundary fixture가 있다.
- [ ] 누락값과 unavailable이 0과 구분되고 partial collection quality가 보존된다.
- [ ] consumer-defined bounded job catalog가 적용되어 OnMaru 일반 CI job이 모두 `other`로 합쳐지지 않는다.
- [ ] Actions timeline, module evidence, performance evidence의 identity와 clock 경계를 검증해 병합한다.
- [ ] baseline/candidate comparability가 runner·toolchain·plan·cache·collector·schema identity를 검사한다.
- [ ] serial sum과 critical path를 구분하고 중첩 구간을 이중 계산하지 않는다.
- [ ] OTLP transform이 고카디널리티 label과 민감한 원문을 거부한다.
- [ ] Grafana에서 Gradle/cache/test/Context/container/Flyway/fallback/mismatch/overhead를 확인할 수 있다.
- [ ] histogram과 query contract가 중앙값·p95 요구사항을 충족하거나 unavailable 이유를 명시한다.
- [ ] local Prometheus·Tempo·Grafana smoke, exporter outage/replay, dashboard contract test가 통과한다.
- [ ] consumer integration guide가 SHA-pinned reusable workflow와 source checkout 방식을 명확히 설명한다.
- [ ] Toolkit release와 OnMaru Backend consumer upgrade는 같은 고정 Toolkit ref로 baseline/candidate를 측정한다.
- [ ] (댓글 추가) cache identity를 versioned structured identity로 migration한다.
- [ ] (댓글 추가) fresh runner와 cold cache를 구분하는 fixture가 있다.
- [ ] (댓글 추가) dependency warm/build cold, build warm/configuration disabled 같은 mixed fixture가 있다.
- [ ] (댓글 추가) seed run이 warm 측정 표본에서 제외된다.
- [ ] (댓글 추가) cache identity가 다른 baseline/candidate는 `incomparable`로 판정된다.
- [ ] (댓글 추가) Grafana가 layer별 hit ratio, restore 비용, 순절약 시간과 cold/warm/realistic profile을 분리한다.

#140 체크리스트
- [ ] README와 상세 architecture 문서에 old→new glossary가 있다.
- [ ] live 문서·test·fixture·dashboard query가 같은 logical ID와 schema version을 사용한다.
- [ ] historical report는 원문 수치와 identity를 보존하고 migration note를 가진다.
- [ ] v1 cache string과 v2 structured identity fixture를 모두 읽는다.
- [ ] v1/v2 또는 다른 cache profile의 직접 비교가 `incomparable`이다.
- [ ] consumer upgrade 전후 Grafana 시계열이 표시 이름 변경으로 단절되지 않는다.
- [ ] terminology/schema drift 검사가 CI에 추가된다.
- [ ] README 첫 화면에서 Toolkit의 목적, 비범위, 현재 소비 방식을 1분 안에 이해할 수 있다.
- [ ] README Mermaid overview가 primary path와 trust boundary를 보여준다.
- [ ] 상세 architecture 문서가 context, sequence, data lineage, failure/replay lifecycle을 설명한다.
- [ ] Backend와 Toolkit의 ownership 표가 책임을 구분한다.
- [ ] 현재 구현과 #139 목표 구조가 시각적으로 구분된다.
- [ ] D2 source와 generated SVG가 저장되고 CI drift 검사를 통과한다.
- [ ] 모든 그림이 caption, alt text, legend와 repository evidence link를 가진다.
- [ ] export 실패가 source CI 판정을 바꾸지 않는다는 failure semantics가 설명된다.
- [ ] Grafana에서 Tempo와 Actions artifact까지 drill down하는 운영 흐름이 설명된다.
- [ ] 문서·diagram 검증 명령이 Toolkit CI에서 통과한다.

상위 Backend PRD의 acceptance criteria(18개 항목)는 해당 문서의 "이 PRD의 acceptance criteria" 절을 정본으로 한다. 이 PRD의 체크리스트는 Toolkit 몫만 옮긴 것이다.

## 본문 대비 정정 사항

- Job catalog: 본문 `java-affected`/`java-full` → 댓글에 따라 `spring-affected`/`spring-full`
- Cache: 본문의 단일 `cache_state` 교체 → 댓글에 따라 즉시 제거하지 않고 v1/v2 dual reader로 이전
- 측정 정책: 2026-11-20 재검증 댓글이 이전 설명의 충돌 조건을 대체
- Archify: 선택 도구로 평가하되, 미채택 시에도 D2 + Mermaid 산출물은 필수
