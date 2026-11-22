# OnMaru Backend Pipeline Toolkit

OnMaru-backend의 CI 실행 시간과 결과를 같은 조건에서 측정·비교하고, Grafana에서 느린 실행의 원인까지 추적하기 위한 재사용 도구 모음입니다. 서비스 애플리케이션의 라이브러리가 아니며, consumer 저장소가 commit SHA로 고정해 호출하는 reusable workflow와 Python CLI로 사용합니다.

## 한눈에 보기

이 Toolkit은 일반 CI의 "통과했는가"에 더해 "얼마나 걸렸는가", "무엇이 가장 오래 걸렸는가", "같은 조건에서 더 나아졌는가"를 설명하도록 돕습니다. 병렬 테스트 전후를 비교하려면 실행 조건이 같아야 하므로, 이 Toolkit은 증적을 정규화하고 비교 가능성을 먼저 확인합니다.

**하지 않는 일(non-goals)**: 테스트 명령을 소유하거나 실행 자격 증명을 보관하지 않습니다. 배포나 release 승격을 결정하지 않으며, 서비스 코드의 런타임 의존성이 되지 않습니다. PyPI 패키지나 Marketplace action으로 배포하지 않으며, 외부 관측 전달이 정확히 한 번 도착함을 보장하지도 않습니다.

**현재 소비 방식**: consumer가 `module-benchmark.yml`을 40자리 commit SHA로 호출합니다. Toolkit은 같은 SHA로 checkout되어 설치되며, 관측 경로는 consumer가 수행하는 post-run 단계에서 선택적으로 실행됩니다. 기본 경로는 **OnMaru-backend CI → Toolkit → Grafana**입니다.

**실패 원칙**: OTLP 전달이 실패하거나 부분 거부되어도 source CI의 판정은 바뀌지 않습니다. 전달 상태는 CI 결론과 별도의 필드로 남습니다. 자세한 구분은 [결과 상태 문서](docs/architecture/outcomes.md)에 있습니다.

```mermaid
flowchart LR
  subgraph consumer["Consumer 신뢰 영역: 비밀값과 테스트 명령"]
    CI["Caller CI<br/>(OnMaru-backend)"]
    Reuse["module-benchmark.yml<br/>고정 SHA 호출"]
    Art["제한된 Actions artifact"]
    Prod["Backend collector<br/>(계획, #139)"]
  end
  subgraph toolkit["Toolkit 신뢰 영역: 비밀값 없이 데이터만 해석"]
    Ver["수집·검증·정규화"]
    Cmp["오프라인 비교"]
    Exp["선택적 OTLP 변환·전달"]
  end
  subgraph obs["관측 영역: 판정 권한 없음"]
    Col["OTel Collector"]
    Store["Mimir·Tempo"]
    Graf["Grafana"]
  end
  Gha["GitHub Actions 실행 페이지"]
  CI ==> Reuse ==> Art ==> Ver ==> Exp ==> Col ==> Store ==> Graf ==> Gha
  Ver -.-> Cmp
  Prod -.-> Art
  classDef planned stroke-dasharray: 5 5,fill:#fff7e0,stroke:#8a5a00,color:#3d2a00
  class Prod planned
```

범례: 굵은 화살표가 기본 경로입니다. 파란 실선 상자는 현재 구현이고, 노란 점선 상자는 #139 목표이며 아직 live 검증되지 않았습니다. 각 그림의 근거 파일과 상세 그림은 [아키텍처 안내](docs/architecture/README.md)와 [그림 목록](docs/architecture/figures.md)에 있습니다.

## OnMaru-backend에 적용하는 CI는 검증·측정·개선을 분리합니다

일반 CI는 “테스트가 통과했는가”를 확인합니다. 이 Toolkit을 OnMaru-backend에 적용할 때의 목표 구조는 여기에 “얼마나 걸렸는가”, “무엇이 가장 오래 걸렸는가”, “변경 뒤에도 같은 조건에서 더 나아졌는가”를 추가합니다. 빠르게 끝난 한 번의 실행을 성과로 취급하지 않고, 같은 조건에서 반복한 결과를 기준선으로 남깁니다.

위 그림의 각 상자는 별도 기능을 뜻하지만, 실제로는 GitHub Actions workflow와 artifact를 통해 연결됩니다. OnMaru-backend는 실제 테스트를 실행하고, Toolkit은 어떤 모듈을 함께 실행할지 계산하고 증적을 읽기 쉬운 결과로 정리합니다. 서비스 운영 DB나 서비스 코드에 Toolkit을 설치하지 않아도 되는 이유가 여기에 있습니다.

현재 consumer에는 기존 serial `verify` CI와 기준선 수집 절차가 있고, module matrix를 기존 required check에 연결하는 fan-out/fan-in 전환은 별도 rollout으로 진행합니다. 따라서 이 README의 병렬 matrix 설명은 “이미 모든 PR에서 대체된 구조”라는 뜻이 아니라, 기존 검증을 유지하면서 단계적으로 붙이는 운영 모델입니다. 기준선이 먼저 필요한 이유도 이 때문입니다. 전환 전과 후의 실제 시간을 같은 방법으로 비교해야 개선 여부를 설명할 수 있습니다.

## 소비 방식은 다섯 가지를 구분합니다

| 방식 | 무엇인가 | 이 저장소에서의 상태 |
| --- | --- | --- |
| Reusable workflow | consumer가 `module-benchmark.yml@<SHA>`를 호출하는 CI 계약 | 현재 주 경로 |
| Source checkout | 같은 SHA의 Toolkit 저장소를 checkout해서 설치하거나 `PYTHONPATH=src`로 실행하는 방식. reusable workflow는 고정 checkout을 `pip install --no-deps`로 설치하고, 로컬 개발과 `scripts/`의 CLI 호출은 `PYTHONPATH=src`를 씁니다 | 현재 사용 |
| PyPI 패키지 | 배포된 패키지를 의존성으로 설치하는 방식 | 배포하지 않으며 사용하지 않습니다 |
| Marketplace action | Actions Marketplace에 게시한 action으로 쓰는 방식 | 게시하지 않으며 사용하지 않습니다 |
| 애플리케이션 런타임 의존성 | 서비스 코드가 Toolkit을 import하거나 설치하는 방식 | 금지된 사용입니다. 서비스 코드는 Toolkit에 의존하지 않습니다 |

## 세 가지 CI 관측은 질문과 산출물이 다릅니다

| 구분 | 답하는 질문 | 실행 시점 | 주요 산출물 |
| --- | --- | --- | --- |
| 일반 CI 관측 | 이 실행의 job과 step은 각각 얼마나 걸렸고 결과는 무엇인가 | 완료된 실행 뒤, 선택적으로 | 시간선 manifest, 진단 Markdown, 대시보드 |
| Module benchmark | 모듈을 병렬로 나눈 구성이 같은 조건에서 최장 모듈 시간을 줄였는가 | PR, develop, nightly의 module matrix | module 보고서, 최장 모듈 시간, 비교 ID |
| Release benchmark | 이전 release와 비교해 추세가 있는가 | release 후보와 이력이 쌓인 뒤 | release 추세 보고서. 조건이 다르면 `inconclusive` |

세 구분은 서로 판정 권한을 가지지 않습니다. 일반 CI 관측은 시간을 설명하고, module benchmark는 병렬화의 효과를 같은 조건에서 비교하며, release benchmark는 릴리스 전후의 추세를 보여 줍니다. 어느 것도 required check를 대체하지 않습니다.

## 두 저장소는 역할을 나누어 안전하게 협력합니다

Toolkit이 서비스 배포 권한이나 비밀값까지 가지면 재사용은 쉬워 보일 수 있지만, 한 저장소의 실수가 모든 consumer에 영향을 줄 수 있습니다. 반대로 Toolkit이 분석 규칙과 workflow 계약만 제공하고 consumer가 실제 명령과 권한을 소유하면, 새 모듈이 늘어나도 안전한 경계를 유지할 수 있습니다.

| 영역 | OnMaru-backend가 소유하는 것 | 이 Toolkit이 제공하는 것 |
| --- | --- | --- |
| 테스트 명령 | Gradle·pytest 명령, module catalog의 `test_command`, fixture | catalog 형식 검증, 변경 경로에 따른 실행 계획 |
| 자격 증명 | 토큰, 인증된 GitHub API callback, 관측 엔드포인트의 헤더 | 자격 증명을 다루지 않는 순수 계산과 HTTPS 전송 규칙 |
| CI 실행 | trigger, runner, cache, 병렬 한도 | reusable workflow와 fan-out/fan-in 구조 |
| 아티팩트 | 모듈 실행 결과와 보관 기간, 다운로드 권한 | 크기와 digest를 검사하는 bounded JSON 파싱. 압축 해제와 명령 실행 없음 |
| 스키마 | 생산자 쪽 필드 작성과 버전 관리 | `ci-performance-evidence/1.0`과 `normalized-execution/1` 검증, 구 형식의 legacy 읽기 |
| 비교 | 실험 계획과 선언된 허용 차이 | 비교 가능성 판정, 중앙값·범위, `inconclusive` 결론 |
| 관측 | Collector 설정, Grafana 권한, 보관 정책 | OTLP 변환, replay 억제, 로컬 스택과 대시보드 정의 |
| 배포와 승격 | 배포, promotion, protected environment 승인, rollback | 전후 증적과 설명 가능한 판정. 배포를 승인하거나 막지 않음 |

Toolkit은 consumer의 **런타임 의존성**이 아닙니다. Toolkit workflow는 consumer의 자격 증명이나 deployment credential을 요구하지 않으며, fork PR에는 secret을 전달하지 않습니다. consumer의 source, 원시 로그, 서비스 비밀값을 이 저장소에 커밋하지 않는 것도 같은 경계의 일부입니다. 신뢰 경계의 전체 설명은 [신뢰·fork·카디널리티·보관 경계](docs/architecture/boundaries.md)에 있습니다.

## 실패 원칙: export는 source CI 판정을 바꾸지 않습니다

source CI의 판정은 run과 job의 결론에서만 계산됩니다. 증적 품질이 완전하지 않으면 성공은 `unverified`가 되지만, 이 판정은 Toolkit이 바꾸지 않습니다. OTLP 전달 실패, 부분 거부, 시간 측정 불가, 비교 불가는 모두 CI 결론과 독립된 필드로 남습니다. 이 원칙과 각 상태의 차이는 [결과 상태 문서](docs/architecture/outcomes.md)에서 설명합니다.

## 변경 범위를 읽어 병렬 테스트를 구성합니다

OnMaru-backend는 consumer 저장소의 benchmark module catalog(.github/benchmark-modules.yml)에 모듈별 경로와 테스트 명령을 기록합니다. 예를 들어 catalog 모듈의 파일만 바뀌면 catalog와 그 결과에 의존하는 모듈을 우선 실행할 수 있습니다. 공통 Gradle 설정이나 workflow 파일이 바뀌었거나 어떤 모듈인지 판단할 수 없으면, 안전을 위해 전체 suite를 실행합니다.

Toolkit의 `module-plan`은 이 목록과 변경 경로를 읽어 실행 계획을 만들고, `module-benchmark.yml`은 계획을 matrix로 나눕니다. 서로 독립적인 모듈은 동시에 실행하고, resource-heavy 작업은 동시성 한도를 지켜 runner가 과부하되지 않게 합니다. 마지막 aggregate 단계는 각 결과를 한 곳에 모아 최장 module 명령 시간과 실패 상태를 기록하고, verify 단계는 branch protection이 읽을 수 있는 하나의 결론을 남깁니다. dependency graph를 확인하지 않은 workflow DAG critical path는 `unavailable`로 남깁니다.

실패한 테스트나 artifact 누락은 성능 저하라는 뜻이 아닙니다. 이런 경우 결과는 `failed` 또는 `inconclusive`로 남기며, 성능이 나빠졌다고 단정하지 않습니다. 이 구분이 없으면 테스트 인프라 문제를 코드 성능 문제로 잘못 해석할 수 있습니다.

## Consumer에서 module benchmark를 호출하는 방법

consumer repository에 module catalog와 caller workflow를 둡니다. 아래는 최소 호출 예시입니다. `<40-character-toolkit-commit-sha>`는 검증한 Toolkit commit SHA로 교체하며, branch나 mutable tag 대신 항상 40자리 immutable SHA를 사용합니다.

```yaml
jobs:
  module-benchmark:
    uses: YRootLab/OnMaru-backend-ci-toolkit/.github/workflows/module-benchmark.yml@<40-character-toolkit-commit-sha>
    with:
      catalog_path: .github/benchmark-modules.yml
      toolkit_ref: <40-character-toolkit-commit-sha>
      mode: pr
      max_parallel: 4
      baseline_ref: develop
      comment_mode: summary
```

`catalog_path`와 모든 `test_command`는 OnMaru-backend가 소유합니다. Toolkit은 caller runner에서 그 명령을 실행해 `module-benchmark-report` artifact와 result, comparison ID, `longest_module_duration_seconds`, `dag_critical_path_quality` output을 caller에 돌려줍니다. 기존 `critical_path_seconds`는 deprecated output으로 빈 값을 반환하므로, 숫자로 읽던 consumer는 [Actions evidence 계약](docs/telemetry/actions-timeline.md)과 [용어 migration](docs/architecture/migration.md)에 따라 전환해야 합니다. 모듈을 새로 추가할 때는 서비스에 Toolkit 코드를 import하는 대신 catalog에 한 항목을 추가하고 테스트 명령을 검증하면 됩니다. rollout 중에는 기존 `verify`를 required check로 유지하고, module benchmark의 artifact와 result가 충분히 쌓인 뒤 branch rule에 연결합니다.

## 기준선은 같은 출발선에서 반복해 만듭니다

병렬화 전후 시간을 비교하려면 실행 조건이 같아야 합니다. OnMaru-backend는 같은 commit과 설정에서 CI를 **세 번** 성공시킨 뒤, consumer collector로 `serial-baseline.json`을 만듭니다. 변경 후에도 같은 방법으로 세 번 수집하고 두 artifact를 비교합니다. 한 번의 실행은 GitHub-hosted runner의 대기, 다운로드 속도, cache 상태에 영향을 받을 수 있으므로 중앙값을 사용합니다.

비교 가능한 결과에는 아래 조건이 같아야 합니다.

- runner image와 아키텍처
- dependency mode와 cache 상태
- Java/Python 버전
- 실행한 suite·명령과 유효 표본 수

GitHub Actions API만으로 CPU·메모리 수치를 얻지 못하면 이를 추정하거나 `0으로 바꾸지 않는다`. 해당 수치는 수집 불가로 남기고 wall-clock 중앙값만 비교합니다. 이 원칙 덕분에 보고서가 실제로 측정하지 않은 자원 사용량을 사실처럼 보여 주지 않습니다.

OnMaru-backend의 collector와 전후 비교 명령은 [CI 기준선 수집과 비교](https://github.com/YRootLab/OnMaru-backend#ci-%EA%B8%B0%EC%A4%80%EC%84%A0-%EC%88%98%EC%A7%91%EA%B3%BC-%EB%B9%84%EA%B5%90)에서 확인할 수 있습니다. collector workflow와 artifact 보관 기간은 각 consumer repository가 관리하며, Toolkit은 evidence schema와 해석 원칙을 일관되게 적용합니다.

## Release에서는 이전 버전과의 추세를 확인합니다

PR은 빠른 피드백이 중요하므로 영향을 받은 모듈을 중심으로 실행합니다. `develop`과 nightly는 전체 suite의 증적을 쌓고, release는 충분한 반복 실행과 immutable evidence를 남깁니다. release manifest에는 tag뿐 아니라 commit SHA, image digest, configuration hash, runner profile, run ID를 남깁니다. 이전 버전이라도 조건이 다르면 Toolkit은 임의의 다른 기준선을 선택하지 않고 `inconclusive`를 반환합니다.

```bash
PYTHONPATH=src python -m pipeline_toolkit.cli trend compare \
  --history-root ./release-evidence \
  --candidate v1.3.0 \
  --baseline previous \
  --metric pipeline.wall_clock \
  --format markdown
```

이 비교 결과는 배포를 자동으로 승인하거나 막지 않습니다. consumer가 자신의 branch protection과 release 정책에 맞춰 결과를 사용합니다. 즉 CD는 OnMaru-backend가 빌드, 배포, health check, rollback과 protected environment 승인을 소유하고, Toolkit은 release 전후의 evidence와 설명 가능한 판정을 제공합니다. Toolkit의 역할은 재현 가능한 증적과 설명 가능한 판정을 만드는 데까지입니다.

## 상세 계약과 개발 검증을 확인할 수 있습니다

아키텍처 문서는 [docs/architecture/README.md](docs/architecture/README.md)에서 시작합니다. 맥락과 신뢰 경계, 호출 흐름, 증적 생성과 정규화, 비교 가능성, OTLP와 replay, Grafana 탐색, 용어 migration을 다룹니다.

필요할 때만 develop과 feature SHA를 각각 세 번 비교하는 CLI는 [Pipeline Benchmark Experiment 사용법과 소비자 계약](docs/benchmark-experiment.md)에 설명합니다. 기본 동작은 dry-run이고, 실제 dispatch는 OnMaruBE #555/#556 완료 후 통합 검증으로 제한합니다.

모듈별 병렬 실행의 입력·출력·안전 규칙은 [OnMaruBE parallel CI benchmark PRD](docs/prd/onmarube-parallel-ci-benchmark.md)에, release evidence의 보관·비교 규칙은 [release trend comparison PRD](docs/prd/release-trend-comparison.md)에 정리되어 있습니다. OnMaru-backend 담당자가 실제 rollout을 수행할 때는 [병렬 CI Toolkit rollout 구현 프롬프트](docs/to-be/onmaru-backend-parallel-ci-toolkit-rollout-prompt.md)를 사용합니다.

Cloud credential 없이 OTLP metric·trace와 Grafana datasource 연결을 확인하려면 [로컬 관측 스택 가이드](docs/telemetry/local-stack.md)를 사용합니다. 고정 버전 Compose, localhost 포트, bounded disposable storage와 fixture/query smoke 도구를 제공합니다.

[CI Grafana 대시보드](docs/telemetry/dashboard.md)는 workflow/job/module 시간, work·outcome·collection quality, Collector 전송 실패·queue 압력과 성공/실패 trace 탐색을 제공합니다. 실제 import/query·장애복구 smoke, 안전한 Actions·manifest 링크, pre-Collector Toolkit 가시성 경계와 telemetry 운영·비용 한도를 함께 설명합니다.

Toolkit 자체를 검증하려면 다음 명령을 실행합니다. 검증에는 pytest, 커버리지 기준, workflow 보안 규칙과 함께 문서 링크·경로·D2 SVG drift 검사(`scripts/check_pipeline_docs.py`)가 포함됩니다.

```bash
python -m pip install -e '.[test]'
bash scripts/verify_toolkit.sh
```
