# Module Benchmark Output Newlines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reusable module benchmark aggregate step이 GitHub Actions output 다섯 개와 Markdown report 줄바꿈을 올바르게 기록하도록 수정한다.

**Architecture:** 기존 workflow의 embedded Python을 테스트에서 그대로 추출·실행해 파일 시스템과 `GITHUB_OUTPUT` 결과를 검증한다. production 수정은 잘못 이중 escape된 newline만 단일 escape로 바꾸며 workflow topology와 보안 경계는 유지한다.

**Tech Stack:** GitHub Actions YAML, embedded Python 3, pytest, PyYAML

## Global Constraints

- Issue #99만 수정하며 consumer source나 raw benchmark data를 포함하지 않는다.
- `.github/workflows/module-benchmark.yml`의 job topology, permissions, inputs, outputs, artifact names는 변경하지 않는다.
- 테스트는 source text 존재 여부가 아니라 embedded Python 실행 결과를 검증한다.
- `result`, `comparison_id`, `manifest_uri`, `report_artifact`, `critical_path_seconds`는 각각 별도의 물리적 `GITHUB_OUTPUT` 줄이어야 한다.
- Markdown report에는 실제 줄바꿈이 있어야 하며 literal `\\n`이 없어야 한다.
- 수정 PR은 `develop`으로 병합하고, 검증된 release flow로 `master`와 patch tag를 만든 뒤 target commit SHA를 consumer에 전달한다.

---

### Task 1: Aggregate output newline regression fix

**Files:**
- Modify: `tests/test_module_benchmark_workflow.py`
- Modify: `.github/workflows/module-benchmark.yml`
- Modify: `handoff.md`

**Interfaces:**
- Consumes: aggregate job의 `Build aggregate manifest and report` embedded Python
- Produces: GitHub output 파일의 다섯 `name=value` 줄과 실제 줄바꿈을 가진 `module-benchmark-report/report.md`

- [ ] **Step 1: Write the failing execution regression test**

  YAML에서 aggregate summary step의 `run` block을 읽고 heredoc Python을 추출한다. `tmp_path`에 module evidence와 `GITHUB_OUTPUT`을 준비하고 필요한 GitHub/step 환경 변수를 제공해 Python을 subprocess로 실행한다. output 파일을 `splitlines()`로 읽어 다섯 key가 독립적으로 존재하고 report에 literal `\\n`이 없음을 단언한다.

- [ ] **Step 2: Verify RED**

  Run `PYTHONPATH=src python3 -m pytest -q tests/test_module_benchmark_workflow.py` and confirm the new test fails because only `result` is parsed from one physical line or the report contains literal escape text.

- [ ] **Step 3: Apply the minimal newline fix**

  aggregate embedded Python의 report 문자열과 세 `output.write` 문자열에서 이중 escape된 newline을 단일 Python newline escape로 바꾼다. 다른 workflow 동작은 변경하지 않는다.

- [ ] **Step 4: Verify GREEN and repository regression**

  Run `PYTHONPATH=src python3 -m pytest -q tests/test_module_benchmark_workflow.py`, `bash scripts/verify_toolkit.sh`, and `git diff --check`.

- [ ] **Step 5: Commit and open PR**

  Commit with `fix(github): module benchmark output 줄바꿈 수정`, push `fix/99-module-output-newlines`, and open a Korean PR into `develop` with `Closes #99` and RED/GREEN evidence.
