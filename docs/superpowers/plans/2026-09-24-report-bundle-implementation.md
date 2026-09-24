# Report Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create one validated report-facts input that deterministically generates developer and easy-reader drafts/prompts, with an opt-in OpenAI adapter and safe `docs/reports` output boundaries.

**Architecture:** Add a dedicated `pipeline_toolkit.report_bundle` package rather than changing the existing generic benchmark renderer. Its parser validates report facts and rejects unsafe data; deterministic renderers construct both audiences; a writer confines files to `docs/reports` and ignored `docs/reports/easy`; an optional adapter calls OpenAI only after explicit provider/model selection. The CLI orchestrates these components and defaults to dry-run.

**Tech Stack:** Python 3.9+, stdlib `json`, `pathlib`, `urllib.request`, existing `argparse`, pytest, coverage, GitHub Actions.

## Global Constraints

- Keep the existing `report` CLI behavior and its tests unchanged.
- Require UTF-8 JSON facts and reject invalid URLs, unsafe paths, unsupported statuses, missing fields, credentials, and secret-like values before writing or calling AI.
- Default to dry-run; only `--write` creates files; only `--ai-provider openai --model NAME` permits network access.
- Developer files are Git-tracked under `docs/reports`; easy files are local-only under `docs/reports/easy` and ignored by Git.
- Never log or persist API keys, raw credentials, or source content beyond the validated facts input.
- A failed, cancelled, timed-out, missing, or non-comparable fact cannot be rendered as an improvement or included in a delta calculation.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/pipeline_toolkit/report_bundle/model.py` | Immutable fact models, JSON parsing, schema and safety validation |
| `src/pipeline_toolkit/report_bundle/render.py` | Deterministic developer/easy Markdown and prompt packet rendering |
| `src/pipeline_toolkit/report_bundle/write.py` | Safe output planning, atomic writes, root containment and overwrite policy |
| `src/pipeline_toolkit/report_bundle/ai.py` | Opt-in OpenAI HTTP adapter and AI Markdown contract validation |
| `src/pipeline_toolkit/report_bundle/__init__.py` | Public report-bundle API |
| `src/pipeline_toolkit/cli.py` | `report-bundle` parser and orchestration |
| `tests/test_report_bundle_model.py` | Input and fail-closed validation coverage |
| `tests/test_report_bundle_render.py` | Deterministic audience output and safety wording coverage |
| `tests/test_report_bundle_write.py` | Dry-run, root containment, overwrite, atomic write coverage |
| `tests/test_report_bundle_ai.py` | Mocked API request, no-key, response contract coverage |
| `tests/test_cli.py` | CLI integration and legacy report regression coverage |
| `.gitignore` | Ignore `docs/reports/easy/` only |
| `docs/reports/README.md` | Document official/easy output boundary and commands |

### Task 1: Validate the canonical report-facts contract

**Files:**

- Create: `src/pipeline_toolkit/report_bundle/model.py`
- Create: `src/pipeline_toolkit/report_bundle/__init__.py`
- Test: `tests/test_report_bundle_model.py`

**Interfaces:**

- Produces: `ReportFact`, `ReportBundleInput`, `ReportBundleValidationError`, `load_report_bundle(path: Path) -> ReportBundleInput`
- Consumes: UTF-8 JSON input following the design spec.

- [ ] **Step 1: Write failing validation tests**

```python
def test_load_report_bundle_accepts_success_and_non_comparable_facts(tmp_path):
    source = tmp_path / "facts.json"
    source.write_text(json.dumps({
        "title": "CI observation", "observed_at": "2026-09-24", "summary": "Measured CI.",
        "facts": [{"name": "serial", "value": 454, "unit": "seconds", "status": "success",
                   "source_url": "https://github.com/org/repo/actions/runs/1", "comparable": False}],
        "limitations": ["same SHA samples are missing"], "next_steps": ["collect three samples"]
    }))
    result = load_report_bundle(source)
    assert result.facts[0].value == 454

def test_load_report_bundle_rejects_credential_url_and_failed_improvement_claim(tmp_path):
    source = tmp_path / "unsafe.json"
    source.write_text(json.dumps({"title": "x", "observed_at": "2026-09-24", "summary": "x",
        "facts": [{"name": "x", "value": 1, "unit": "seconds", "status": "failed",
                   "source_url": "https://token@example.test/run", "comparable": True}],
        "limitations": ["x"], "next_steps": ["x"]}))
    with pytest.raises(ReportBundleValidationError): load_report_bundle(source)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python3 -m pytest tests/test_report_bundle_model.py -q`

Expected: FAIL because `pipeline_toolkit.report_bundle` does not exist.

- [ ] **Step 3: Implement immutable models and fail-closed parsing**

```python
ALLOWED_STATUSES = frozenset({"success", "failed", "cancelled", "timeout", "missing"})

@dataclass(frozen=True)
class ReportFact:
    name: str; value: float; unit: str; status: str; source_url: str; comparable: bool

def load_report_bundle(path: Path) -> ReportBundleInput:
    payload = json.loads(path.read_text(encoding="utf-8"))
    # validate required strings/lists, ISO date, https URL without userinfo,
    # finite numeric values, allowed status, and recursively reject secret-like keys.
    return ReportBundleInput(...)
```

Implement `is_performance_eligible(fact)` as `fact.status == "success" and fact.comparable` so later tasks cannot accidentally use failed evidence for improvement wording.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `python3 -m pytest tests/test_report_bundle_model.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline_toolkit/report_bundle tests/test_report_bundle_model.py
git commit -m "feat(report): validate canonical report facts"
```

### Task 2: Render deterministic developer and easy-reader packets

**Files:**

- Create: `src/pipeline_toolkit/report_bundle/render.py`
- Test: `tests/test_report_bundle_render.py`

**Interfaces:**

- Consumes: `ReportBundleInput` and `is_performance_eligible` from Task 1.
- Produces: `render_developer_draft(bundle) -> str`, `render_easy_draft(bundle) -> str`, `render_developer_prompt(bundle) -> str`, `render_easy_prompt(bundle) -> str`.

- [ ] **Step 1: Write failing audience-rendering tests**

```python
def test_easy_draft_uses_plain_language_and_marks_failed_candidate_as_unconfirmed(bundle):
    rendered = render_easy_draft(bundle)
    assert "코드를 합치기 전 자동 확인" in rendered
    assert "개선 성과로 사용하지 않음" in rendered
    assert "21% 빨라졌다" not in rendered

def test_developer_prompt_preserves_source_links_and_comparability_rule(bundle):
    rendered = render_developer_prompt(bundle)
    assert "https://github.com/org/repo/actions/runs/1" in rendered
    assert "success and comparable" in rendered
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python3 -m pytest tests/test_report_bundle_render.py -q`

Expected: FAIL because the renderer functions do not exist.

- [ ] **Step 3: Implement deterministic section renderers**

```python
def render_developer_draft(bundle: ReportBundleInput) -> str:
    return "\n".join([f"# {bundle.title}", "", "## Evidence quality", ...]) + "\n"

def render_easy_draft(bundle: ReportBundleInput) -> str:
    return "\n".join([f"# {bundle.title}", "", "## 어떤 일이 있었나", ...]) + "\n"
```

Sort facts by `(status, name, source_url)` for stable output. Render failed or non-comparable facts only in a limitation section containing the fixed sentence `개선 성과로 사용하지 않음`. Prompt packets must include validated facts and explicit audience rules, not API keys or raw input paths.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `python3 -m pytest tests/test_report_bundle_render.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline_toolkit/report_bundle/render.py tests/test_report_bundle_render.py
git commit -m "feat(report): render dual-audience report drafts"
```

### Task 3: Add safe write planning and ignored easy output

**Files:**

- Create: `src/pipeline_toolkit/report_bundle/write.py`
- Modify: `.gitignore`
- Modify: `docs/reports/README.md`
- Test: `tests/test_report_bundle_write.py`

**Interfaces:**

- Consumes: four renderer strings from Task 2 and a repository root path.
- Produces: `OutputPlan`, `plan_outputs(root: Path, observed_at: str, slug: str, audience: str, easy_output: Path | None) -> OutputPlan`, `write_outputs(plan, contents, overwrite: bool) -> tuple[Path, ...]`.

- [ ] **Step 1: Write failing path-safety tests**

```python
def test_plan_outputs_uses_tracked_and_ignored_defaults(tmp_path):
    plan = plan_outputs(tmp_path, "2026-09-24", "ci-observation", "both", None)
    assert plan.developer_markdown == tmp_path / "docs/reports/2026-09-24-ci-observation-detailed.md"
    assert plan.easy_markdown == tmp_path / "docs/reports/easy/2026-09-24-ci-observation-easy.md"

def test_write_outputs_rejects_escape_and_existing_file_without_overwrite(tmp_path):
    with pytest.raises(ValueError): plan_outputs(tmp_path, "2026-09-24", "../escape", "easy", None)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python3 -m pytest tests/test_report_bundle_write.py -q`

Expected: FAIL because `plan_outputs` does not exist.

- [ ] **Step 3: Implement root-contained atomic writer and documentation**

```python
def _inside(root: Path, candidate: Path) -> bool:
    return candidate.resolve().is_relative_to(root.resolve())

def write_outputs(plan: OutputPlan, contents: Mapping[Path, str], overwrite: bool) -> tuple[Path, ...]:
    for destination in contents:
        if destination.exists() and not overwrite:
            raise FileExistsError(destination)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(contents[destination], encoding="utf-8")
        temporary.replace(destination)
    return tuple(contents)
```

Use a Python 3.9-compatible containment helper based on `os.path.commonpath`, not `Path.is_relative_to`. Add `.gitignore` entry `docs/reports/easy/`. Document `--audience developer|easy|both`, `--write`, and the tracked/ignored boundary in `docs/reports/README.md`.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `python3 -m pytest tests/test_report_bundle_write.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline_toolkit/report_bundle/write.py tests/test_report_bundle_write.py .gitignore docs/reports/README.md
git commit -m "feat(report): write dual reports within safe roots"
```

### Task 4: Add the opt-in OpenAI adapter without making it a runtime requirement

**Files:**

- Create: `src/pipeline_toolkit/report_bundle/ai.py`
- Test: `tests/test_report_bundle_ai.py`

**Interfaces:**

- Consumes: prompt strings from Task 2 and `OPENAI_API_KEY` only when `provider == "openai"`.
- Produces: `generate_openai_markdown(prompt: str, model: str, api_key: str, opener: Callable[..., Any]) -> str`, `validate_ai_markdown(markdown: str, audience: str) -> str`.

- [ ] **Step 1: Write failing adapter tests with a fake opener**

```python
def test_openai_adapter_sends_prompt_without_api_key_in_body():
    seen = {}
    def opener(request, timeout):
        seen["body"] = request.data.decode()
        return FakeResponse('{"choices":[{"message":{"content":"# Report\\n## 한계"}}]}')
    result = generate_openai_markdown("facts", "gpt-5", "secret-key", opener)
    assert result.startswith("# Report")
    assert "secret-key" not in seen["body"]

def test_validate_ai_markdown_rejects_easy_claim_without_comparable_evidence():
    with pytest.raises(ValueError): validate_ai_markdown("# x\n21% 빨라졌다", "easy")
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python3 -m pytest tests/test_report_bundle_ai.py -q`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Implement the adapter with stdlib HTTP only**

```python
def generate_openai_markdown(prompt, model, api_key, opener=urllib.request.urlopen):
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with opener(request, timeout=30) as response:
        return json.loads(response.read())["choices"][0]["message"]["content"]
```

Require a non-empty provider, model, and key. Catch `urllib.error.URLError` at the CLI boundary, print no request headers, and do not write AI output until `validate_ai_markdown` confirms the required headings and absence of unsupported performance-claim phrases.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `python3 -m pytest tests/test_report_bundle_ai.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline_toolkit/report_bundle/ai.py tests/test_report_bundle_ai.py
git commit -m "feat(report): add opt-in OpenAI report adapter"
```

### Task 5: Wire the CLI, document usage, and run regression verification

**Files:**

- Modify: `src/pipeline_toolkit/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `docs/reports/README.md`

**Interfaces:**

- Consumes: Tasks 1–4 public APIs.
- Produces: `pipeline-toolkit report-bundle --input PATH --slug SLUG --audience {developer,easy,both} [--write] [--overwrite] [--easy-output PATH] [--ai-provider openai --model NAME]`.

- [ ] **Step 1: Write failing CLI behavior tests**

```python
def test_report_bundle_is_dry_run_by_default(tmp_path, capsys):
    source = write_valid_bundle(tmp_path)
    assert main(["report-bundle", "--input", str(source), "--slug", "ci", "--repo-root", str(tmp_path)]) == 0
    assert not (tmp_path / "docs/reports/2026-09-24-ci-detailed.md").exists()
    assert '"dry_run": true' in capsys.readouterr().out

def test_report_bundle_requires_write_for_overwrite_and_provider_model_pair(tmp_path):
    source = write_valid_bundle(tmp_path)
    assert main(["report-bundle", "--input", str(source), "--slug", "ci", "--overwrite"]) == 2
    assert main(["report-bundle", "--input", str(source), "--slug", "ci", "--ai-provider", "openai"]) == 2
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py -q`

Expected: FAIL because `report-bundle` is not an argparse subcommand.

- [ ] **Step 3: Add CLI orchestration and machine-readable summary**

```python
bundle = sub.add_parser("report-bundle")
bundle.add_argument("--input", required=True); bundle.add_argument("--slug", required=True)
bundle.add_argument("--audience", choices=("developer", "easy", "both"), default="both")
bundle.add_argument("--repo-root", default="."); bundle.add_argument("--easy-output")
bundle.add_argument("--write", action="store_true"); bundle.add_argument("--overwrite", action="store_true")
bundle.add_argument("--ai-provider", choices=("openai",)); bundle.add_argument("--model")
```

Validate option combinations before reading credentials: `--overwrite` requires `--write`; provider and model must appear together; AI requires `--write`; `OPENAI_API_KEY` is read only inside the `openai` branch. Print JSON containing `dry_run`, planned paths, generated audiences, and whether AI was requested. Preserve all existing command branches verbatim.

- [ ] **Step 4: Run focused and full verification**

Run: `python3 -m pytest tests/test_cli.py -q && bash scripts/verify_toolkit.sh`

Expected: all CLI tests pass; full suite remains at or above 90% coverage; workflow security verification passes.

- [ ] **Step 5: Commit and open implementation PR**

```bash
git add src/pipeline_toolkit/cli.py tests/test_cli.py docs/reports/README.md
git commit -m "feat(report): add dual-audience report bundle command"
git push -u origin feature/56-report-bundle
```

Create a Korean PR to `develop` that references `Closes #56`, lists dry-run/write/AI safety behavior, includes verification output, and states that it does not automatically commit, push, or merge generated official reports.

## Plan Self-Review

| Spec requirement | Implementing task |
| --- | --- |
| One shared fact input | Task 1 |
| Deterministic dual drafts and prompts | Task 2 |
| `docs/reports` official and ignored `docs/reports/easy` local boundary | Task 3 |
| Explicit opt-in AI provider/model and key isolation | Task 4 |
| dry-run default, CLI, docs, backward compatibility | Task 5 |

The plan deliberately does not add a new third-party HTTP or template dependency. Every named interface is defined in an earlier task, and each task has a failing test, focused pass command, and independently reviewable commit.
