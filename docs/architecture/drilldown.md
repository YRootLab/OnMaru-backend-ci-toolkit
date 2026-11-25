# Grafana에서 Tempo, Actions까지의 탐색

대시보드는 집계된 값을 보여 주지만, 그 값이 어떤 실행에서 왔는지 확인하려면 trace와 원본 증적으로 내려가야 한다. 이 문서는 Grafana 패널에서 Tempo trace, GitHub Actions 실행, 보관된 manifest artifact까지 이동하는 경로를 설명한다. 구현 설정은 [observability/dashboards/ci-performance.json](../../observability/dashboards/ci-performance.json)과 [observability/dashboards/ci-benchmark.json](../../observability/dashboards/ci-benchmark.json)에 있으며, 운영 설명은 [CI 관측 대시보드 가이드](../telemetry/dashboard.md)에 있다.

탐색의 출발점은 metric 패널이다. 예를 들어 job 시간 histogram은 `ci_job`과 `workflow`, `environment`로 묶인다. 패널은 집계된 histogram의 sum과 count로 평균을 보여 줄 뿐, 개별 실행을 가리키지 않는다. 개별 실행으로 가려면 같은 시간 창의 Tempo 표로 이동한다. 이 표는 TraceQL로 성공과 그 밖의 결과를 나눠 보여 주고, 각 행에 run ID, attempt, manifest digest, 결과가 담긴다. 실패뿐 아니라 취소, 건너뜀, 알 수 없는 결과도 빠지지 않도록 질의가 설계되어 있다. ERROR 상태만으로는 취소가 보이지 않기 때문이다.

Tempo 표의 각 행에서 세 가지 링크가 나온다. 첫째 **Tempo trace**는 그 trace를 Tempo에서 연다. 둘째 **Actions run**은 원본 GitHub Actions 실행 페이지를 연다. 이 링크는 repository와 숫자 run ID로만 만들어지며, trace 속성에 담긴 임의 URL을 그대로 보간하지 않는다. 셋째 **Manifest artifacts**는 실행 페이지의 `#artifacts` 섹션을 연다. 사용자는 거기서 보관된 증적을 내려받고, manifest의 `toolkit.ci.manifest.digest`와 attempt가 같은지 확인한다.

세 번째 링크가 특히 조심스러운 이유가 있다. OTLP v1은 manifest의 digest를 제공하지만, 검증된 artifact ID는 제공하지 않는다. artifact ID를 추측해서 정확한 다운로드 URL을 만들면 잘못된 파일로 연결될 위험이 있다. 그래서 링크는 실행 페이지의 artifact 섹션까지만 간다. 보관 기간이 지나 artifact가 사라졌다면 manifest 자체를 consumer 저장소에 남겨 두어야 한다는 것이 운영 원칙이다.

trace에서 Actions로 내려가는 방향은 실행 정체성을 확인하는 용도이다. 같은 run ID와 attempt를 가리키는지, Toolkit ref가 맞는지, digest가 같은지를 보면 된다. 이 세 값이 맞지 않으면 그 trace는 다른 실행의 것이거나 정정된 manifest에서 나온 것이므로 같은 실행으로 해석하지 않는다.

계층 시간을 탐색할 때는 waterfall을 쓴다. Context 생성, container 준비, Flyway 구간은 `tests` span 안에 놓이며, 그 위치는 causal graph가 없어서 검증되지 않았음을 `toolkit.ci.timing` 속성이 알려 준다. 중첩 구간을 합쳐서 테스트 시간과 다시 더하지 않는다. 이 원칙은 [비교 가능성과 critical path](comparability.md)와 같다.

이 탐색 경로는 로컬 스택에서 Grafana provisioning과 query API, 링크 필드를 통해 검증되었다. 스크린샷 자동화는 사용할 수 없었으므로 시각적 레이아웃은 별도 확인 대상이다. 실제 Actions artifact 보관과 접근 권한은 consumer의 실행으로만 증명되며, 이 저장소에서는 계획 항목으로 남긴다.
