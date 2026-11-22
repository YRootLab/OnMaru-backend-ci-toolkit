# partial, unavailable, inconclusive, failure의 구분

Toolkit의 결과는 여러 층에서 나오므로 "실패"라는 한 단어로 묶으면 원인을 잘못 읽게 된다. 이 문서는 자주 혼동되는 다섯 상태를 구분한다. 실행 결과(source verdict), 증적 품질(quality), 측정 가능성(unavailable), 비교 판정(inconclusive), 관측 전달 상태(export status)이다. 상태 이름은 각 계층의 계약에서 온다.

가장 먼저 구분할 것은 source verdict이다. 이것은 GitHub Actions의 run과 job 결론에서만 계산된다. 정규화 함수 `_source_verdict`는 run 결론이 `success`이고 시간선 품질이 `complete`이며 모든 job이 `success`일 때만 `success`를 반환한다. 결론은 `success`인데 품질이 완전하지 않으면 `unverified`가 된다. 즉 "실행은 성공처럼 보이지만 증명이 부족하다"는 상태를 따로 둔다. 다른 결론은 그대로 전달되며, `failed`, `cancelled`, `timed_out`은 관측 계층에서 각각 `failure`, `cancellation`, `timeout`으로 대응된다. 이 판정은 consumer의 required check가 내리는 판정과 같은 것이며, Toolkit이 바꾸지 않는다.

`partial`은 증적의 범위가 일부만 채워졌다는 뜻이다. 예를 들어 여섯 모듈 중 네 개의 execution artifact만 유효하면 artifact 품질은 `partial`이며, 빠진 모듈은 quality 이슈에 기록된다. 이때 남은 네 모듈의 시간은 보고할 수 있지만, 전체 suite 시간이라고 부를 수는 없다. `longest_module_duration_seconds`도 완전한 모듈 명령에서만 계산되고, 모듈 전체가 빠지면 unavailable이 된다.

`unavailable`은 측정 자체가 없다는 뜻이다. 0과 다르다. Gradle 시간이나 Context 생성 횟수가 envelope에 없으면 그 값은 `None`이며 대시보드에서는 빈 패널로 나온다. workflow wall-clock, runner queue, DAG critical path도 신뢰할 타임스탬프와 의존 그래프가 없으면 `unavailable`이다. aggregate job은 workflow 완료 시각을 관찰할 수 없으므로, 자기 자신의 렌더링 시각을 완료 시각으로 쓰지 않는다. 이 원칙이 있기 때문에 "빈 값은 없음, 0은 측정된 0"이라는 구분이 유지된다.

`inconclusive`는 비교 결론이다. 두 실행의 조건이 다르거나 표본이 부족하면 개선이나 회귀를 말하지 않고 이 상태를 낸다. 릴리스 비교에서 이전 버전의 조건이 다르면 Toolkit은 임의로 다른 기준선을 고르지 않고 `inconclusive`를 반환한다. 비교 엔진의 `incomparable`과 `insufficient-evidence`도 같은 범주에 속하며, 세부 기준은 [비교 가능성과 critical path](comparability.md)에 있다.

`failure`는 실행이나 입력이 성능이 아니라 정상 동작에서 실패했음을 뜻하는 말로만 써야 한다. 테스트 실패, artifact 누락, 파싱 오류는 같은 말이 아니다. 누락과 거부는 `missing`, `invalid`로 기록되고, 실패한 테스트는 실행 결과로 기록된다. 이 문서의 원칙은 README에도 있는 "실패한 테스트나 artifact 누락은 성능 저하가 아니다"라는 문장과 같다. 이를 구분하지 않으면 테스트 인프라 문제를 코드 성능 문제로 잘못 읽게 된다.

마지막은 export 상태이다. `exported`, `duplicate`, `busy`, `partial`, `failed`는 관측 데이터가 목적지에 도착했는지를 나타낸다. 이 상태는 CI 결론과 독립이다. `ExportResult`의 실패가 source verdict를 바꾸지 않으며, 성공도 실행이 성공했다는 증거가 아니다. consumer 코드는 export 결과를 검증 단계의 대체물로 쓰지 말아야 하며, 원래 결론과 export 결과를 별도 필드로 저장한다. OTLP 문서의 예시가 이 계약을 `assert delivery.ci_conclusion == evidence["run"]["conclusion"]`으로 확인한다.

이 원칙에 따라, export가 실패하면 consumer는 manifest와 digest, collection 시각, `ExportResult`, replay 저장소 상태를 보존한다. 그리고 CI 결론은 그대로 두고, 전달 문제를 별도 경고로 다룬다. 전달이 실패했다는 이유로 required check를 빨갛게 만들거나, 반대로 빈 관측을 green으로 표시하는 것은 둘 다 금지된다.
