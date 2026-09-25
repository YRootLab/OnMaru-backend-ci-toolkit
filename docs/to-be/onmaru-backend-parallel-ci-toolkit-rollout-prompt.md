# OnMaru-backend에서 Toolkit 기반 병렬 CI를 안전하게 rollout하는 구현 프롬프트

## 이 작업은 속도와 검증 범위를 함께 지켜야 합니다

당신은 OnMaru-backend의 Senior Backend·CI/CD Platform·Observability Engineer다. 별도 repository인 `YRootLab/OnMaru-backend-ci-toolkit`을 GitHub Actions reusable workflow로 호출해, 기존의 직렬 CI를 측정 가능하고 안전한 병렬 CI로 전환하라.

목표는 테스트를 빼서 빨라 보이게 만드는 일이 아니다. 같은 검증 범위를 유지하고, 직렬 기준선과 같은 조건의 병렬 성공 표본을 비교해 실제 대기 시간 개선을 증명하는 일이다. backend application에 Toolkit을 라이브러리로 import하지 말고, consumer-owned catalog와 version-pinned reusable workflow를 사용하라.

```text
serial baseline → shadow check → successful parallel evidence
→ final verify fan-in → durable develop/nightly/release trend
```

## 현재 상태를 먼저 확인하고 PR #374를 안전하게 대체합니다

PR #374는 consumer-owned module benchmark caller를 추가하려던 올바른 출발점이다. 그러나 현재 `develop`과 충돌하고, AI module의 `uv` bootstrap 수정 전 실행이 실패한 이력이 있다. **PR #374를 즉시 닫지 않는다.** 먼저 최신 `develop`에서 대체 PR을 만들고, 실제 GitHub Actions 검증이 성공한 뒤에만 #374에 대체 PR 링크와 사유를 남겨 `superseded`로 닫는다.

대체 PR은 최신 `develop`에서 `feature/365-toolkit-module-caller-rollout` 같은 짧은 작업 브랜치로 시작한다. 과거 PR의 설명과 테스트 의도는 재사용할 수 있지만, 충돌을 기계적으로 해결하거나 과거의 성공·실패 run을 새 구현의 증거로 쓰지 않는다.

작업을 시작하기 전에 아래 이슈와 현재 workflow를 조사해 `Current State`를 먼저 보고하라.

- #364: 기존 `verify`를 fan-out/fan-in required check로 전환
- #365: Toolkit module matrix caller와 affected fallback 연결
- #366: develop/nightly/release/CD evidence와 gate 연결
- #368: serial baseline manifest 발행
- #379: AI module runner의 `uv` bootstrap 수정 완료 여부

## 호출자는 immutable Toolkit release를 안전하게 고정합니다

Toolkit workflow와 runtime checkout에는 반드시 같은 **40자리 commit SHA**를 전달한다. branch명, mutable tag, caller의 `github.workflow_sha`를 `toolkit_ref`로 넘기면 안 된다. caller SHA는 OnMaru-backend의 commit이지 Toolkit implementation SHA가 아니기 때문이다.

현재 검증된 Toolkit release `v0.1.1`의 target SHA는 다음과 같다. 새 release가 검증되면 그 release의 immutable target SHA로 함께 갱신하되, workflow ref와 `toolkit_ref`는 항상 같은 값을 사용한다.

```yaml
jobs:
  module-benchmark:
    uses: YRootLab/OnMaru-backend-ci-toolkit/.github/workflows/module-benchmark.yml@0f6049a59add9e97dff3d37671ee524c8f3b6ce8
    with:
      catalog_path: .github/benchmark-modules.yml
      toolkit_ref: 0f6049a59add9e97dff3d37671ee524c8f3b6ce8
      mode: ${{ github.event_name == 'pull_request' && 'pr' || 'develop' }}
      max_parallel: 4
      baseline_ref: develop
      comment_mode: none
```

caller workflow는 PR, `develop` push, 수동 실행에서 동작할 수 있다. 권한은 기본 `contents: read`로 제한하고, `secrets: inherit`, write token, release/deploy environment, deployment credential을 넣지 않는다. fork PR은 항상 read-only로 처리한다.

`.github/benchmark-modules.yml`은 OnMaru-backend가 소유한다. 각 module에 경로, 실제 테스트 명령, 의존 관계, resource profile을 기록한다. 일반 파일 변경은 해당 module과 역의존 module을 선택하고, Gradle 설정·공통 workflow·판단 불가 path는 full-suite fallback을 사용해야 한다. docs-only, common path, unknown path, direct module path를 fixture 테스트로 고정하라.

## 처음에는 shadow check로 관측하고 기존 검증을 보존합니다

대체 PR이 병합돼도 기존 `.github/workflows/ci.yml`의 직렬 `verify`를 제거하거나 약화하지 않는다. 새로운 module benchmark는 처음에는 shadow check다. 즉 결과, artifact, critical path를 관측하지만 merge 여부는 기존 required `verify`가 결정한다.

shadow 기간에는 다음을 확인한다.

- 모든 catalog module이 실제 runner에서 command를 실행하는가
- #379의 AI `uv` bootstrap이 fresh runner에서도 동작하는가
- matrix가 `max_parallel: 4`의 동시성 상한을 지키는가
- 각 module evidence와 aggregate report artifact가 생성되는가
- 실패, 취소, artifact 누락이 `failed` 또는 `inconclusive`로 남는가
- 빠른 실패를 빠른 성공으로 계산하지 않는가

같은 commit SHA와 같은 runner/cache/toolchain 조건에서 병렬 성공 표본을 세 번 모으기 전에는 official speedup을 주장하지 않는다. artifact URI, run ID, module wall-clock, aggregate critical path, success/failure status를 모두 남긴다.

## 직렬 기준선도 artifact로 고정한 뒤 공정하게 비교합니다

이미 동일 commit SHA `34276f201ce6f7b5ffb6e7ab2784eb584a91a699`에서 직렬 `verify` 성공 세 표본을 확보했다.

| 표본 | `verify` 시간 |
| --- | ---: |
| run 36159816646 | 413초 |
| run 36160594916 | 361초 |
| run 36161322635 | 400초 |
| 중앙값 | 400초 |

#368에서 collector workflow를 기본 브랜치에서도 workflow-dispatch할 수 있게 보완하고, 위 run ID를 입력으로 `ci-serial-baseline` immutable artifact를 발행하라. raw benchmark data나 consumer source는 Toolkit repository에 commit하지 않는다.

비교는 다음 조건이 모두 맞는 성공 표본끼리만 수행한다.

- 동일 commit SHA 또는 사전에 승인된 동일 코드·명령 조건
- runner image와 architecture
- dependency mode와 cache policy/state
- Java·Python 버전과 실행한 suite/명령
- complete artifact와 success 결과

CPU·메모리(RSS)는 GitHub Actions API만으로 수집할 수 없다. 수집하지 못한 값은 `null` 또는 `unavailable`로 보존하고 0으로 기록하지 않는다. 조건이 다르거나 표본이 부족하면 결과는 `inconclusive`다.

병렬 성공 표본도 세 번 모인 뒤 중앙값과 critical path를 계산한다. 개선율은 아래 수식으로 구하되, 실패율·취소율·artifact 누락이 증가하지 않은 경우에만 `improved`로 표시한다.

```text
(직렬 중앙값 - 병렬 중앙값) / 직렬 중앙값 × 100
```

## 최종 verify는 결과를 모으되 중복 테스트를 만들지 않습니다

shadow evidence가 안정화되면 #364에서 기존 `verify`를 final fan-in check로 전환한다. `verify`라는 check 이름을 유지하면 branch rule과 개발자 경험을 불필요하게 바꾸지 않아도 된다.

최종 구조에서는 같은 Gradle module test를 native lane과 Toolkit matrix가 두 번 실행하지 않도록 역할을 명시한다.

| 실행 주체 | 책임 |
| --- | --- |
| Toolkit matrix | 변경 영향 기반 Gradle/Python module test와 module evidence |
| native CI lane | repository hygiene, contract, 생성물 등 matrix 밖의 검사 |
| final `verify` | 모든 lane 결과, module artifact 완전성, 허용된 skip을 fan-in으로 판정 |

child job 하나라도 실패하거나 필요한 artifact가 없으면 final `verify`도 실패해야 한다. skip은 명시적으로 보고하고 success로 위장하지 않는다. 이 단계의 workflow fixture와 PR Actions run을 #364의 완료 증거로 남긴다.

## 측정은 PR에서 끝나지 않고 develop·release까지 이어집니다

#366에서 PR, `develop`, nightly, release의 목적을 분리한다. PR은 빠른 변경 영향 피드백, `develop`과 nightly는 full-suite 반복 표본, release는 immutable manifest와 이전 release 비교를 담당한다. CD는 build 시작부터 deploy, health check 성공까지의 lead time을 별도 evidence로 남긴다.

release 비교에는 tag, commit SHA, image digest, runner profile, configuration hash, cache state, benchmark suite를 보존한다. 최소 다섯 개의 비교 가능한 성공 표본을 확보하고, 중앙값이 15% 이상 느려지면 approval-hold 결과를 만든다. 누락·실패·환경 불일치는 performance regression이 아니라 `inconclusive` 또는 별도 failure reason으로 기록한다.

## branch protection은 마지막에 별도 운영 변경으로 제안합니다

병렬 final `verify`가 안정화되고 shadow/rollout 증거가 충분히 쌓이기 전에는 branch protection을 바꾸지 않는다. 안정화 후에는 `develop`과 `master`의 required check를 final `verify`로 지정하는 별도 Issue와 PR을 제안한다. branch protection은 저장소 운영 정책이므로 자동으로 변경하거나 우회하지 않는다.

## 완료 보고에는 검증과 한계를 함께 적습니다

각 PR 설명에는 구현한 workflow·catalog·테스트, immutable Toolkit SHA, 실행한 GitHub Actions run, artifact URL, 중앙값·critical path·실패율, 비교 가능성 판정, 남은 한계를 기록한다. 관련 이슈는 `Refs` 또는 실제 완료 시에만 `Closes`로 연결한다. PR #374는 대체 PR이 성공적으로 merge된 뒤에만 supersede 사유와 대체 링크를 남겨 닫는다.
