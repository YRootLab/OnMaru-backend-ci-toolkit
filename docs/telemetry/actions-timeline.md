# CI Actions timeline evidence v1

Related: [Toolkit #115](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/115), [ADR-0005](../decisions/0005-consumer-owned-ci-observability.md).

`normalize_actions_timeline(run, jobs_response)` accepts one GitHub Actions run API response and a fully paginated workflow-jobs response. OnMaruBE collects these responses after the run; Toolkit only normalizes them. The output identifies `run.id` and `run.attempt`, preserves job and step conclusions, and records each duration with `available`, `unavailable`, or `invalid` quality. Incomplete job pagination is marked `partial_jobs`; duplicate IDs and excessive collections are rejected. The consumer should retain the original Actions run URL and artifact as the diagnostic source.

`observed_job_window_seconds` spans the first observed job start through the last observed job completion. `sum_job_work_seconds` adds completed job durations. Neither is the workflow elapsed time. The Actions run `updated_at` field is not treated as a precise completion timestamp. Workflow elapsed time, runner queue time, and the dependency DAG critical path remain `unavailable` until trustworthy source timestamps and graph edges are collected. The existing module command maximum must not be relabeled as the DAG critical path.

This module is the first local evidence contract. It does not fetch pages, upload artifacts, export OTLP, or create a Grafana dashboard. The consumer post-run workflow, credential isolation, replay/deduplication, and staging success/failure verification remain in #115.
