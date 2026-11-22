# OTLP, replay와 중복 억제

관측 경로는 manifest를 받아 metric과 trace로 바꾸고, 그것을 Collector로 보내는 일을 맡는다. 이 경로의 핵심 약속은 두 가지이다. 같은 manifest는 같은 정체성을 가져서 재전송해도 같은 payload가 나와야 하고, 전달 결과는 원래 CI 결론을 바꾸지 않아야 한다. 이 문서는 [telemetry/export.py](../../src/pipeline_toolkit/telemetry/export.py)와 변환 모듈이 이 약속을 어떻게 구현하는지 설명한다. 생명주기 그림은 [failure-replay](../diagrams/failure-replay.svg)에 있다.

변환은 두 종류이다. 첫째는 `transform_actions_evidence`로, 정규화된 workflow, job, step, module 관측을 `toolkit_ci_*` 계열 metric과 workflow 및 job 계층 span으로 바꾼다. 둘째는 `transform_layer_evidence`로, `normalized-execution/1` manifest와 digest가 맞는 성능 envelope을 받아 `onmaru_ci_*` 계열 metric과 context·container·Flyway 구간을 만든다. 두 변환은 metric 이름 접두사가 다르며, 대시보드의 질의는 이 이름을 그대로 쓴다.

정체성은 manifest의 digest에서 온다. 전송 식별자는 repository, run ID, attempt, manifest digest의 SHA-256이며, trace ID와 span ID는 이 정체성과 workflow·job·step 키에서 결정적으로 유도된다. 재실행이나 정정된 manifest는 digest가 달라지므로 다른 정체성을 얻는다. 같은 manifest의 재시도는 trace ID와 span ID가 같고 본문도 바이트 단위로 같아야 한다. 이 불변식은 이후 replay가 같은 batch를 인식하는 근거이다.

replay 저장소는 consumer가 소유한 `SQLiteReplayStore`이다. 저장소는 목적지와 정체성마다 해시, payload plan digest, lease 소유권, batch별 acknowledgement 상태를 기록한다. 원본 JSON, URL, 자격 증명은 저장하지 않는다. 같은 DB를 공유하는 동시 실행은 `busy`를 받는다. 중간에 죽은 프로세스의 lease는 설정된 export 예산과 5초가 지나야 회수된다. 이미 acknowledgement를 받은 batch는 이후에도 억제된다.

결과 상태는 `exported`, `duplicate`, `busy`, `partial`, `failed` 다섯 가지이다. `duplicate`는 모든 batch가 이미 확인되었다는 뜻이고, `partial`은 어떤 batch가 수신자에 의해 부분 거부되어 terminal 상태가 되었다는 뜻이다. 부분 거부된 batch는 다시 보내지 않는다. 다시 보내면 이미 받아들여진 일부가 중복 집계될 수 있기 때문이다. 재시도는 연결 실패와 HTTP 429, 502, 503, 504에만 적용되며, 다른 HTTP 오류나 잘못된 acknowledgement는 재시도하지 않는다.

이 억제는 정확히 한 번 전달을 보장하지 않는다. 수신자가 요청을 받아들였는데 응답이 유실되면 재시도가 중복을 만들 수 있다. 서로 다른 저장소는 서로를 조정하지 않는다. 따라서 중복 여부의 최종 기준은 원본 manifest와 그 digest이다. downstream의 보관 정책과 histogram 집계 의미도 같이 고려해야 한다.

Mimir와 Tempo는 같은 실행을 서로 다른 이름으로 가리키지 않아야 한다. metric에는 SHA, run URL, run ID, 테스트 이름을 라벨로 넣지 않는다. 대신 Grafana 패널은 Tempo의 trace 속성 `cicd.pipeline.run.id`, `toolkit.ci.run.attempt`, `toolkit.ci.manifest.digest`로 원본 실행을 찾는다. metric 쪽의 `ci_job`과 `workflow`, `environment` 라벨은 카탈로그 값으로만 제한된다. 즉 두 저장소의 연결 고리는 metric 라벨이 아니라 manifest digest와 시간 창이다. 이 연결의 상세 탐색은 [drilldown.md](drilldown.md)에서 설명한다.

라벨이나 대상 설정을 바꾸면 기존 replay 계획과 달라지므로 `replay_plan_mismatch`가 된다. 이 실패는 조용히 새 batch를 보내지 않는다. 운영자가 새 run이나 attempt로 검증하거나, 검토된 replay 상태 migration을 수행해야 한다.

현재 구현은 로컬 Collector와 Prometheus, Tempo, Grafana 스택에서 synthetic manifest로 검증되었다. 실제 Grafana Cloud에 대한 OTLP 전달, Cloud 보관 기간, 그리고 consumer 쪽 post-run 워크플로 연결은 아직 live 검증되지 않았으며, 그 상태는 계획 항목으로 남는다.
