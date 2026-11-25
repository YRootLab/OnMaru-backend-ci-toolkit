# 증적 생성·검증·정규화

증적은 세 종류가 있다. 첫째는 GitHub Actions가 제공하는 run과 job, step의 시간선이다. 둘째는 모듈이 남기는 `execution.json`이다. 셋째는 `ci-performance-evidence/1.0` envelope으로, Gradle task, Spring Context, Testcontainers 같은 세부 시간과 cache 상태를 담는 계약이다. 이 문서는 세 증적이 어떤 경계를 통과해 하나의 `normalized-execution/1` manifest가 되는지 설명한다. 흐름은 [data-lineage](../diagrams/data-lineage.svg) 그림과 같다.

시간선 수집은 consumer가 제공하는 인증된 callback을 통해 이루어진다. Toolkit은 자격 증명을 다루지 않고, `collect_attempt_jobs`가 `/repos/{owner}/{repo}/actions/runs/{id}/attempts/{attempt}/jobs`를 `per_page=100`으로 읽는다. 페이지가 비어 있거나 전체 개수가 바뀌거나 중복 ID가 나오면 증적을 완전하다고 보지 않고 실패로 처리한다. 전송 예외는 삼키지 않고 위로 전파하므로, 권한 오류나 rate limit이 "빈 실행 성공"으로 보이지 않는다. 이 함수의 계약은 [github/responses.py](../../src/pipeline_toolkit/github/responses.py)에 있다.

정규화 단계인 `normalize_actions_timeline`은 job을 ID 순으로, step을 번호 순으로 정렬하고 중복을 거부한다. 타임스탬프가 역전되었거나 시간대가 없거나 형식이 틀리면 duration 품질을 `invalid`로 표시하고, 값이 아예 없으면 `unavailable`로 표시한다. 0으로 바꾸거나 다른 값으로 추정하지 않는다. API 입력은 job 256개, job당 step 256개, 텍스트 4,096자로 제한된다. 이 정규화는 [telemetry/timeline.py](../../src/pipeline_toolkit/telemetry/timeline.py)에 구현되어 있다.

모듈 artifact는 더 엄격하게 검증된다. 각 JSON 파일은 1 MiB 이하, 전체 16 MiB 이하, artifact 256개 이하여야 한다. 중복 JSON 키, 잘못된 UTF-8이나 JSON, 지원하지 않는 schema 버전, run·attempt·Toolkit ref 불일치, 1년을 넘는 duration, 음수나 `NaN`은 격리된다. 알 수 없는 필드(예: `command`)는 버린다. 같은 모듈 ID가 두 번 나오면 도착 순서로 고르지 않고 모호한 후보를 모두 제외한다. Toolkit은 archive를 풀지 않고, artifact 안의 경로나 명령을 해석하거나 실행하지 않는다.

성능 envelope `ci-performance-evidence/1.0`은 별도의 namespace이며 기존 module evidence와 섞이지 않는다. 파서는 알 수 없는 키, 중복 키, 64 KiB를 넘는 payload를 거부하고, 측정되지 않은 값은 `None`으로 둔다. layer 상태는 `dependency`, `build`, `configuration` 세 층에 대해 `disabled`, `cold`, `warm`, `partial`, `invalidated`, `unknown` 중 하나만 허용한다. 측정되지 않은 값을 0으로 채우는 경로는 없으며, 이 원칙은 [비교 가능성과 critical path](comparability.md)에서 다시 쓰인다.

envelope은 실행 identity와 맞을 때만 manifest에 붙는다. 저장소, run ID, attempt, commit SHA가 모두 시간선과 같아야 하며, 하나라도 다르면 해당 artifact만 거부하고 Actions 증적은 그대로 남긴다. 이때 envelope의 실패가 원래 실행의 판정을 바꾸지 않는다는 점이 중요하다. 원래 판정은 run과 job의 결론에서만 계산되며, 시간선 품질이 완전하지 않으면 `success`가 `unverified`로 낮아진다. 판정 규칙은 [normalize/performance.py](../../src/pipeline_toolkit/normalize/performance.py)의 `_source_verdict`에 있다.

이 저장소에서 envelope의 예시는 fixture로 검증된다. `schemas/ci-performance-evidence-1.0.json`과 `tests/fixtures/performance-evidence/`가 그 계약이다. 반면 Backend #867이 실제로 이 envelope을 만드는 일은 #139 계획에 속하며, 이 저장소의 테스트가 live 생성을 증명하지는 않는다. 과거 `cache_state` 문자열을 담은 legacy 기록은 `legacy-limited` 품질로만 읽히며, 레이어별 cache 상태를 추론하지 않는다. 자세한 변환 규칙은 [용어 migration](migration.md)에 있다.
