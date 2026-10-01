# CI Actions timeline evidence v1

Related: [Toolkit #118](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/118), [Root #115](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/115), [ADR-0005](../decisions/0005-consumer-owned-ci-observability.md).

Optional post-run transformation and delivery are documented in [Actions-to-OTLP v1](otlp-export.md). This evidence contract remains independent of exporter availability.

`collect_attempt_jobs(repository, run_id, attempt, fetch_page)` in `pipeline_toolkit.github.responses` collects the explicit `/repos/{owner}/{repo}/actions/runs/{id}/attempts/{attempt}/jobs` endpoint with `per_page=100`. The consumer supplies an authenticated callback that returns decoded JSON for each relative path. No credentials, checkout, execution, or network transport are owned by Toolkit. It collects more than 100 jobs without switching to the latest attempt. An empty later page returns partial evidence; duplicate IDs, changed totals, mismatched attempts, malformed responses and excessive collections fail closed. Transport exceptions propagate, so permission/rate-limit failures cannot appear as successful empty runs. Use the corresponding attempt-specific run response when inspecting a rerun.

`normalize_actions_timeline(run, jobs_response, *, toolkit_ref=None, module_artifacts=None, expected_modules=None)` preserves job and step conclusions and timing quality. Jobs are sorted by ID and steps by number; duplicates are rejected. Timestamp reversal, timezone-less and malformed timestamps have `invalid` duration quality; missing timestamps have `unavailable` quality. Observed windows compare timezone-aware instants. API inputs are capped at 256 jobs, 256 steps per job and 4,096 characters per retained text field. Short pagination is marked `partial_jobs`.

## Module artifacts and consumer boundary

The reusable module workflow publishes versioned `execution.json` with run ID, attempt, Toolkit SHA, module ID, exit code, duration and completeness. The [module JSON schema](../../schemas/actions-module-1.0.json) documents this envelope. Artifacts are supplied as objects with positive integer `id` and raw JSON `data` bytes. Optional `digest` is `sha256:<64 lowercase hex characters>` over the **JSON member bytes**, not the GitHub artifact ZIP digest. The consumer verifies any ZIP/download digest before selecting the member and enforces archive download, decompression and member limits. Toolkit does not extract archives or interpret paths, commands, logs or artifact names.

An immutable lowercase 40-character `toolkit_ref` is required for module joins. `expected_modules` maps module IDs to numeric job IDs in this attempt, for example `{"api": 701, "worker": 702}`. The map comes from the consumer's executed matrix and collected jobs; Toolkit never infers a job from a fuzzy name. The optional envelope `job_id` must agree with that map; when absent (as in the reusable producer), the explicit map supplies it. Without either a numeric job ID or a map, a member cannot join. Run, attempt, Toolkit ref and observed job must agree. Older unversioned artifacts lack trustworthy attempt identity and are invalid rather than silently upgraded.

Each JSON member is capped at 1 MiB, aggregate member bytes at 16 MiB and artifact count at 256. Duplicate JSON keys, invalid UTF-8/JSON, unsupported schema versions, identity mismatches, nonfinite/negative/greater-than-one-year durations and incorrect member digests are quarantined. Unknown producer fields such as `command` are discarded. Duplicate artifact IDs or module IDs quarantine all ambiguous candidates instead of choosing by arrival order. Failed execution evidence can be complete; result and evidence completeness are separate concerns.

`artifact_quality.status` is `complete`, `missing`, `invalid`, `partial` or `unavailable`. No members for expected modules is `missing`; all rejected members is `invalid`; a mix of valid and missing/rejected/incomplete members is `partial`. Missing modules and invalid members also appear in top-level `quality.issues`. Omitting module collection leaves artifact quality `unavailable`, preserving the jobs-only API. Passing an empty list with the expected map explicitly reports missing evidence.

Every bounded member receives a computed content digest. Top-level `identity` includes repository, head SHA, run ID, attempt and Toolkit ref. `evidence_digest` is SHA-256 over normalized evidence before inserting the digest itself: UTF-8 JSON, sorted keys, compact separators, no nonfinite values and deterministic job/step/module/artifact ordering. It provides replay identity, not an authenticity signature. Page/artifact order does not change it; reruns, contents and quality do. Over-limit rejected payloads are not hashed or retained.

## Diagnostic artifact

`render_actions_diagnostics(evidence)` in `pipeline_toolkit.reports.diagnostics` returns deterministic Markdown. The consumer writes/uploads it with normalized JSON in its own repository. It includes failed/cancelled jobs and steps, every module's ID, associated job, execution status, completeness and exit code, timestamp quality, evidence/artifact issues, Toolkit ref, digest and the original run URL when canonical. Module failure remains visible even when the associated job and its steps report success. Names are escaped and credential-like text redacted. Source URLs must exactly match `https://github.com/{owner}/{repository}/actions/runs/{run_id}` with the evidence's numeric run ID; userinfo, ports, query/fragment, controls, escapes, dot segments and other origins/paths are omitted as unavailable, without echoing their contents. GitHub Enterprise URLs need a separately reviewed origin contract. Rendering does not execute content or fetch links. Consumers should retain transport/collection exceptions as explicit errors instead of fabricating empty job responses.

```python
from pathlib import Path
from pipeline_toolkit.github.responses import collect_attempt_jobs
from pipeline_toolkit.telemetry.timeline import normalize_actions_timeline
from pipeline_toolkit.reports.diagnostics import render_actions_diagnostics

# fetch_page and downloaded_members are consumer-owned, bounded inputs.
jobs = collect_attempt_jobs(repository, run["id"], run["run_attempt"], fetch_page)
evidence = normalize_actions_timeline(
    run, jobs, toolkit_ref=toolkit_sha,
    module_artifacts=downloaded_members, expected_modules=executed_module_jobs,
)
Path("actions-diagnostics.md").write_text(render_actions_diagnostics(evidence), encoding="utf-8")
```

## Timing and output migration

`observed_job_window_seconds` spans observed job execution timestamps; `sum_job_work_seconds` adds valid job durations. Neither is exact workflow elapsed time. `updated_at` is not a guaranteed completion timestamp. Workflow wall-clock, runner queue and DAG critical path remain `unavailable` until trustworthy timestamps and dependency edges exist. `longest_module_duration_seconds` measures the longest complete module command and has `partial` quality when module coverage is incomplete; unavailable modules are not replaced by zero.

The reusable workflow returns `longest_module_duration_seconds` and `dag_critical_path_quality=unavailable`. Legacy `critical_path_seconds` remains declared for expression compatibility but is **empty**, and its manifest value is `null`. Its workflow wall-clock is also unavailable: the aggregate job cannot observe final workflow completion, and its own rendering time is not substituted for completion. The summary identifies the longest module and marks DAG critical path unavailable. Consumers previously coercing the legacy output to a number must migrate to the module duration output and check availability before conversion. Existing pinned commits keep historical behavior.

Aggregate uses the detect job's executed matrix as expected module coverage, not just the received file count. Every versioned execution must match the current run ID, attempt and Toolkit ref and name an expected module. Unknown matrix coverage, invalid/bounded members, stale attempts, foreign runs and duplicate modules are explicit quality issues; ambiguous members are excluded from timings. Missing expected modules make retained timings partial, and no valid timings means longest duration is unavailable. `sum_work_quality` is complete only when the entire expected matrix has valid complete durations. Aggregate publishes the quality issues alongside its report and manifest.

Verification covers a synthetic 205-job pagination scenario, a failed/cancelled/rerun fixture, producer-to-normalizer integration and invalid/oversized/digest/duplicate inputs. Read-only normalization of OnMaruBE run `36822854010`, attempt 1, found 19 jobs and 110 steps with complete timing quality and a 712-second observed window. Raw consumer responses are not committed. OTLP, credential isolation and consumer post-run workflow wiring remain in other #115 workstreams.
