# PR에서 Grafana까지의 호출 흐름

한 PR이 Grafana 패널이 되기까지는 네 단계를 거친다. 먼저 consumer CI가 변경을 계획하고 모듈 테스트를 실행한다. 다음으로 각 모듈이 증적 artifact를 남기고, 마지막 fan-in 단계가 모든 결과를 모은다. 그 뒤 완료된 실행을 Toolkit이 정규화하고, 선택적인 post-run 단계가 OTLP로 내보낸다. 순서 그림은 [pr-sequence](../diagrams/pr-sequence.svg)에 있다.

개발자가 PR을 열면 GitHub가 `pull_request` 이벤트를 consumer의 caller workflow에 전달한다. caller는 `module-benchmark.yml`을 40자리 commit SHA로 호출한다. 이 호출이 reusable workflow의 첫 job인 detect를 시작하고, detect는 consumer 저장소를 checkout한 뒤 Toolkit을 `toolkit_ref`와 같은 SHA로 checkout해 `pip install --no-deps`로 설치한다. 이 설치는 PyPI 패키지가 아니라 고정된 checkout에서 이루어지므로, 실행되는 Toolkit 코드는 caller가 지정한 commit과 일치한다. 이후 `module-plan`이 변경 경로와 모듈 catalog를 읽어 실행할 모듈 목록을 만들며, 그 규칙은 [모듈 계획과 fail-closed 규칙](module-plan.md)에 있다.

모듈 job은 matrix로 실행된다. 각 job은 consumer가 소유한 `test_command`를 secret 없이 실행하고, 결과를 `module-evidence-<id>` artifact로 올린다. 이 artifact에는 실행 번호, attempt, Toolkit SHA, 모듈 ID, 종료 코드와 소요 시간이 담긴다. 실험 목적으로 Backend collector가 Gradle, Spring Context, Testcontainers 시간을 남기는 경로는 현재 계획 단계이며, 이 저장소에는 그 producer가 없다. 따라서 이 흐름의 점선 화살표는 #139 목표이다.

aggregate 단계는 detect가 만든 실행 matrix를 기대 범위로 삼아 artifact를 모은다. 기대한 모듈이 빠지거나, attempt나 SHA가 맞지 않거나, 중복된 항목이 있으면 그 사실을 quality 이슈로 남긴다. 최장 모듈 시간은 완전한 모듈 명령에서만 계산하며, 빠진 모듈을 0으로 채우지 않는다. DAG critical path는 `unavailable`로 남는다. 이 단계의 출력인 `longest_module_duration_seconds`와 `dag_critical_path_quality`가 caller에게 돌아간다. 기존 `critical_path_seconds`는 빈 값을 반환하는 deprecated 출력이다.

완료된 실행은 consumer의 post-run 단계에서 `collect_attempt_jobs`로 jobs API를 페이지 단위로 읽고, `normalize_actions_timeline`과 정규화 manifest로 바뀐다. 그 manifest는 consumer가 보관하는 저장소에 남으며, 이후 OTLP 변환과 전달은 manifest를 근거로 실행된다. 전달이 실패해도 원래 CI 결론은 바뀌지 않는다. 이 원칙은 [partial, unavailable, inconclusive, failure의 구분](outcomes.md)에서 자세히 다룬다.

Collector는 metric과 trace를 받아 Mimir 호환 저장소와 Tempo로 나눠 보낸다. Grafana는 PromQL로 metric을 조회하고 TraceQL로 trace를 찾으며, 그 결과에 붙은 링크로 Tempo trace와 Actions 실행 페이지에 이동한다. 이 탐색 경로는 [Grafana에서 Tempo, Actions까지의 탐색](drilldown.md)에서 설명한다.

현재 로컬 스택에서 확인된 것은 synthetic success와 failure manifest가 Collector를 거쳐 Prometheus와 Tempo에서 조회되는 흐름이다. 실제 Backend 실행과 Grafana Cloud 전달은 아직 live 검증되지 않았다.
