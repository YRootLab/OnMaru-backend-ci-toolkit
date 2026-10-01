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

실제 dispatch는 `develop`의 전용 `pipeline-benchmark-experiment.yml`을 호출하며 입력 `baseline_ref`, `candidate_ref`에는 40자리 **workflow/config ref**를 전달한다. 이 둘은 application source identity가 아니다. Consumer workflow는 해당 immutable ref를 사용하되 실제 측정 대상 application source와 test plan은 아래의 별도 고정 계약을 따라야 한다. CLI는 POST 직전에 두 remote ref를 다시 검사해 준비 중 이동을 거부한다. POST 후에는 재시도하거나 최신 workflow run을 검색하지 않는다. [GitHub REST API의 2026-03-10 workflow dispatch 응답](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)의 `workflow_run_id`와 `html_url`을 그대로 receipt에 기록하는 `gh api` 어댑터를 사용한다. 응답을 잃었거나 API가 run ID를 반환하지 않으면 dispatch가 발생했을 수 있으므로 Actions에서 확인해야 한다.

Wait는 receipt에 기록한 run/attempt를 기다리고 성공 시 artifact를 수집한다. CLI는 sample 실행이나 rerun을 시작하지 않는다. 일반 workflow matrix의 서로 다른 job은 별도 workflow run 세 개를 대신하지 않는다.

## 정책과 결과

`pipeline-experiment/2`는 양쪽 각각 **서로 다른 성공 workflow run 정확히 세 개**와 별도 검증한 동일 application tree/test-plan digest를 요구한다. `/1` 문서는 source comparability를 증명하지 않으므로 새 정책에서 거부한다. 두 개 또는 네 개를 전달해도 일부를 선택하지 않고 `inconclusive`로 반환한다. 중복 run ID는 attempt가 달라도 중복이며, 중복 ordinal, 취소, 실패, timeout, 결측, run 신원이나 비교 조건 불일치를 제외 사유로 남긴다. 자동 추가 실행은 없다.

`compare_module_benchmarks(..., target=RELEASE)`를 재사용해 15% 초과 중앙값 회귀를 `approval_review`로 표시한다. 이 결과는 검토 자료이며 필수 CI나 자동 배포 gate를 변경하지 않는다. 모든 개별 값, 중앙값, 범위, 상대 delta, 실패율과 제외 사유를 함께 보고한다. 세 표본으로 통계적 유의성을 주장하지 않는다. `comparison.policy_outcome`과 상위 verdict는 제외 증적이 있으면 회귀 승인 요청을 만들지 않는다.

기준선 중앙값이 0이면 상대 변화율을 정의할 수 없으므로 `zero_baseline` 사유의 `inconclusive`로 반환한다. 실패율은 측정값이나 artifact의 유효성과 별개로 신원이 확인된 완료 run/attempt의 실패·취소·timeout·startup failure를 센다. 중복 run/attempt는 한 번만 세고 외부 저장소·알 수 없는 실행은 분모에서도 제외한다. `run_counts.authenticated_completed`와 `run_counts.failed`가 분모와 분자를 명시한다. 실패 run의 값이 없으면 실행 실패 사유와 `measurement_reason`을 함께 남긴다.

결과 JSON의 `collection`을 별도 파일로 저장하면 네트워크 없이 재비교할 수 있다. `source_identity`, 별도 API 검증 결과 `identity_checks`, `manifest_attestation`을 allowlist로 보존한다. Offline replay는 저장된 검증 증적을 신뢰해 재계산할 뿐 새 서명/API 인증이 아니다. 제삼자가 편집한 collection은 신뢰하지 말고 원 receipt로 online collection을 다시 수행한다.

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
  "policy_version": "pipeline-experiment/2",
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
      "source_identity": {
        "application_source_commit": "cccccccccccccccccccccccccccccccccccccccc",
        "application_source_tree": "dddddddddddddddddddddddddddddddddddddddd",
        "test_plan_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
      },
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

예시는 한 관측값만 표시한다. 실제 성공 결과에는 baseline/candidate 각각 ordinal 1, 2, 3이 있어야 한다. `value`는 확인된 workflow wall-clock seconds이며 finite nonnegative number다. 시간선 수집이 값을 확정하지 못하면 임의의 job window나 최장 모듈 시간으로 대체하지 않고 불완전 증적을 남긴다. `suite`와 환경의 모든 항목 및 sample workflow path가 양쪽에서 같아야 한다. 서로 다른 `commit_sha`는 workflow/config 신원이며 허용하지만 application tree와 test plan은 여섯 표본 전체에서 동일해야 한다. Application commit은 달라도 전체 Git tree OID가 같으면 같은 source로 취급한다.

### 신뢰할 수 있는 committed-source/test-scope attestation

#556은 trusted baseline controller가 application source commit을 immutable SHA로 선택하고 양쪽에 같은 source를 checkout하도록 구현해야 한다. 전체 root Git tree OID(`git rev-parse <application_source_commit>^{tree}`)에는 application, dependency locks, database fixture와 실행 설정 등 모든 tracked 입력을 포함한다. Workflow 최적화 ref와 source checkout을 분리한다. Candidate application 코드나 test subset이 바뀌면 파이프라인 성능 비교가 아니다.

Application commit에는 `.github/pipeline-benchmark-test-plan.json`을 commit한다. 최소 `scope`와 `suite`를 포함하며, #556 producer는 실제 실행 명령·대상 module·test filter·fixture/seed·dependency mode를 빠짐없이 고정해야 한다. `git show <application_source_commit>:.github/pipeline-benchmark-test-plan.json`의 **원본 바이트** SHA-256을 `test_plan_sha256`으로 기록한다. JSON 재직렬화의 hash를 쓰지 않는다. Trusted worker는 이 committed plan만 실행하고 candidate artifact/입력 문자열을 명령으로 실행하지 않으며, dirty/untracked source 변경과 scope 축소를 거부한다. Candidate config는 검토된 cache/scheduling 등 제한된 옵션만 바꿀 수 있고 테스트 명령/대상을 override할 수 없다.

별도 trusted attestor job은 GitHub API와 trusted worker에서 확인한 실제 checkout tree·실행 plan·run/attempt를 사용해 최종 manifest를 생성한다. Candidate sample이 주장한 digest를 그대로 복사하거나 candidate가 최종 artifact를 업로드하도록 하면 안 된다. Candidate/테스트 job에는 `id-token: write`, `attestations: write`, upload/관측 secret이나 privileged token을 주지 않는다. Attestor는 candidate source·artifact 명령을 실행하지 않으며 baseline의 검토된 immutable workflow만 사용한다. 이 격리가 실제 실행과 서명된 신원의 연결을 보장해야 한다; digest 문자열이나 sample artifact metadata만으로는 그 연결을 증명할 수 없다.

Attestor는 업로드할 **정확한 experiment-manifest.json 바이트**에 GitHub build provenance attestation을 발행한다. Signer는 `YRootLab/OnMaru-backend/.github/workflows/pipeline-benchmark-experiment.yml`, signer/source digest는 receipt의 baseline SHA, source ref는 `refs/heads/develop`, GitHub-hosted runner여야 한다. [공식 `gh attestation verify` 계약](https://cli.github.com/manual/gh_attestation_verify)에 따라 CLI는 repo·signer workflow·두 digest·source ref·self-hosted 거부를 고정한 read-only 서명 검증을 수행한다. Exact byte digest와 trusted signer 검증으로 candidate의 manifest 교체/위조를 차단한다. 재사용 signer workflow로 변경하려면 Toolkit의 고정 signer 정책도 별도 리뷰해야 한다.

CLI는 각 application commit을 authenticated GitHub Git Commit API로 조회해 tree OID를 대조하고, 해당 SHA의 committed test-plan 파일을 Contents API로 가져와 Git blob OID·원본 SHA-256·scope/suite를 검증한다. 검증 결과는 run/attempt마다 별도로 보존한다. Source/tree/plan 누락·위조·API 실패·서명 실패는 제외 및 `inconclusive`이고 성능 verdict를 만들지 않는다. API 조회는 committed object 신원을, trusted attestation은 실제 실행과 그 신원의 연결을 검증한다. #555/#556가 이 계약을 실제 소비자에서 검증하기 전에는 로컬 fake-gh 통과를 실제 integration 완료로 간주하지 않는다.

각 sample은 소비자 소유의 별도 `workflow_dispatch` run이고 GitHub API가 `head_sha=commit_sha`를 확인해야 한다. Sample workflow는 오케스트레이터와 다른 파일을 사용할 수 있다. 이름은 run-name을 통해 `pipeline-experiment/<experiment_run_id>/<side>/<ordinal>`로 정확히 기록한다. CLI는 `runs/<run_id>/attempts/<run_attempt>`를 조회하여 완료·success, head repository, SHA, workflow path와 이 상관관계를 검사한다. Baseline과 candidate 모두 같은 sample workflow path를 사용한다. 이 계약은 임의의 성공 CI 실행을 해당 실험의 표본으로 섞는 것을 차단한다. 소비자는 fork source나 특권·관측 secret을 sample job에 전달하지 않아야 한다.

`manifest_url`은 해당 run의 `pipeline-experiment-sample-<attempt>` GitHub artifact URL이다. CLI는 artifact metadata를 조회해 정확한 run/SHA, 이름, 크기와 만료 여부를 확인하고 `collection.artifact_checks`에 replay용 결과를 남긴다. `grafana_url`은 선택 항목이며 credential이나 query를 포함하지 않는 `https://<tenant>.grafana.net/d/<dashboard>`를 사용한다. 관측 전송이 끊기면 null/누락으로 표시하고 원본 benchmark verdict를 유지한다. CLI는 관측 secret을 요구하거나 출력하지 않는다.

Grafana tenant는 한 개의 DNS label이고 dashboard 경로는 `/d/<uid>` 또는 `/d/<uid>/<slug>`다. UID와 slug에는 ASCII 영숫자·밑줄·하이픈만 허용한다. 원본 URL의 공백·제어 문자·Markdown 구문·percent escape·추가 경로는 거부하며 파싱 과정에서 문자를 제거해 허용하지 않는다. Markdown 보고서는 링크를 재검증한 autolink로 출력하고 제외 진단 JSON은 fenced code block으로 표시한다.

## 상한과 실패 복구

Git과 `gh`는 shell 없이 argv로 호출한다. 명령 하나는 기본 30초, stdout+stderr 합계 1 MiB 이내이고 timeout·초과 출력은 process group에 TERM, 0.1초 후 KILL을 보내고 최대 0.5초 reap한다. 이미 종료한 부모도 정리가 끝날 때까지 reap하지 않아 PID/PGID 재사용으로 다른 group을 종료하지 않는다. Stderr 원문은 출력하지 않는다. Wait는 최대 3600초·1000 poll, poll 간격 0.01~30초이며 전체 deadline은 개별 API 요청에도 적용된다. Artifact 목록은 최대 100개를 완전히 확인해야 한다. JSON과 ZIP은 각각 1 MiB 이내다. ZIP은 정확히 한 멤버만 허용하므로 멤버/합산 비압축 바이트 상한 모두 1 MiB이며, 64 KiB 이하 출력 chunk의 실제 streaming inflation으로 상한을 검사한다. Local/central size·CRC·method·flags 일치, 실제 크기·CRC와 stream EOF를 확인한다. Forged size, data descriptor, ZIP64/extra field, duplicate/추가 파일, trailing compressed data, symlink와 암호화 archive는 거부한다. 디스크 추출이나 artifact 명령 실행은 없다. 서명 검증에만 bounded JSON 원본을 private temporary directory에 기록하고 즉시 정리한다; consumer source/raw API 응답은 저장하지 않는다.

CLI의 JSON 오류와 exit 2는 실행 조건·수집 자체 실패다. Exit 0의 `inconclusive`는 수집한 증적으로 비교를 확정할 수 없다는 의미다. Receipt의 원본 Actions run을 먼저 확인하고 consumer-local manifest·실패 진단을 사용한다. Failed/cancelled samples를 성공값으로 바꾸거나 부족한 표본을 자동 rerun하지 않는다. `command_failed`나 응답 유실 후 dispatch를 자동 반복하면 추가 비용이 발생할 수 있다.

CLI를 Python으로 embed할 때 custom/ignored `SIGCHLD` handler는 PID reservation을 깨뜨릴 수 있어 subprocess 시작 전에 `unsafe_process_reaping`으로 거부한다. 기본 child-reaping 정책의 별도 CLI process를 사용한다. OS가 KILL 이후에도 reap하지 못하면 0.5초 상한에서 반환하며 다른 process group을 탐색·종료하지 않는다.
