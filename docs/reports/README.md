# Reports

이 폴더는 toolkit을 사용한 CI/CD·테스트·benchmark 관측 결과 중, 다른 개발자가 저장소에서 검토해야 하는 상세 기술 보고서를 보관한다.

- 보고서는 관측값, 실행 링크, 비교 조건, 변경 이력, 확정·미확정 결론을 분리한다.
- 코드 또는 pipeline 변경과 함께 공유할 보고서는 Git Flow PR로 `develop`에 반영한다.
- 비개발자·포트폴리오 독자를 위한 쉬운 설명은 `docs/reports/easy/`에 생성한다. 이 경로는 `.gitignore` 처리되어 로컬에서만 확인하며 PR에 포함하지 않는다.
- 작성에는 [상세 기술 보고서 프롬프트](prompts/detailed-technical-report.md)를 사용한다.

## OnMaru-backend CI Toolkit 학습 시리즈

소스 파일을 모르는 독자도 CI Toolkit의 설계와 rollout을 따라갈 수 있도록, 아래 세 편의 기술 블로그 원고를 함께 제공한다.

- [GitHub Actions·CI·CD·테스트의 실행 원리](2026-09-26-onmaru-ci-series-01-actions-ci-cd-tests.md)
- [reusable workflow와 두 저장소의 권한 경계](2026-09-26-onmaru-ci-series-02-reusable-workflow-boundary.md)
- [fan-out/fan-in, shadow check, evidence 기반 rollout](2026-09-26-onmaru-ci-series-03-parallel-rollout-evidence.md)

## report-bundle 출력 경계

`pipeline-toolkit report-bundle`은 하나의 관측 입력으로 두 독자용 초안과 prompt packet을 계획한다.

- `--audience developer`: Git으로 추적하는 상세 기술 보고서와 prompt packet만 만든다.
- `--audience easy`: Git에서 제외한 `docs/reports/easy/`의 쉬운 보고서와 prompt packet만 만든다.
- `--audience both`: 두 독자용 결과를 함께 만든다.

기본 실행은 출력 예정 경로와 내용을 보여 주기만 하며 파일을 만들지 않는다. 실제 저장은 `--write`를 명시해야 한다. `--write`는 저장소 root 아래의 출력 경로만 허용하고, 기존 파일은 `--overwrite`가 없으면 덮어쓰지 않는다.

## 사용 방법

관측 사실은 UTF-8 JSON으로 한 번만 준비한다. 기본 실행은 dry-run이며, JSON으로 생성 대상과 독자 범위를 확인할 수 있다.

```bash
pipeline-toolkit report-bundle \
  --input ci-observation.json \
  --slug onmaru-backend-ci \
  --repo-root .
```

공식 개발자용 보고서만 PR에 포함하려면 다음처럼 명시적으로 저장한다.

```bash
pipeline-toolkit report-bundle \
  --input ci-observation.json \
  --slug onmaru-backend-ci \
  --audience developer \
  --write
```

쉬운 설명도 함께 로컬에서 만들려면 `--audience both --write`를 사용한다. 쉬운판은 `docs/reports/easy/`에만 생성되고 Git에서 제외된다. 기존 결과를 바꾸려면 `--write --overwrite`를 함께 지정해야 한다.

OpenAI 완성본은 기본적으로 호출되지 않는다. provider와 model을 모두 명시하고 `--write`를 사용한 경우에만 `OPENAI_API_KEY`를 읽는다.

```bash
OPENAI_API_KEY="..." pipeline-toolkit report-bundle \
  --input ci-observation.json \
  --slug onmaru-backend-ci \
  --audience both \
  --write \
  --ai-provider openai \
  --model gpt-5
```

이 명령은 생성된 공식 보고서를 자동으로 commit, push, 또는 merge하지 않는다.
