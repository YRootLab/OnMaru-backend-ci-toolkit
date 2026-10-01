# 필요할 때 실행하는 Pipeline Benchmark Experiment

Toolkit #122는 OnMaruBE의 CI 또는 test 파이프라인 변경을 고정된 `develop`과 커밋된 `feature/*` HEAD로 비교하는 CLI 계약을 제공한다. 일반 PR·push와 배포에는 반복 benchmark를 추가하지 않는다. Python 3.9 이상에서 동작하며 `git`, 인증된 `gh`가 필요하다.

## 현재 통합 상태

로컬 계약은 fake `gh` subprocess와 comparator로 검증한다. 실제 통합은 [OnMaruBE #555](https://github.com/YRootLab/OnMaru-backend/issues/555)의 관측 검증과 [#556](https://github.com/YRootLab/OnMaru-backend/issues/556)의 소비자 workflow가 완료된 뒤 별도 명시적 dispatch 한 번으로 검증해야 한다. CLI는 두 Issue가 모두 `closed`인 경우에만 POST를 허용한다. Issue 종료는 구현과 운영 검증을 대체하지 않으며, #556은 아래 artifact·run-name 계약까지 구현해야 한다. 이 기능의 개발·테스트에서는 실제 Actions dispatch를 실행하지 않았다.

## 실행

OnMaruBE의 깨끗한 `feature/*` 브랜치에서 후보 커밋을 `origin`에 push한 뒤 실행한다. `origin`은 정확히 `YRootLab/OnMaru-backend`여야 하며 fork를 허용하지 않는다. 인증된 GitHub API의 저장소 신원, remote `develop` 및 feature 브랜치를 확인하고 HEAD와 remote 후보 SHA가 같은지 검사한다. 기준선이 없거나 두 SHA가 같으면 중단한다. 전용 workflow는 active 상태이고 고정 baseline 커밋에 네 입력이 있어야 한다.

```sh
pipeline-toolkit experiment
pipeline-toolkit experiment dry-run --repo-root /path/to/OnMaruBE --scope ci --reason 'Gradle cache 비교'
pipeline-toolkit experiment dispatch --repo-root /path/to/OnMaruBE --scope test --reason 'test 파이프라인 비교' > /outside/consumer/receipt.json
pipeline-toolkit experiment wait --receipt /outside/consumer/receipt.json --timeout 1800 --poll-interval 5 > /outside/consumer/result.json
```

인자가 없는 `experiment`는 dry-run이다. Dry-run은 GitHub 조회만 수행하고 stable JSON의 baseline/candidate SHA, 정책 버전과 dispatch payload를 출력한다. Receipt와 결과는 consumer working tree 밖에 저장해 다음 실행의 clean-tree 검사를 유지한다. `scope=ci|test`만 지원한다. `cd`와 다른 scope는 격리된 staging 준비 여부와 무관하게 v1에서 거부한다.

실제 dispatch는 `develop`의 전용 `pipeline-benchmark-experiment.yml`을 호출하며 입력 `baseline_ref`, `candidate_ref`에는 40자리 SHA를 전달한다. Consumer workflow는 해당 SHA를 사용하고 측정 중 브랜치가 이동해도 다른 source로 바꾸면 안 된다. CLI는 POST 직전에 두 remote ref를 다시 검사해 준비 중 이동을 거부한다. POST 후에는 재시도하거나 최신 workflow run을 검색하지 않는다. [GitHub REST API의 2026-03-10 workflow dispatch 응답](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)의 `workflow_run_id`와 `html_url`을 그대로 receipt에 기록하는 `gh api` 어댑터를 사용한다. 응답을 잃었거나 API가 run ID를 반환하지 않으면 dispatch가 발생했을 수 있으므로 Actions에서 확인해야 한다.

Wait는 receipt에 기록한 run/attempt를 기다리고 성공 시 artifact를 수집한다. CLI는 sample 실행이나 rerun을 시작하지 않는다. 일반 workflow matrix의 서로 다른 job은 별도 workflow run 세 개를 대신하지 않는다.

## 정책과 결과

`pipeline-experiment/1`은 양쪽 각각 **서로 다른 성공 workflow run 정확히 세 개**를 요구한다. 두 개 또는 네 개를 전달해도 일부를 선택하지 않고 `inconclusive`로 반환한다. 중복 run ID는 attempt가 달라도 중복이며, 중복 ordinal, 취소, 실패, timeout, 결측, run 신원이나 비교 조건 불일치를 제외 사유로 남긴다. 자동 추가 실행은 없다.

`compare_module_benchmarks(..., target=RELEASE)`를 재사용해 15% 초과 중앙값 회귀를 `approval_review`로 표시한다. 이 결과는 검토 자료이며 필수 CI나 자동 배포 gate를 변경하지 않는다. 모든 개별 값, 중앙값, 범위, 상대 delta, 실패율과 제외 사유를 함께 보고한다. 세 표본으로 통계적 유의성을 주장하지 않는다. `comparison.policy_outcome`과 상위 verdict는 제외 증적이 있으면 회귀 승인 요청을 만들지 않는다.

기준선 중앙값이 0이면 상대 변화율을 정의할 수 없으므로 `zero_baseline` 사유의 `inconclusive`로 반환한다. 실패율은 측정값이나 artifact의 유효성과 별개로 신원이 확인된 완료 run/attempt의 실패·취소·timeout·startup failure를 센다. 중복 run/attempt는 한 번만 세고 외부 저장소·알 수 없는 실행은 분모에서도 제외한다. `run_counts.authenticated_completed`와 `run_counts.failed`가 분모와 분자를 명시한다. 실패 run의 값이 없으면 실행 실패 사유와 `measurement_reason`을 함께 남긴다.

결과 JSON의 `collection`을 별도 파일로 저장하면 네트워크 없이 재비교할 수 있다.

```sh
pipeline-toolkit experiment compare --input collection.json
pipeline-toolkit experiment compare --input collection.json --format markdown
```

Offline 결과는 `verification=offline_replay`로 표시한다. 원본 artifact와 receipt는 consumer가 보존해야 한다. Replay는 저장된 증적의 일관성을 확인하며 GitHub에서 새로 인증한 증적이라고 주장하지 않는다.

## OnMaruBE #556이 구현할 manifest 계약

오케스트레이터는 `pipeline-experiment-manifest-<attempt>`라는 GitHub artifact 한 개에 `experiment-manifest.json` 파일 하나만 업로드한다. 취소·실패 시 원본 consumer-local 진단을 남겨야 한다. 성공 artifact는 다음 형식을 사용한다.

```json
{
  "version": 1,
  "policy_version": "pipeline-experiment/1",
  "repository": "YRootLab/OnMaru-backend",
  "baseline_ref": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "candidate_ref": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "scope": "ci",
  "experiment_run_id": 900,
  "experiment_run_attempt": 1,
  "observations": [
    {
      "side": "baseline",
      "ordinal": 1,
      "run_id": 1,
      "run_attempt": 1,
      "commit_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "value": 99,
      "suite": "full-java",
      "environment_identity": {
        "runner_image": "ubuntu-24.04",
        "java_version": "21",
        "python_version": "3.9",
        "cache_state": "cold",
        "database_fixture": "postgres-16",
        "cpu_memory_profile": "4cpu-16gb",
        "dependency_mode": "locked",
        "config_catalog_hash": "sha256:catalog"
      },
      "manifest_url": "https://github.com/YRootLab/OnMaru-backend/actions/runs/1/artifacts/1001",
      "grafana_url": "https://example.grafana.net/d/ci"
    }
  ]
}
```

예시는 한 관측값만 표시한다. 실제 성공 결과에는 baseline/candidate 각각 ordinal 1, 2, 3이 있어야 한다. `value`는 확인된 workflow wall-clock seconds이며 finite nonnegative number다. 시간선 수집이 값을 확정하지 못하면 임의의 job window나 최장 모듈 시간으로 대체하지 않고 불완전 증적을 남긴다. `suite`와 환경의 모든 항목 및 sample workflow path가 양쪽에서 같아야 한다. SHA는 두 실행의 서로 다른 source 신원이며 비교 조건의 불일치 사유가 아니다.

각 sample은 소비자 소유의 별도 `workflow_dispatch` run이고 GitHub API가 `head_sha=commit_sha`를 확인해야 한다. Sample workflow는 오케스트레이터와 다른 파일을 사용할 수 있다. 이름은 run-name을 통해 `pipeline-experiment/<experiment_run_id>/<side>/<ordinal>`로 정확히 기록한다. CLI는 `runs/<run_id>/attempts/<run_attempt>`를 조회하여 완료·success, head repository, SHA, workflow path와 이 상관관계를 검사한다. Baseline과 candidate 모두 같은 sample workflow path를 사용한다. 이 계약은 임의의 성공 CI 실행을 해당 실험의 표본으로 섞는 것을 차단한다. 소비자는 fork source나 특권·관측 secret을 sample job에 전달하지 않아야 한다.

`manifest_url`은 해당 run의 `pipeline-experiment-sample-<attempt>` GitHub artifact URL이다. CLI는 artifact metadata를 조회해 정확한 run/SHA, 이름, 크기와 만료 여부를 확인하고 `collection.artifact_checks`에 replay용 결과를 남긴다. `grafana_url`은 선택 항목이며 credential이나 query를 포함하지 않는 `https://<tenant>.grafana.net/d/<dashboard>`를 사용한다. 관측 전송이 끊기면 null/누락으로 표시하고 원본 benchmark verdict를 유지한다. CLI는 관측 secret을 요구하거나 출력하지 않는다.

Grafana tenant는 한 개의 DNS label이고 dashboard 경로는 `/d/<uid>` 또는 `/d/<uid>/<slug>`다. UID와 slug에는 ASCII 영숫자·밑줄·하이픈만 허용한다. 원본 URL의 공백·제어 문자·Markdown 구문·percent escape·추가 경로는 거부하며 파싱 과정에서 문자를 제거해 허용하지 않는다. Markdown 보고서는 링크를 재검증한 autolink로 출력하고 제외 진단 JSON은 fenced code block으로 표시한다.

## 상한과 실패 복구

Git과 `gh`는 shell 없이 argv로 호출한다. 명령 하나는 기본 30초, stdout+stderr 합계 1 MiB 이내이고 timeout·초과 출력은 process group을 종료한다. Stderr 원문은 출력하지 않는다. Wait는 최대 3600초·1000 poll, poll 간격 0.01~30초이며 전체 deadline은 개별 API 요청에도 적용된다. Artifact 목록은 최대 100개를 완전히 확인해야 한다. JSON과 zip/uncompressed manifest는 각각 1 MiB 이내이고 경로 탈출, 추가 파일, symlink와 암호화 archive를 거부한다. Artifact 명령·consumer source를 실행하거나 archive를 디스크에 추출하지 않는다.

CLI의 JSON 오류와 exit 2는 실행 조건·수집 자체 실패다. Exit 0의 `inconclusive`는 수집한 증적으로 비교를 확정할 수 없다는 의미다. Receipt의 원본 Actions run을 먼저 확인하고 consumer-local manifest·실패 진단을 사용한다. Failed/cancelled samples를 성공값으로 바꾸거나 부족한 표본을 자동 rerun하지 않는다. `command_failed`나 응답 유실 후 dispatch를 자동 반복하면 추가 비용이 발생할 수 있다.
