# 신뢰·fork·카디널리티·보관 경계

이 문서는 Toolkit이 지키는 네 가지 경계를 한곳에 모은다. 자격 증명, 외부 PR, 라벨 카디널리티, 보관 기간이다. 각 경계는 설계 문서와 코드에서 확인할 수 있으며, 실행 중 위반되면 조용히 넘어가지 않고 명시적인 거부나 quality 이슈로 드러난다.

자격 증명은 consumer가 소유한다. Toolkit 라이브러리는 인증 헤더를 만들지 않으며, GitHub API 호출은 consumer가 넘기는 callback이 맡는다. 외부 전송에 쓰이는 인증 헤더도 consumer가 공급하며, 표현이나 checkpoint에는 저장되지 않는다. OTLP 전송은 HTTPS를 요구하고 `localhost`, `127.0.0.1`, `::1`만 예외이다. URL에 자격 증명이나 query, fragment가 있으면 거부하며, 리다이렉트를 따르지 않고 환경 프록시 설정도 쓰지 않는다. 이 규칙은 [telemetry/export.py](../../src/pipeline_toolkit/telemetry/export.py)에 있다.

fork에서 온 PR은 신뢰하지 않는다. reusable workflow는 consumer의 테스트 명령을 secret 없이 실행하며, Toolkit checkout은 `persist-credentials: false`로 가져온다. 이는 README가 밝힌 계약이다. 따라서 외부 PR의 코드가 Toolkit이나 관측 자격 증명에 접근하지 못한다. 외부 PR의 artifact는 데이터로만 읽히며, 그 안의 명령이나 경로를 실행하지 않는다. consumer 원시 로그와 서비스 비밀값은 이 저장소에 커밋하지 않는다.

카디널리티는 metric 라벨로 제한된다. CI metric의 라벨은 `workflow`, `environment`, `ci_job`, `module`, `scope`, `outcome`, `quality`처럼 유한한 집합뿐이다. SHA, PR 번호, run URL, 테스트 클래스, step 이름, 저장소 이름, digest는 metric 라벨이 되지 않고 trace 속성에만 들어간다. 카탈로그에 없는 job이나 모듈은 `other`로 묶인다. Prometheus가 대상 식별에 쓰는 `job`과 `instance`는 CI job 라벨로 쓰지 않으며, `le`, `quantile`, `__*` 같은 예약 이름도 거부된다. 이 원칙은 실제 통합에서 `job` 라벨이 Collector의 상수 라벨과 충돌해 metric이 사라진 사건을 계기로 생겼다.

카디널리티 예산도 설계의 일부다. 운영 기준은 workflow와 environment별 활성 series 2,000개이며, 1,600개에서 경고한다. 16개 job과 모듈과 `other`로 이루어진 카탈로그는 보수적 상한이 1,682개이다. 생산자 상한인 256개 항목은 이 예산을 넘어서므로, 카탈로그는 운영 예산 안에서 설계해야 한다. 이 수치는 rollout 허용 조건이며, 대시보드가 강제하는 할당량이 아니다. 초과를 막는 것은 consumer 소유 설정이다.

보관 기간도 경계로 관리된다. 초기 Cloud 목표는 metric 30일, trace 7일 이하이며, 실제 tenant 기본값과 요금제 한도는 확인해야 한다. 이 저장소는 Cloud 보관 기간을 provisioning하지 않는다. 대신 manifest는 감사와 replay 기간 동안 독립적으로 보관되어야 한다. replay 저장소는 기본 10만 identity까지 기록하고 자동으로 제거하지 않으며, 확인된 항목을 지우면 중복 전송이 다시 가능해지므로 검토 없이 지우지 않는다.

이 네 경계는 "데이터가 없음"을 "정상"으로 바꾸지 않도록 서로 맞물린다. 예를 들어 라벨을 줄이려고 SHA를 빼면 추적은 manifest와 trace 속성으로 해야 하고, 보관 기간이 지나면 원본 증적이 사라질 수 있다. 그 공백은 대시보드의 빈 패널로 드러나며, Toolkit은 그것을 0으로 채우지 않는다.

이 경계 중 현재 저장소에서 검증된 것은 라벨 검사, 금지된 이름, digest 검사, 전송 제한, 그리고 fork 금지 workflow 계약이다. Cloud 보관, tenant 한도, 실제 fork PR의 secret 차단은 live 실행으로 따로 확인해야 하며 계획 항목이다.
