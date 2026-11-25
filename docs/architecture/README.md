# 아키텍처 문서 안내

이 디렉터리는 OnMaru Backend Pipeline Toolkit의 현재 구현을 설명한다. 각 문서는 설명하는 코드와 계약의 파일 경로를 링크로 남긴다. 현재 구현과 #139 목표(Backend #867 producer, Grafana Cloud 전달 등)는 구분해서 적으며, 목표 항목은 "계획"이라고 표시한다. 그림의 범례와 근거는 [그림 목록](figures.md)에 있다.

처음 읽는다면 [맥락과 신뢰 경계](context.md)에서 Toolkit이 어디에 놓이고 누가 무엇을 소유하는지 확인한 뒤, [PR에서 Grafana까지의 호출 흐름](call-flow.md)으로 실행 순서를 따라가면 된다. 나머지 문서는 특정 질문에 답하는 참조 문서다.

| 문서 | 답하는 질문 |
| --- | --- |
| [맥락과 신뢰 경계](context.md) | Toolkit은 어떤 저장소·권한·데이터 경계에 있는가? |
| [PR에서 Grafana까지의 호출 흐름](call-flow.md) | 한 PR이 어떤 순서로 증적과 관측 데이터가 되는가? |
| [모듈 계획과 fail-closed 규칙](module-plan.md) | 변경 경로를 알 수 없을 때 무엇을 실행하는가? |
| [증적 생성·검증·정규화](evidence.md) | 원시 artifact는 어떤 조건을 통과해야 manifest가 되는가? |
| [비교 가능성과 critical path](comparability.md) | 두 실험은 언제 비교할 수 있고, 숫자는 어떤 의미인가? |
| [OTLP, replay와 중복 억제](telemetry-replay.md) | 같은 manifest를 다시 보내면 무엇이 일어나고, Mimir와 Tempo는 어떻게 같은 실행을 가리키는가? |
| [Grafana에서 Tempo, Actions까지의 탐색](drilldown.md) | 대시보드의 값에서 원본 실행과 증적으로 어떻게 내려가는가? |
| [신뢰·fork·카디널리티·보관 경계](boundaries.md) | 자격 증명, 외부 PR, 라벨 수, 보관 기간은 어떻게 제한하는가? |
| [partial, unavailable, inconclusive, failure의 구분](outcomes.md) | 결과 상태가 서로 다를 때 어떻게 읽어야 하는가? |
| [그림 목록](figures.md) | 각 그림의 캡션, 대체 텍스트, 범례, 근거 파일은 무엇인가? |
| [용어 migration](migration.md) | 예전 이름(Java lane, cache_state 문자열 등)은 무엇으로 바뀌었는가? |

설계 결정의 원문은 [ADR 목록](../decisions/README.md)에 있으며, 과거 보고서와 PRD의 수치와 식별자는 그대로 보존된다. 아키텍처 문서에서 과거 이름이 필요할 때만 [용어 migration](migration.md)을 참조한다.
