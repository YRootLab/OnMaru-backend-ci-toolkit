# Reports

이 폴더는 toolkit을 사용한 CI/CD·테스트·benchmark 관측 결과 중, 다른 개발자가 저장소에서 검토해야 하는 상세 기술 보고서를 보관한다.

- 보고서는 관측값, 실행 링크, 비교 조건, 변경 이력, 확정·미확정 결론을 분리한다.
- 코드 또는 pipeline 변경과 함께 공유할 보고서는 Git Flow PR로 `develop`에 반영한다.
- 비개발자·포트폴리오 독자를 위한 쉬운 설명은 `docs/reports/easy/`에 생성한다. 이 경로는 `.gitignore` 처리되어 로컬에서만 확인하며 PR에 포함하지 않는다.
- 작성에는 [상세 기술 보고서 프롬프트](prompts/detailed-technical-report.md)를 사용한다.

## report-bundle 출력 경계

`pipeline-toolkit report-bundle`은 하나의 관측 입력으로 두 독자용 초안과 prompt packet을 계획한다.

- `--audience developer`: Git으로 추적하는 상세 기술 보고서와 prompt packet만 만든다.
- `--audience easy`: Git에서 제외한 `docs/reports/easy/`의 쉬운 보고서와 prompt packet만 만든다.
- `--audience both`: 두 독자용 결과를 함께 만든다.

기본 실행은 출력 예정 경로와 내용을 보여 주기만 하며 파일을 만들지 않는다. 실제 저장은 `--write`를 명시해야 한다. `--write`는 저장소 root 아래의 출력 경로만 허용하고, 기존 파일은 `--overwrite`가 없으면 덮어쓰지 않는다.
