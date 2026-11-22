# 용어 migration

이 문서는 예전 이름과 현재 계약 이름을 대응시킨다. 살아 있는 가이드, fixture, 대시보드 질의는 현재 이름을 쓴다. 과거 보고서와 PRD는 당시의 수치와 식별자를 그대로 두고, 맨 위에 이 문서로 가는 migration 메모만 추가했다. ADR은 원문을 바꾸지 않는다. 현재 ADR-0002, 0003, 0005는 proposed 상태이며 다른 ADR로 대체되지 않았으므로 superseded 관계도 추가하지 않았다.

## 용어 대응표

| 예전 이름 또는 형식 | 현재 이름 또는 계약 | 바뀐 이유와 주의 |
| --- | --- | --- |
| OnMaru-backend의 Java lane (native CI 한 줄 흐름) | Spring Boot 백엔드 검증 lane, logical ID `spring-affected`, `spring-full` | Java 21과 Spring Boot 검증이 lane의 실제 범위이기 때문이다. Toolkit은 job 표시 이름에 `[logical-id]` 표지가 있을 때만 이 ID를 인정하며, 표지가 없으면 `other`와 `unmapped`로 드러낸다. |
| `java-affected` | `spring-affected` | 영향 범위 선택(affected) 실행의 logical ID이다. 표시 이름 변경만으로는 identity가 바뀌지 않도록 명시적으로 매핑한다. |
| `java-full` | `spring-full` | 전체 suite 실행의 logical ID이다. 같은 이유로 명시 매핑을 쓴다. |
| `cache_state` 문자열 (module evidence의 단일 값) | `cache.cacheIdentity`의 구조화된 `layers`와 `seedProvenance` | 한 문자열로 dependency, Build, Configuration의 cache 상태를 표현할 수 없었기 때문이다. 기존 기록은 `quality: legacy-limited`로 읽고 원문 문자열을 `legacy.cache_state`에 그대로 둔다. 문자열에서 레이어 상태를 추론하지 않는다. |
| `critical_path_seconds` (workflow output) | `longest_module_duration_seconds`와 `dag_critical_path_quality` | 최장 모듈 명령 시간은 DAG critical path가 아니다. 새 출력은 측정 가능성을 함께 준다. 기존 출력은 빈 값을 반환하므로 숫자로 읽던 consumer는 품질을 확인한 뒤 변환해야 한다. 기존 pinned commit의 동작은 그대로다. |
| CI Grafana의 `job` 라벨 | `ci_job` 라벨 | Prometheus에서 `job`은 scrape 대상의 예약 라벨이다. 충돌로 metric이 사라진 사건 뒤에 바꿨다. 이 변경은 metric payload를 바꾸므로 기존 replay identity는 `replay_plan_mismatch`가 된다. 새 run이나 검토된 replay 상태 migration으로 처리한다. |
| `toolkit_ci_*` 계열 metric과 `onmaru_ci_*` 계열 metric | 둘 다 현재 계약 | 이름 변경이 아니다. `toolkit_ci_*`는 workflow, job, step, module 관측(#120)이고, `onmaru_ci_*`는 layer 관측(#144)이다. 두 계열을 같은 패널에서 합산하지 않는다. |
| 단일 `critical_path` 해석 | 중첩 구간과 unavailable 품질 | 구간을 더하지 않는다. causal graph가 없으면 critical path는 `unavailable`이다. |

## 워크플로 identity는 바뀌지 않는다

이 저장소의 workflow 이름은 그대로 유지한다. `.github/workflows/ci.yml`의 표시 이름은 `CI`이고, `.github/workflows/module-benchmark.yml`의 표시 이름은 `module-benchmark`이다(문서에서 "Module Benchmark"로 부르는 것은 같은 workflow를 가리킨다). `CI Observability`는 이 저장소의 workflow 파일이 아니며, ADR-0005에 따라 consumer가 소유하는 관측 workflow이다. 이 이름과 파일은 migration 대상이 아니다.

## 과거 문서에 붙인 메모

다음 문서는 본문을 바꾸지 않고 맨 위에 이 문서로 가는 메모를 추가했다. 수치, 날짜, 식별자, 판정은 그대로 둔다.

- [2026-09-27 CI Toolkit 문제 해결 기록](../reports/2026-09-27-onmaru-ci-toolkit-troubleshooting-journey.md): Java lane과 `critical_path_seconds`의 당시 의미를 다룬다.
- [2026-10-01 CI 벤치마크 관측 정책 보고서](../reports/2026-10-01-ci-benchmark-observability-policy.md): `critical_path_seconds`의 당시 설명을 다룬다.
- [OnMaruBE 모듈별 병렬 CI·Benchmark PRD](../prd/onmarube-parallel-ci-benchmark.md): deprecated 출력 표를 다룬다.
- [2026-09-26 모듈 benchmark 출력 줄바꿈 계획](../superpowers/plans/2026-09-26-module-benchmark-output-newlines.md): Java lane 이름을 다룬다.

## 적용 규칙

살아 있는 문서와 fixture에서 새 이름을 쓰되, 과거 수치는 고치지 않는다. 기존 reader는 legacy 형식을 계속 읽는다. legacy reader를 제거하는 결정은 retention과 consumer upgrade가 끝난 뒤에 따로 한다. 그 전까지 `cache_state` 문자열과 `critical_path_seconds` 출력은 호환을 위해 남아 있으며, 새 코드는 이를 새 계약의 근거로 쓰지 않는다.
