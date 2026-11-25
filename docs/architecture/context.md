# 맥락과 신뢰 경계

Toolkit은 OnMaru-backend의 CI 결과를 읽고 해석하는 저장소이며, 서비스 코드나 배포 경로에 들어가지 않는다. 이 문서는 Toolkit이 어떤 신뢰 영역에 놓이는지, 각 영역이 무엇을 볼 수 있고 무엇을 할 수 없는지 정리한다. 시스템 맥락 그림은 [system-context](../diagrams/system-context.svg)에 있고, 그림의 범례와 근거는 [그림 목록](figures.md)에 있다.

세 개의 신뢰 영역이 있다. 첫 번째는 consumer 영역으로, OnMaru-backend 저장소와 그 runner, secret, 테스트 명령이 여기에 속한다. 테스트를 실제로 실행하고 어떤 cache와 자격 증명을 쓸지 결정하는 곳이 이곳이므로, 실패의 원인과 권한은 여기서 나온다. 두 번째는 Toolkit 영역이다. Toolkit은 고정된 commit SHA로 checkout되어 consumer가 올린 artifact를 데이터로만 읽는다. 이 영역에는 secret이 전달되지 않고, artifact의 명령이나 경로를 실행하지 않는다. 세 번째는 관측 영역으로 OpenTelemetry Collector, Mimir 호환 metric 저장소, Tempo, Grafana가 속한다. 이 영역은 이미 계산된 관측값을 보여 줄 뿐, CI의 성공이나 실패를 바꾸지 않는다.

신뢰 영역 사이의 연결은 모두 단방향 데이터 흐름이다. consumer의 reusable workflow가 artifact를 업로드하면 Toolkit이 그 bytes를 검증하고 manifest를 만든다. 그 manifest가 OTLP로 내보내지면 관측 영역이 받는다. 관측 영역에서 consumer 쪽으로 명령을 되돌려 보내는 경로는 없다. Grafana 패널의 링크는 사용자의 브라우저에서 열릴 뿐, Grafana가 GitHub API를 호출하지 않는다.

Toolkit이 소유하지 않는 것도 분명하다. 테스트 명령과 module catalog의 `test_command`는 consumer가 소유한다. 자격 증명, 배포 권한, branch protection, 보관 정책과 Cloud tenant 설정도 consumer나 운영자의 몫이다. Toolkit은 이 경계 안에서 데이터의 정확성과 설명 가능한 판정만 제공한다. 이 구분은 [README의 소유 표](../../README.md)와 같은 내용이며, 더 자세한 신뢰 조건은 [신뢰·fork·카디널리티·보관 경계](boundaries.md)에서 다룬다.

현재 구현과 계획을 구분하면 다음과 같다. 현재 저장소에는 입력 검증, 정규화, 비교, 변환, OTLP 전달, 로컬 관측 스택, 대시보드, 그리고 `module-benchmark.yml` reusable workflow가 있다. 계획 항목은 Backend #867 collector가 `ci-performance-evidence/1.0`을 실제로 만드는 일, consumer post-run 단계가 이를 연결하는 일, 그리고 Grafana Cloud tenant에 전달하고 보관 기간을 확인하는 일이다. 계획 항목은 실제 live 증적이 없으므로 이 저장소의 fixture 검증으로 대신할 수 없다.
