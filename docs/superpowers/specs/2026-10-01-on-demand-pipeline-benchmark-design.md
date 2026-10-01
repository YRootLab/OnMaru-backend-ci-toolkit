# On-demand Pipeline Benchmark Experiment 설계

## 목표

일반 PR·push·CD마다 비용이 큰 3회 반복 benchmark를 실행하지 않는다. CI, test 또는 CD 파이프라인을 개선하는 개발자가 필요할 때만 OnMaruBE의 전용 workflow를 실행해 고정된 `develop` baseline과 feature candidate를 각각 3회 측정한다. Toolkit이 증적과 비교를 담당하고 Agent Toolkit skill이 안전한 CLI 실행 절차를 제공한다.

## 경계와 데이터 흐름

OnMaruBE는 source checkout, 테스트·배포 명령, GitHub token, workflow trigger와 관측 자격 증명을 소유한다. Pipeline Toolkit은 실행 계획, versioned manifest, 비교 가능성, 3회 비교와 보고 형식을 제공한다. Agent Toolkit은 사용자 머신에서 저장소 상태를 확인하고 Toolkit CLI와 `gh` CLI를 호출하지만 source, secret 또는 raw benchmark data를 저장하지 않는다.

`ci-benchmark-experiment` 실행은 현재 `feature/*` HEAD와 dispatch 시점의 remote `develop`을 각각 immutable SHA로 resolve한다. OnMaruBE의 `Pipeline Benchmark Experiment` workflow가 baseline과 candidate를 서로 다른 성공 실행 3회씩 수행한다. 결과 manifest를 Toolkit comparator가 읽고 개별 값, 중앙값, 범위, 실패율과 제외 사유를 보고한다. OpenTelemetry 후처리 경로는 같은 실행을 Prometheus 호환 metric과 CI trace로 보내며 Grafana는 탐색 화면만 제공한다.

## 실행 계약

스킬은 `gh` 인증, OnMaruBE remote, clean working tree, `feature/*` branch, remote `develop`, workflow 존재를 검사한다. dry-run은 기본이며 dispatch payload와 고정 SHA만 보여 준다. 사용자가 실제 실행을 명시하면 `candidate_ref`, `baseline_ref`, `scope`, `reason`을 전달하고 Actions run을 기다린다. 반복 횟수 3과 비교 threshold는 정책 버전에서 고정한다.

`scope=ci|test`를 v1에서 지원한다. `scope=cd` 계약은 포함하되 OnMaruBE #545의 격리된 staging이 검증되기 전에는 fail-closed로 거부한다. Fork, dirty tree, 움직이는 SHA, 누락된 artifact, 취소·실패 실행은 비교 결과를 만들지 않고 명시적인 사유와 복구 방법을 출력한다.

## 결과와 안전성

성공 결과는 baseline/candidate SHA, 3개 개별 표본, 중앙값, 범위, delta, verdict, Actions run, manifest와 Grafana 링크를 포함한다. 두 표본 이하, 조건 불일치 또는 일부 실패는 `inconclusive`다. 실험은 일반 PR required check와 자동 배포 gate가 아니며 사용자가 별도로 채택 결정을 내린다.

권한 있는 workflow는 PR head code나 artifact 명령을 실행하지 않는다. Grafana secret은 테스트 job, CLI와 skill에 전달하지 않는다. 관측 전송 실패가 benchmark 원본 verdict를 바꾸지 않으며 consumer-local manifest와 진단 artifact는 남는다.

## 검증

CLI fixture는 dry-run, dirty tree, 잘못된 branch, baseline 미존재, 동일 SHA, workflow 미존재, 2회 표본, 3회 성공, 실패·취소·누락, 중복 실행을 다룬다. Skill eval은 자연어 요청에서 불필요한 일반 PR benchmark를 거부하는지, 명시적 실험에서 dry-run을 먼저 제시하는지, 실제 실행 후 링크와 verdict를 빠짐없이 요약하는지 확인한다. 실제 GitHub dispatch는 별도 통합 검증 한 번으로 제한한다.
