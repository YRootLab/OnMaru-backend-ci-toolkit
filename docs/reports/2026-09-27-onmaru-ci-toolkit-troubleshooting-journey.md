# OnMaru CI Toolkit은 왜 필요했고, 어디서 느려졌는가

- 상태: 트러블슈팅 기록
- 기준일: 2026-09-27
- 관련 이슈: #110
- 대상: `OnMaru-backend-ci-toolkit`과 consumer인 `OnMaru-backend`

## 먼저 결론부터: Toolkit은 의미가 있다. 단, 역할을 바로잡아야 한다

이 Toolkit의 가치가 “모듈을 가능한 한 많이 GitHub Actions runner로 나누는 것”이라면 지금의 결과는 실패에 가깝다. 동일한 Gradle·Spring 테스트를 runner마다 다시 준비하는 방식은 개발자를 더 오래 기다리게 하고, runner 사용량도 늘렸다. 실제로 module-per-runner shadow benchmark의 중앙값은 약 9분 49초였고, 당시 직렬 CI 중앙값 약 5분 4초보다 느렸다.

하지만 Toolkit의 본래 가치까지 사라진 것은 아니다. Toolkit은 애플리케이션 라이브러리가 아니라, consumer 저장소의 명령을 import 없이 안전하게 조합하는 **CI 제어·측정 계층**이다. 변경 영향 계획, immutable SHA로 고정한 reusable workflow, 실행 근거 artifact, fail-closed fan-in, 비교 불가능한 표본의 배제, 추세 보고서를 제공한다. 이 기능은 “무엇을 실행해야 하는가”와 “그 실행이 실제로 빨라졌는가”를 감이 아니라 증거로 판단하게 한다.

이번 여정에서 얻은 가장 중요한 결론은 단순하다. **PR을 빠르게 만들려면 shared workspace 안에서 필요한 테스트를 선택해야 한다. 전체 모듈 matrix는 성능을 재는 장비이지, 모든 PR의 필수 검사가 아니다.**

## 문제 상황: 숫자는 낮아 보였는데, 기다림은 길어졌다

OnMaru Backend에는 Java/Spring API, Python/FastAPI, 계약 검증, 문서·생성물 검증이 함께 있다. 초기 CI는 이 작업을 한 runner에서 수행했으며, 가장 긴 Spring API 테스트가 전체 결과를 붙잡았다. 여기서 “독립 모듈을 병렬 runner로 나누면 빨라질 것”이라는 가설이 출발점이었다.

문제는 GitHub Actions 화면에 여러 종류의 시간이 동시에 있다는 점이다. 개별 module job의 실행 시간, 가장 긴 module 명령 시간, workflow의 시작부터 종료까지의 wall-clock, 모든 runner가 사용한 시간의 합은 같은 숫자가 아니다. 이 구분을 충분히 엄격하게 하지 않으면, 짧은 module 시간이나 낮은 `critical_path_seconds`를 보고 전체 PR도 빨라졌다고 오해할 수 있다.

PR #413은 그 오해를 드러낸 좋은 사례였다. 일반 CI는 약 6분 35초에 끝났지만, 별도 Module Benchmark는 16개 job을 `max_parallel: 4`로 실행해 약 14분 50초가 걸렸다. 일반 CI는 runner 약 7.6분을 사용했고, benchmark만 약 25.6분을 사용했다. 둘을 같이 보면 개발자가 모든 표시를 기다릴 때 더 오래 걸리고, runner 비용도 크게 늘어난다. benchmark 결과의 `critical_path_seconds`는 가장 긴 **개별 명령**을 뜻할 뿐, matrix 대기열·runner 준비·aggregate 시간을 포함하는 PR wall-clock이 아니다.

## 시간 순서로 본 시도와 결과

### 1. 직렬 CI 기준선: 병목은 Spring API였다

직렬 구조에서는 Java, 계약, AI, hygiene가 같은 흐름 안에서 진행돼 독립적인 짧은 검사가 긴 Spring API 테스트 뒤에 대기했다. 이 시점의 관찰은 “Spring API 테스트를 삭제하자”가 아니었다. 검증을 유지하되, 서로 의존하지 않는 lane은 동시에 시작할 수 있다는 것이었다.

초기 master의 직렬 표본은 4분 36초, 5분 4초, 6분 43초처럼 크게 흔들렸다. 이 값은 당시 코드와 테스트 범위의 관찰값이다. 이후 Stamp 모듈, migration, 통합 테스트가 추가된 현재 실행과 단순 비교하면 안 된다. 코드와 명령, cache 상태, runner가 다르면 빠르거나 느린 실행 하나는 성과도 회귀도 아니다.

### 2. module-per-runner shadow benchmark: 병렬화 자체가 해답은 아니었다

Toolkit의 `module-benchmark.yml`은 consumer의 module catalog를 읽고 `detect → matrix test → aggregate → verify` 흐름을 만든다. 각 matrix job은 새 `ubuntu-latest` runner에서 consumer가 소유한 Gradle 또는 Python 명령을 실행하고, `/usr/bin/time` 결과와 실행 상태를 artifact로 남긴다. `max_parallel: 4`는 한 번에 네 job만 허용한다.

이 구조는 측정에는 유용하지만, Gradle monorepo의 일반 CI를 빠르게 만드는 방식으로는 맞지 않았다. 각 job이 checkout, JDK/도구 준비, Gradle configuration, 의존성 해석, 컴파일 산출물 생성을 따로 수행한다. 특히 `spring-api`는 모든 모듈과 adapter를 조립하고 Testcontainers를 사용하므로 가장 늦은 matrix 묶음에서 실행됐다. 결과적으로 3회 shadow 실행의 중앙값은 약 9분 49초였고, 직렬 기준보다 느렸다.

이 실패는 무의미하지 않았다. “모듈을 runner 단위로 분해하면 항상 빨라진다”는 가정을 실제 실행으로 반증했고, 해당 workflow가 기존 required CI를 대체하지 않은 shadow 경로였기 때문에 운영 검증을 약화시키지 않았다.

### 3. shared-workspace fan-out: 처음으로 공정 비교에서 개선을 만들었다

다음 변경은 module matrix를 required path로 넣는 대신, OnMaru Backend의 native CI를 `plan → hygiene / java / contract / ai → verify`로 바꿨다. Java lane은 여러 Gradle task를 **한 번의 Gradle 호출**로 실행한다. 이 방식은 한 runner 안에서 Gradle configuration과 컴파일 산출물을 공유하며, Java와 독립적인 AI·계약·hygiene은 동시에 실행한다.

동일 애플리케이션 소스에서 직렬 CI와 shared-workspace fan-out CI를 각각 세 번 실행했을 때 중앙값은 7분 54초에서 6분 55초로 59초, 12.4% 줄었다. 이 숫자는 비교 조건을 맞춘 실제 개선이다. 다만 Java 전체 테스트를 계속 실행했으므로 작은 모듈 PR의 핵심 병목인 `:apps:spring-api:test`는 남아 있었다.

### 4. benchmark rollout의 혼선: 관측 경로가 PR 경험을 방해했다

consumer의 `.github/workflows/module-benchmark.yml`은 `pull_request`와 `develop` push에서 reusable Toolkit workflow를 호출한다. PR #413처럼 release branch와 develop의 차이가 넓으면 catalog가 현재 12개 module을 모두 선택한다. 일반 CI 6 jobs와 별도로 benchmark 16 jobs가 생긴다. 이 benchmark는 현재 branch protection의 required `verify`가 아니지만, GitHub UI에서 많은 check와 긴 실행 시간으로 보인다.

여기서 “Toolkit이 CI를 느리게 만들었다”는 인상은 사실의 일부다. 정확히는 Toolkit의 **측정용 matrix를 일반 PR의 빠른 검증 경험에 겹쳐 놓은 운영 정책**이 느리게 만들었다. reusable workflow가 수행한 일은 의도대로 evidence를 모으는 것이었지만, 호출 시점과 목적이 잘못 배치됐다.

## 근본 원인: 세 종류의 일을 한 파이프라인에 섞었다

첫째는 merge를 판단하는 검증이다. 빠르게 실패를 알려야 하며, 변경 범위에 비례해야 한다. 둘째는 release 전에 수행하는 전체 통합 검증이다. 느려도 되지만 누락이 없어야 한다. 셋째는 성능 관찰과 추세 비교다. 전체 matrix, artifact, 반복 표본, runner 사용량을 모아야 하므로 가장 비싸다.

이 세 목적을 모두 PR마다 동일한 강도로 수행하면 어떤 목표도 제대로 달성하지 못한다. PR은 느려지고, 전체 검증은 matrix와 중복되고, benchmark는 cache·queue 때문에 공정한 비교 조건을 잃는다. 특히 현재 Toolkit의 `critical_path_seconds`는 module 명령 중 최대값이므로, workflow wall-clock 또는 모든 runner 비용을 대표하는 지표로 쓰면 안 된다.

## Toolkit 코드의 책임과 한계

`module-plan`은 consumer catalog와 changed path를 입력으로 받아 실행할 module 목록을 출력한다. 경로를 알 수 없거나 공용 설정이 바뀌면 full suite를 선택해야 한다. 이 fail-closed 정책은 속도보다 검증 누락을 막는 경계다.

`.github/workflows/module-benchmark.yml`은 그 계획을 matrix로 바꾸고 module별 artifact를 모은다. aggregate는 성공·실패·inconclusive와 개별 명령 기준 critical path를 기록한다. 이 workflow는 consumer test command와 secret을 소유하지 않으며, immutable 40자리 SHA로 고정된 Toolkit 구현만 checkout한다. 이 경계는 여전히 옳다.

다만 이 workflow는 Gradle build cache나 한 runner의 compilation output을 matrix job 사이에 공유하지 않는다. 따라서 Java modular monolith의 daily PR gate로 쓰기보다, nightly·수동·release benchmark로 쓰는 것이 설계와 비용에 맞는다. Issue #107/PR #108이 workflow run마다 concurrency group을 분리한 것은 서로 다른 run의 pending job 취소를 막는 수정이다. 이 수정은 실행 안정성을 높였지만, full matrix가 PR에 적합하다는 뜻은 아니다.

## 선택지와 판단

| 선택지 | PR 속도 | 비용 | 검증 안전성 | 판단 |
| --- | --- | --- | --- | --- |
| 모든 module을 새 runner matrix로 실행 | 낮음 | 높음 | 높음 | benchmark 전용 |
| 모든 PR에서 Java 전체 suite 실행 | 중간 | 중간 | 높음 | 앱·DB·공용 변경 fallback |
| 변경 module을 한 Gradle 호출로 선택 실행 | 높음 | 낮음 | 조건부 높음 | 일반 도메인 PR의 목표 |
| Spring/Testcontainers를 무작정 병렬 fork | 불확실 | 중간 | 낮음 | 계측·격리 전에는 금지 |

## 복구 계획: 무엇을 남기고 무엇을 멈출 것인가

1. Module Benchmark는 PR과 `develop` push의 기본 경로에서 분리하고, `workflow_dispatch`, nightly, release candidate에서 전체 matrix를 수행한다. 이 workflow는 삭제하지 않는다. 성능 추세·모듈별 evidence·회귀 분석의 역할을 맡긴다.
2. PR required CI는 shared-workspace fan-out을 유지한다. 이것은 이미 같은 소스 반복 실행에서 12.4% 단축을 확인했다.
3. Java PR lane에는 path-to-task 선택기를 추가한다. 단일 domain 변경이면 해당 module test와 빠른 Spring 경계 테스트만 한 Gradle 호출로 실행한다. `apps:spring-api`, JDBC, shared module, migration, Gradle/workflow, 다중 module 변경은 반드시 전체 Java suite로 fallback한다.
4. `spring-api`의 JUnit class duration, Testcontainers 시작 횟수, migration 시간을 먼저 artifact로 집계한다. 이후 가장 느린 테스트부터 공유 PostGIS container·schema 격리·제한된 fork를 한 변수씩 검증한다.
5. 채택 기준은 단일 module PR 중앙값 45% 이상 단축이다. 실패율, p95, 검증 누락이 나빠지거나 이 기준을 넘지 못하면 선택 실행을 required policy로 승격하지 않는다.

## 최종 판단

지금까지의 작업은 “아무것도 안 한 상태가 더 빨랐다”는 결론으로 끝나면 안 된다. 그렇게 보이는 오래된 실행은 다른 코드·다른 테스트 범위의 숫자이고, module matrix가 느리다는 사실은 실제로 확인된 중요한 반증이다. 잘못된 병렬화는 분명히 비용을 늘렸다. 그 부분은 중단·분리해야 한다.

반면 shared-workspace fan-out, immutable reusable workflow, consumer-owned catalog, evidence artifact, fail-closed verification은 다음 개선의 안전장치다. Toolkit은 속도를 마술처럼 만드는 제품이 아니다. 속도 개선 가설을 안전하게 실험하고, 실패를 빠르게 드러내며, 성공을 같은 조건에서만 기록하게 하는 도구다. 이 역할을 지킬 때만 OnMaru Backend뿐 아니라 다른 Java monorepo에도 재사용할 이유가 있다.

## 근거 실행

- 직렬 기준선 표본: [36210391321](https://github.com/YRootLab/OnMaru-backend/actions/runs/36210391321), [36210694890](https://github.com/YRootLab/OnMaru-backend/actions/runs/36210694890), [36211063456](https://github.com/YRootLab/OnMaru-backend/actions/runs/36211063456)
- 공정 비교의 shared-workspace fan-out 표본: [36220121070](https://github.com/YRootLab/OnMaru-backend/actions/runs/36220121070), [36222274315](https://github.com/YRootLab/OnMaru-backend/actions/runs/36222274315), [36222669964](https://github.com/YRootLab/OnMaru-backend/actions/runs/36222669964)
- module-per-runner shadow 관찰: [36211314573](https://github.com/YRootLab/OnMaru-backend/actions/runs/36211314573)
- release PR full-matrix 관찰: [PR #413](https://github.com/YRootLab/OnMaru-backend/pull/413), [CI 36275169841](https://github.com/YRootLab/OnMaru-backend/actions/runs/36275169841), [Module Benchmark 36275170237](https://github.com/YRootLab/OnMaru-backend/actions/runs/36275170237)
