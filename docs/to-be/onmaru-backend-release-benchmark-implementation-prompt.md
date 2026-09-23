# OnMaru-backend Release Benchmark 연동 구현 프롬프트

## 목표

당신은 Senior Backend, CI/CD Platform, Observability Engineer다.

`onmaru-backend`에서 별도 repository인 `onmaru-modular-backend-pipeline-toolkit`을
사용하여 release tag별 benchmark와 이전 release 대비 성능 비교를 구현하라.

```text
Release Tag → Commit SHA → Image Digest → Deployment
→ Benchmark Run → Previous Release Comparison
→ Report / Artifact / Promotion Gate
```

## 제약

- benchmark 분석 로직을 backend repository에 재구현하지 않는다.
- `pipeline-toolkit` CLI를 consumer로 사용한다.
- OnMaru 서비스 DB에 benchmark raw data를 저장하지 않는다.
- 기존 API, DB, deployment, workflow convention을 먼저 조사하고 재사용한다.
- 기존 workflow와 migration을 덮어쓰지 않는다.
- fork PR에는 production secret을 전달하지 않는다.
- 근거 없는 microservice 분리나 대규모 아키텍처 변경을 하지 않는다.

## 1. 사전 조사

구현 전에 다음을 조사하고 `Current State`를 먼저 보고하라.

- Spring Boot/FastAPI module 구조
- Gradle multi-module, pytest/JUnit, Testcontainers 실행 방식
- Dockerfile과 image tagging 방식
- GitHub Actions의 현재 serial/parallel 구조
- staging/production 배포 방식과 Kubernetes/Helm 설정
- migration 실행 방식
- health/readiness/liveness/metrics endpoint
- Prometheus/OpenTelemetry 설정
- release tag, changelog, artifact storage
- GitHub token/secret 권한
- 기존 benchmark/performance test

보고 형식:

```text
Current architecture:
Current CI flow:
Current deployment flow:
Current release identity:
Current observability:
Current test entrypoints:
Current storage:
Risks:
Unknowns:
```

## 2. Release Identity

다음 metadata를 생성·검증·보존하라.

```json
{
  "repository": "YRootLab/Onmaru-backend",
  "version": "v1.4.0",
  "tag": "v1.4.0",
  "commitSha": "abc123",
  "imageRepository": "ghcr.io/yrootlab/onmaru-backend",
  "imageDigest": "sha256:...",
  "createdAt": "ISO-8601"
}
```

- tag, commit SHA, image digest를 함께 저장한다.
- 실제 배포 image digest를 기대값과 비교한다.
- staging과 production deployment를 구분한다.
- 값이 불일치하면 deployment 또는 benchmark를 실패 처리한다.
- metadata에 secret, credential, PII를 포함하지 않는다.

권장 위치는 `artifacts/release/<version>/release.json`이다.

## 3. Benchmark 설정과 CLI

가능하면 다음 파일을 추가하라.

```text
.pipeline/pipeline.yml
.pipeline/benchmark.yml
.pipeline/release.yml
```

`benchmark.yml`은 실제 command를 반영하고 다음을 정의한다.

- `service: onmaru-backend`
- `suite: default-backend`
- staging runner, architecture, CPU/memory limit
- database fixture version
- external dependency mock/real mode
- warmup runs, repetitions, minimum valid runs
- cold/warm cache state
- Spring/FastAPI unit/integration, contract, Docker, smoke stages

다음 toolkit command를 사용한다.

```bash
pipeline-toolkit release register
pipeline-toolkit benchmark suite
pipeline-toolkit benchmark compare
pipeline-toolkit publish
```

## 4. Release-to-Release 비교 workflow

기존 release workflow를 우선 재사용하고 필요한 job만 추가하라.

```text
release tag 확인
→ commit SHA 확인
→ image build 및 digest 확인
→ release metadata 등록
→ staging deploy
→ deployed image digest 검증
→ 직전 성공 release 조회
→ benchmark compare 실행
→ artifact와 Job Summary publish
→ regression warning 또는 promotion gate
→ production promotion
→ production benchmark 저장
```

비교 명령의 목표 형태:

```bash
pipeline-toolkit benchmark compare \
  --baseline "${PREVIOUS_RELEASE}" \
  --candidate "${CURRENT_RELEASE}" \
  --environment staging \
  --suite default-backend \
  --repetitions 5 \
  --cache-state warm \
  --publish
```

baseline 선택 순서는 다음과 같다.

1. 같은 production 환경의 직전 성공 release
2. 같은 major/minor 계열의 직전 성공 release
3. target branch의 최근 성공 benchmark
4. repository policy가 명시한 baseline
5. 없으면 `inconclusive`

## 5. 비교 가능성 검증

baseline과 candidate의 다음 조건을 비교하라.

- environment
- runner image와 architecture
- CPU/memory limit
- benchmark suite와 config hash
- toolkit version
- cache state
- database fixture version
- external dependency mode

조건이 다르거나 image digest, raw artifact, valid run이 부족하면 성능 결과를 확정하지 말고 `inconclusive`로 기록하라.

결과 상태는 `improved`, `regressed`, `unchanged`, `inconclusive` 중 하나다.

## 6. 저장 구조

초기에는 GitHub Artifact를 사용하고, 기존 Object Storage가 있으면 해당 convention을 따른다.

```text
benchmark/onmaru-backend/
├── releases/<version>/
│   ├── release.json
│   └── runs/<run-id>/
│       ├── manifest.json
│       ├── raw/
│       ├── normalized/
│       ├── charts/
│       └── report/report.{md,html,json}
└── comparisons/<baseline>__<candidate>/
    ├── comparison.json
    ├── report.md
    ├── report.html
    └── charts/
```

`manifest.json`에는 benchmark run ID, release version, commit SHA, image digest,
environment, suite, toolkit version, config hash, status, raw artifact URI,
report URI를 포함하라.

OnMaru 서비스 DB에는 필요할 경우 다음 reference/summary만 저장한다.

```text
releaseVersion, commitSha, imageDigest, environment,
benchmarkRunId, comparisonId, result, reportUri
```

## 7. Health, Smoke Test, Promotion

기존 Actuator/FastAPI convention을 재사용하여 health, readiness, liveness,
metrics 경로를 확인하라. Smoke test는 HTTP status, response schema, latency,
database connectivity, external dependency behavior, critical API path를 검증한다.

초기 promotion 정책:

- `improved`: promotion 가능
- `unchanged`: promotion 가능, report 기록
- `regressed`: warning과 approval 필요
- `inconclusive`: 자동 promotion 금지 또는 명시적 approval 필요

benchmark 실패를 성능 regression으로 오인하지 말고, timeout, missing artifact,
failed deployment, invalid data를 별도 failure reason으로 기록하라.

## 8. 테스트

다음 테스트를 추가하라.

### Unit

- release metadata 생성
- tag/commit/image digest validation
- baseline 선택
- config hash 생성
- environment compatibility check
- `inconclusive` 판정
- manifest 생성
- secret redaction

### Integration

- release tag workflow input
- image digest 검증
- staging deployment 후 readiness
- benchmark artifact 생성
- baseline/candidate comparison
- missing artifact, failed deployment, timeout, cancellation

### Contract

pipeline-toolkit input schema와 backend metadata schema의 호환성을 검증하라.

## 9. 보안과 Observability

- benchmark job은 read-only token을 우선 사용한다.
- deployment credential과 benchmark credential을 분리한다.
- Docker socket 접근을 기본 허용하지 않는다.
- report/log/artifact의 secret과 PII를 redaction한다.
- production benchmark는 protected environment 또는 approval을 사용한다.
- Prometheus label에 commit SHA, full tag, test name, module name, full path, workflow run ID를 넣지 않는다.
- 상세 release/version/test 정보는 report와 Benchmark Evidence Store에 저장한다.

허용되는 metric 예시:

```text
ci_pipeline_duration_seconds{service="onmaru-backend",environment="staging"}
ci_benchmark_runs_total{service="onmaru-backend",environment="staging",result="success"}
ci_pipeline_regressions_total{service="onmaru-backend",environment="staging"}
```

## 10. Acceptance Criteria

```text
[ ] release tag가 commit SHA와 연결된다.
[ ] Docker image digest가 기록되고 실제 배포 digest와 검증된다.
[ ] 이전 성공 release를 자동 선택할 수 있다.
[ ] baseline/candidate를 동일 suite와 조건으로 반복 실행한다.
[ ] 모든 BenchmarkRun ID를 Comparison에 저장한다.
[ ] median, p95, absolute delta, relative delta를 생성한다.
[ ] CPU/memory 변화도 함께 보고한다.
[ ] 비교 불가능한 결과를 inconclusive로 표시한다.
[ ] raw/normalized/report artifact를 저장한다.
[ ] GitHub Job Summary에 비교 요약을 출력한다.
[ ] release/tag artifact에 benchmark report 링크를 남긴다.
[ ] OnMaru 서비스 DB와 benchmark storage를 분리한다.
[ ] secret과 PII가 artifact에 저장되지 않는다.
[ ] production promotion 전에 staging 비교 결과를 확인할 수 있다.
[ ] 실패한 benchmark를 regression으로 잘못 판정하지 않는다.
[ ] release tag부터 raw artifact까지 결과를 재현할 수 있다.
```

## 최종 보고 형식

구현 후 다음을 보고하라.

```text
Modified workflows:
Added benchmark configuration:
Added release metadata:
Added smoke tests:
Added integration tests:
Added storage/publish configuration:
Added documentation:
Commands executed:
Verification results:
Known limitations:
Follow-up Issues:
```

먼저 조사 결과를 보고하고 구현 계획을 제시한 뒤, 각 변경을 구현하고 테스트하라.
