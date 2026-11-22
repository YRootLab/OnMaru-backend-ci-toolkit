# 모듈 계획과 fail-closed 규칙

모듈 계획은 "이번 변경으로 어떤 모듈을 실행해야 하는가"를 결정한다. 이 결정은 빠른 피드백을 주지만, 잘못 줄이면 실제로 깨진 모듈을 건너뛰게 된다. 그래서 Toolkit의 계획기는 확신할 수 없을 때 항상 전체 suite로 되돌아간다. 구현은 [catalog/planner.py](../../src/pipeline_toolkit/catalog/planner.py)의 `plan_affected_modules`에 있다.

입력은 consumer가 소유한 module catalog와 변경된 파일 경로 목록이다. catalog에는 모듈의 ID, 경로 패턴, 의존 모듈, `test_command`와 자원 프로필이 들어 있다. 계획기는 catalog를 만들 때 ID의 유일성, 필수 필드, 존재하지 않는 의존 대상을 검사하고, 하나라도 어긋나면 계획을 만들지 않고 실패한다. 이 검사는 catalog 오류가 조용히 일부 모듈만 실행되는 상황을 막는다.

계획 규칙은 다음 순서로 적용된다. 변경 경로 목록이 비어 있거나 알 수 없으면 전체 실행이며 이유는 `unknown-diff`이다. 변경 경로 중 하나라도 `always_full_paths`에 매칭되면, 예를 들어 공통 Gradle 설정이나 workflow 파일이면 전체 실행이며 이유는 `always-full-path`이다. 어떤 모듈 경로에도 매칭되지 않으면 전체 실행이며 이유는 `unknown-path`이다. 이 세 경우가 모두 "모르면 전부 실행"이라는 fail-closed 원칙을 구현한다. 마지막으로 매칭된 모듈과 그 모듈에 의존하는 모듈을 역방향 의존 그래프에서 모두 포함한다.

결과 객체는 정렬된 모듈 목록, 전체 실행 여부, 그리고 그 이유를 담는다. 이 이유는 PR 요약과 증적에 남으므로, 실행된 모듈이 적었을 때 사람이 "왜 줄었는가"를 확인할 수 있다. 실행 matrix 자체는 reusable workflow의 detect job이 만들며, 이후 aggregate가 이 matrix를 기대 범위로 사용한다. 즉 계획이 줄여 놓은 범위를 검증 단계가 다시 확인하는 구조이다.

이 규칙이 보장하지 않는 것도 있다. catalog가 실제 테스트 구조를 빠짐없이 반영하지 않으면 계획기는 그 사실을 알 수 없다. 또한 계획은 실행 범위를 정할 뿐, 실행이 성공했다는 증명이 아니다. 실제 판정은 aggregate의 quality와 source verdict가 담당하며, 그 구분은 [outcomes.md](outcomes.md)에 있다.

이 규칙은 현재 구현이며 fixture 테스트로 검증된다. 대규모 OnMaru-backend 모듈 catalog의 정확성은 consumer의 #867 구현과 live 실행으로 따로 확인해야 하므로 이 문서에서는 계획 항목으로 남긴다.
