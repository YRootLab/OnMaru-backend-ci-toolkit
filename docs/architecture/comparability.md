# 비교 가능성과 critical path

두 실행의 숫자를 나란히 놓는다고 개선을 말할 수 있는 것은 아니다. 같은 조건에서 반복했는지, 허용된 차이만 있었는지, 표본이 충분한지가 먼저 확인되어야 한다. 이 문서는 [compare/performance.py](../../src/pipeline_toolkit/compare/performance.py)의 비교 엔진이 이 질문을 어떤 순서로 다루는지, 그리고 critical path를 왜 `unavailable`로 남기는지 설명한다. 엔진의 정책 버전은 `performance-compare/1`이다.

엔진은 결과를 세 가지로만 낸다. `incomparable`은 선언되지 않은 차이가 있다는 뜻이다. 프로필, namespace, 입력 digest, layer 상태, toolchain, writer, restore 정책, 선택된 계획 중 하나라도 선언과 다르면 이 상태가 되고, 그 이유 목록을 보여 주며 개선량을 계산하지 않는다. `insufficient-evidence`는 비교 자체는 가능하지만 한쪽 표본이 너무 적어 중앙값과 범위가 의미를 갖지 못하는 상태이다. 최소 기술 표본은 3개이다. `comparable`은 그제서야 중앙값, 범위와 쌍을 이룬 차이를 보고한다.

허용되는 차이는 코드에 명시되어 있다. `ALLOWED_VARIABLES`는 `affected_selection`과 `cache_enablement` 두 가지뿐이다. 즉 affected 선택 여부나 cache 활성화만 baseline과 candidate 사이에서 달라질 수 있고, 그 밖의 차이는 모두 불일치로 취급된다. 예를 들어 같은 소스와 같은 테스트 universe를 유지한 채 cache를 켜는 실험은 비교 가능하다. 반대로 소스 digest가 다르면 cache 효과와 코드 변화가 섞이므로 비교하지 않는다.

실험은 사전에 계획을 선언한다. 계획 종류는 `AB-BA`와 `AB`이며 side당 3회에서 5회까지 실행한다. controlled-cold, controlled-warm, realistic-pr 세 프로필은 서로 합쳐지지 않는다. fresh runner와 cold cache는 같은 상태가 아니므로 구분해서 기록한다. seed 실행은 warm 표본에서 제외되고, seed provenance가 불명이면 역시 제외된다.

p95는 초기 정책으로만 제공된다. 같은 cohort에서 14일 동안 유효 실행이 100건 이상 쌓일 때만 p95 추정치를 보고하며, 그 전에는 `insufficient-samples`로 남긴다. 이 숫자는 운영 정책이지 통계적 보장이 아니다. histogram에서 나온 추정치는 원시 분위수와 구분해서 표시한다.

critical path도 같은 원칙을 따른다. 모듈별 duration이나 Gradle task 시간을 모아 전체 configuration 시간이라고 부르지 않는다. 시간들은 서로 중첩될 수 있고, 어느 것이 어느 것을 기다렸는지 알려 주는 인과 그래프가 없기 때문이다. 그래서 normalize 단계는 개별 구간을 하한으로만 보고하고, 합계를 만들지 않으며, critical path 품질을 `unavailable`로 둔다. 이 값은 실행 시간과 다르게 해석되어야 하며, 시간 절약 추정치는 검증된 대응 표본이 있을 때만 계산한다.

예산 판단도 있다. collector를 켰을 때의 추가 비용은 consumer workflow 중앙값의 3%와 15초 중 작은 값으로 제한된다. 이 비용은 wall-clock뿐 아니라 runner-minutes, 동시성, cache와 artifact 바이트를 함께 본다. 이 예산은 엔진의 상수로 구현되어 있고, 실제 consumer 측정은 계획 항목이다.

결과 해석에서 조심할 점은, `comparable`이 "개선되었다"는 판정이 아니라는 것이다. 엔진은 설명 가능한 중앙값과 쌍 차이를 주고, 회귀 임계값과 릴리스 정책은 consumer가 정한다. 비교가 `incomparable`이나 `insufficient-evidence`일 때 가장 나쁜 실수는 빈 결과를 0이나 개선으로 바꾸는 것이다. 이 엔진은 그런 변환을 하지 않는다.
