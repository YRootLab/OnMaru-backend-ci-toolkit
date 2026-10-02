# OnMaru CI/CD 벤치마크 관측 체계 최종 보고서

작성일: 2026-10-01 · 관련 Issue: [Toolkit #113](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/113) · 결정: [ADR-0005](../decisions/0005-consumer-owned-ci-observability.md)

## 결론과 증거 수준

OnMaruBE가 CI 실행·필수 검사·실패 진단의 소유권을 유지하고, Toolkit은 고정된 버전의 증적 해석·비교·보고 기능을 제공한다. 불변 manifest와 GitHub Actions 실행 기록이 개별 판정의 근거다. OpenTelemetry는 이 근거에서 파생한 메트릭과 CI 시간선 trace를 Grafana Cloud로 전달한다. Grafana Cloud Metrics의 Mimir는 관리형 **Prometheus 호환 메트릭 저장소**이며 PromQL로 조회한다. Grafana는 추세·경보·탐색 화면이다. 이 관측 경로는 필수 CI 판정에 개입하지 않는다.

이 문서는 **설계와 운영 정책**이다. 수집 workflow, exporter, CI 대시보드가 이미 배포됐다는 주장이 아니다. 실제 효과는 후속 구현과 동일 조건 반복 실행으로 검증한다.

| 현재 확인된 사실 | 근거 | 아직 확인되지 않은 것 |
| --- | --- | --- |
| OnMaruBE의 일반 CI와 module benchmark caller가 별도로 존재한다. | OnMaruBE `.github/workflows/ci.yml`, `.github/workflows/module-benchmark.yml` | 관측 연계 후의 실행 시간과 비용 |
| Toolkit module workflow는 명령별 `/usr/bin/time` 결과를 artifact로 만들며 최장 명령 시간을 `critical_path_seconds`로 반환한다. | Toolkit `.github/workflows/module-benchmark.yml` | 실제 workflow DAG critical path와 runner 대기 시간 |
| OnMaruBE는 Grafana Cloud를 서비스 관측 백엔드로 결정했고 Spring API 계측과 Grafana 정의 파일을 갖고 있다. | OnMaruBE ADR-0009, `observability/grafana/` | CI 대시보드의 staging import 및 실제 데이터 표시 |
| 작업 시작 시 release 비교 문서와 비교 코드는 유효 표본 5회를 요구했다. Toolkit PR #117이 비교 코드를 3회로 변경했고 OnMaruBE PR #544가 Toolkit SHA를 고정했다. | 변경 전 ADR-0003·병렬 CI PRD, Toolkit PR #117, OnMaruBE PR #544 | release workflow에서 실제 3회 판정을 연결한 결과 |

## 두 저장소와 관측 서비스의 책임

| 책임 | OnMaruBE | Toolkit | 관리형 관측 서비스 |
| --- | --- | --- | --- |
| Trigger, 테스트·Gradle 명령, `verify`, 배포·승인 | 결정·실행 | 호출된 절차만 제공 | 없음 |
| GitHub token, Grafana 전송 자격 증명, 보관 정책 | 보유·관리 | 요구하거나 저장하지 않음 | 제한된 수신 권한 |
| 원본 실행·로그·artifact, 1차 실패 진단 | 소유 | 증적 형식·오류 코드를 제공 | 링크와 파생 데이터만 표시 |
| 정규화, 비교 가능성, 판정·보고서 형식 | 결과를 소비 | 구현·버전 관리 | 판정의 정본이 아님 |
| 메트릭·trace 저장, 대시보드·경보 | 설정·운영 책임 | 저카디널리티 변환 계약 | Mimir·trace 저장소·Grafana 기능 제공 |

Toolkit의 reusable workflow는 OnMaruBE가 지정한 immutable commit SHA로 **OnMaruBE의 Actions 실행 안에서** 동작한다. Toolkit 저장소에서 OnMaruBE의 CI를 원격으로 시작하거나 실패 때 Toolkit 저장소에 문의하는 경로를 만들지 않는다. 수정이 Toolkit 코드에 필요하다고 판명된 경우에만 버전·오류 코드·원본 실행 링크를 근거로 별도 Toolkit Issue를 연다.

## 측정·trace·증적 계약

| 지표 | 정의 | 누락 시 처리 |
| --- | --- | --- |
| workflow 경과 시간 | GitHub가 제공하는 신뢰 가능한 시작·완료 시각의 차이. 완료 시각을 확정할 수 없으면 근삿값으로 표기한다. | `unavailable`/`estimated` 품질 표시 |
| 관측된 job window | 가장 이른 job 시작부터 가장 늦은 job 완료까지. workflow 경과 시간과 다른 지표다. | 시각 누락 시 계산하지 않음 |
| job·step 실행 시간 | 각각의 `completed_at - started_at` | 누락·음수·역전 시 invalid |
| runner 대기 시간 | job별 queue 진입 시각이 신뢰 가능한 소스에서 확인될 때만 계산 | GitHub API에 해당 시각이 없으면 `unavailable` |
| 총 작업량 | 완료된 job 실행 시간의 합. runner 비용의 대리 지표로만 사용 | 누락 job을 제외한 부분값임을 표시 |
| DAG critical path | 실제 dependency graph와 job 시간을 모두 확인한 경우에만 계산 | 그래프 불완전 시 `inconclusive`; 최장 모듈 시간으로 대체하지 않음 |
| 모듈 실행·Gradle cache | 모듈 명령 시간과 Gradle이 직접 보고한 cache·task 결과를 구분 | 계측 전에는 hit rate를 추정하지 않음 |

CI trace는 GitHub Actions가 제공한 시각으로 **완료 후 재구성**한다. `workflow → job → step`을 보여 주지만, 실행 중 모든 프로세스에 trace context가 전파됐다는 뜻은 아니다. Gradle task 또는 Spring 요청의 상세 trace는 각각 별도 계측이 있어야 한다. 배포 SHA·image digest로 CI와 서비스 관측을 상관시킬 수 있으나, 임의의 CI span을 서비스 요청의 parent span으로 만들지 않는다. OpenTelemetry의 [CI/CD span 규약](https://opentelemetry.io/docs/specs/semconv/cicd/cicd-spans/)을 준거로 삼되 규약의 안정성 변경은 버전 계약에서 검토한다.

정본은 OnMaruBE가 보관하는 schema-versioned manifest와 원본 Actions 실행·artifact다. Prometheus 메트릭과 trace는 **파생된 탐색·경보 데이터**이며, 데이터가 만료·유실돼도 과거 release 판정은 manifest에서 재현 가능해야 한다. `run_id + run_attempt`와 증적 digest를 수집 단위로 쓰고 재시도·재수집에서 중복 집계하지 않도록 한다. 전송 실패, 부분 수집, 타임스탬프 누락은 수집 품질 상태로 보고한다. 구현 전에는 저장 방식이나 정확한 전송 보장을 달성했다고 주장하지 않는다.

Prometheus label은 안정적인 workflow, job, environment, 결과와 제한된 module catalog 식별자로만 구성한다. commit SHA, run ID, test name, 파일 경로, 사용자 데이터는 label로 보내지 않는다. 개별 실행 식별자와 원본 URL은 manifest·trace 속성에 둔다. 수집량·보존 기간·cardinality와 Grafana Cloud 비용은 rollout 전에 확인하고 상한을 기록한다.

## 안전한 수집과 실패 진단

OnMaruBE의 신뢰된 기본 브랜치 후처리 workflow가 완료된 실행을 읽어 전송한다. 이 workflow는 PR head 코드를 checkout·실행하지 않으며, PR artifact를 크기·schema·허용 필드로 제한해 입력으로만 취급한다. PR 테스트 job과 fork PR에는 관측 자격 증명을 전달하지 않는다. 최소 권한 GitHub token과 전송 전용 Grafana 자격 증명을 사용한다. `workflow_run`의 권한 상승 위험은 [GitHub 보안 지침](https://docs.github.com/en/actions/reference/security/secure-use)을 기준으로 검증한다.

OnMaruBE의 필수 `verify`는 자체 테스트 결과만으로 결정된다. 테스트 실패, Toolkit 계약·수집 실패, GitHub 인프라 실패, 관측 전송 실패를 다른 코드로 표시한다. 같은 OnMaruBE 실행의 Job Summary와 artifact에 실패한 job·step, 종료 코드, 누락 증적, Toolkit ref, 오류 코드, 조치 링크를 남긴다. Grafana가 불가해도 이 진단은 남고 PR 필수 검사는 관측 서비스에 의해 실패하거나 성공으로 뒤집히지 않는다. 관측 누락은 별도의 운영 경보 대상이다.

## 세 번의 비교와 판정 한계

- 일반 PR 검증은 한 번 실행한다. 파이프라인 구조·affected module·Gradle cache 개선 실험은 baseline과 candidate를 **각각 유효한 성공 3회** 측정한다.
- Release 성능 비교도 baseline과 candidate 각각 **동일 조건의 유효한 성공 3회**를 요구한다. 기존 15% 초과 중앙값 회귀는 `approval_hold`로 남긴다. 이는 승인 검토 요청이지 세 표본만으로 통계적 유의성을 증명했다는 선언이 아니다.
- 모든 개별 값, 중앙값, 범위, 제외 사유와 비교 조건을 보고한다. 실패·취소·timeout·artifact 누락은 성능 표본에서 제외한다. 부족하거나 호환되지 않으면 `inconclusive`다. 변동성이 크면 숫자만으로 개선을 확정하지 않고 검토 근거를 남긴다.
- 개선 실험은 application source와 테스트 범위를 고정하고 workflow/cache 정책만 의도적으로 바꾼다. Release 간 비교는 서로 다른 SHA·image digest를 **각각의 불변 신원**으로 기록하며, 환경·suite·config·runner·cache 조건의 호환성을 검사한다. 서로 다른 release SHA 자체를 불일치 사유로 취급하지 않는다.
- cold cache와 warm cache를 섞지 않는다. CI 개발자 대기 시간, 전체 runner 작업량, 실패율을 함께 판단한다. 더 짧은 모듈 명령 시간만으로 구조 변경을 채택하지 않는다.

이 3회 정책은 기존 5회 정책을 변경한다. [Toolkit PR #117](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/pull/117)이 `compare_module_benchmarks` 코드를 3회 기준으로 변경했고 [OnMaruBE PR #544](https://github.com/YRootLab/OnMaru-backend/pull/544)가 새 불변 Toolkit SHA를 고정해 caller 실행을 검증했다. 다만 현재 module benchmark aggregate는 성공 실행도 `inconclusive`로 반환하므로, **release workflow가 baseline/candidate 각 3회를 수집하고 comparator를 호출하기 전에는 실제 release 판정이 적용됐다고 표시하지 않는다.**

Toolkit SHA 고정과 caller 검증은 [OnMaruBE #542](https://github.com/YRootLab/OnMaru-backend/issues/542)에서 완료했다. 실제 release 3회 판정 연결은 [OnMaruBE #543](https://github.com/YRootLab/OnMaru-backend/issues/543)에서 추적한다.

## 대시보드·부하 시험·보고서

첫 CI 대시보드는 workflow·job 시간 추세, 모듈 시간, 실패·취소율, 수집 완전성, 전송 지연·실패를 표시한다. run 상세 링크와 manifest 링크를 제공한다. 실제 Grafana import, 최소 한 번의 성공·실패 실행 표시, 경보 발송과 복구를 staging에서 확인한 후 운영 화면이라고 부른다. 단순 JSON 파일 존재는 완료 증거가 아니다.

기존 k6 시나리오는 Spring API의 **통제된 staging 부하 시험**에 사용한다. 단계별 요청률, p95 응답 시간, 오류율과 Spring 메트릭·trace를 함께 확인한다. 가상 사용자 수를 실사용자 수로 등치하지 않고, 처음부터 1만 명 부하를 요구하지 않는다. FastAPI의 추후 Lightsail 배포와 그 서비스의 부하·trace 연결은 현재 범위에서 제외한다.

보고서는 사실·추론·미확정을 구분하고, 비교 가능한 표본만으로 delta를 제시한다. Prometheus 쿼리 결과만으로 release gate를 재계산하지 않으며, manifest의 판정과 Grafana 추세가 다르면 데이터 품질 문제로 조사한다.

## 상시 관측과 반복 benchmark 실행 정책

모든 일반 PR과 push에서는 기존 필수 CI를 한 번 실행하고 그 실행 결과만 후처리 관측한다. OpenTelemetry 전송을 위해 테스트를 다시 실행하지 않으며 baseline/candidate 3회 비교도 자동으로 추가하지 않는다.

CI, test 또는 CD 파이프라인 자체를 개선할 때는 별도 `Pipeline Benchmark Experiment`를 명시적으로 실행한다. 실행 시점의 remote `develop` SHA와 커밋된 `feature/*` SHA를 고정하고 각각 성공 표본 3회를 측정한다. PR label은 주 실행 인터페이스로 사용하지 않는다. v1의 CD 실험은 운영을 대상으로 하지 않으며 격리된 staging이 준비될 때까지 비활성화한다.

P3에서 Toolkit CLI와 Agent Toolkit의 `ci-benchmark-experiment` skill이 이 수동 workflow의 dry-run, dispatch, 대기와 결과 요약을 제공한다. CLI와 skill은 관측 secret을 취급하지 않고, 일반 PR required check 또는 자동 배포 gate를 추가하지 않는다. 세부 계약은 [병렬 CI benchmark PRD](../prd/onmarube-parallel-ci-benchmark.md)에 기록한다.

## 실행 순서와 수용 기준

1. **정책과 계약:** 이 보고서, ADR, PRD의 3회 기준을 일치시키고 Toolkit 비교 코드와 OnMaruBE caller의 변경 Issue를 분리한다.
2. **정확성:** [Toolkit #115](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/115)에서 GitHub run·job·step 수집, 누락·재실행·중복 처리와 consumer-local 실패 보고를 fixture와 실제 Actions 실행으로 검증한다.
3. **관측:** 같은 Issue의 관리형 Prometheus 메트릭·CI trace를 shadow 모드로 전송하고, 원본 manifest와 대시보드의 값·링크·보존 한계를 대조한다. 수집 실패는 필수 CI와 독립적이어야 한다.
4. **최적화:** 그다음 [OnMaruBE #525](https://github.com/YRootLab/OnMaru-backend/issues/525)의 affected module·Gradle 구조 개선과 build cache·configuration cache 템플릿을 동일 범위의 전후 3회 측정으로 평가한다. `setup-java`의 Gradle 의존성 캐시를 task output cache나 configuration cache hit로 잘못 해석하지 않는다.
5. **P3 실행 편의:** 정확한 증적과 관측 경로가 검증된 뒤 전용 workflow·Toolkit CLI·Agent Skill로 필요할 때만 3회 실험을 시작하고 결과를 회수한다.

관련 근거: [GitHub workflow jobs API](https://docs.github.com/en/rest/actions/workflow-jobs), [Grafana Cloud의 OTLP·Mimir 매핑](https://grafana.com/docs/grafana-cloud/send-data/otlp/otlp-format-considerations/), [Gradle build cache와 configuration cache의 차이](https://docs.gradle.org/current/userguide/configuration_cache.html).
