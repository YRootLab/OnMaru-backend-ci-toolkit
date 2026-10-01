# Actions evidence to OTLP v1

Related: [Toolkit #120](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/120), [Actions evidence v1](actions-timeline.md), [observability policy](../reports/2026-10-01-ci-benchmark-observability-policy.md).

The optional consumer post-run process transforms a persisted Actions evidence manifest into metrics and reconstructed traces. It runs no tests, executes no artifact content and changes no required CI verdict. The original manifest and Actions diagnostics remain authoritative. The existing `TelemetryEvent` API remains compatible.

```python
from pipeline_toolkit.telemetry import (
    MetricPolicy, transform_actions_evidence,
    ExportConfig, SQLiteReplayStore, export_otlp,
)

# Read evidence and collection_time_ns from the consumer's persisted collection.
# These labels come from trusted consumer configuration, not names in PR content.
policy = MetricPolicy(
    workflow="ci", environment="test",
    jobs={701: "api", 702: "worker"}, modules=("api", "worker"),
)
bundle = transform_actions_evidence(evidence, policy, observed_at_ns=collection_time_ns)
store = SQLiteReplayStore("consumer-state/otlp-replay.sqlite")  # parent must exist
delivery = export_otlp(bundle, ExportConfig("http://127.0.0.1:4318"), store)
# Persist delivery as observability status; do not substitute it for verify.
assert delivery.ci_conclusion == evidence["run"]["conclusion"]
```

Validate configuration and open the replay store within the consumer's optional-observation error boundary: invalid configuration, invalid evidence and store initialization errors raise before export. Once called, `export_otlp` returns transport/checkpoint failures as an `ExportResult`. This is a bounded synchronous operation, not a background service. Its `status` is `exported`, `duplicate`, `busy`, `partial` or `failed`; `reason` is a bounded machine code. Response bodies, credentials and exception messages are never returned. Successful delivery does not imply a successful CI run, and failed delivery does not replace the original `ci_conclusion`.

## Source checks and identity

The transformer requires schema version 1, repository, run ID, attempt and the manifest's SHA-256 `evidence_digest`. It recomputes the canonical digest, checks collection bounds, unique job/step/module identities, module-to-job references and duration/window/work consistency. A digest detects content changes; it is not an authenticity signature. Consumers still own provenance, download/archive validation and access control.

Identity is SHA-256 of the repository, run ID, attempt and manifest digest tuple. Trace and span IDs are deterministically derived from that identity and the workflow/job/step key. Reruns and corrected manifests produce distinct identities. Retry bodies, trace IDs and span IDs remain byte-identical. Evidence is capped at 16 MiB, 256 jobs, 256 steps per job, 256 modules and 8,192 combined observations before export.

Trace attributes carry `vcs.repository.name`, `vcs.ref.head.revision` when present, `cicd.pipeline.run.id`, `toolkit.ci.run.attempt`, `toolkit.ci.manifest.digest`, Toolkit ref and the original safe HTTPS run URL. Individual job/step links are derived from that run URL and numeric source identifiers. Credential-bearing or malformed links are omitted. Metric resources contain only the fixed `service.name=onmaru-ci`; they do not contain run identity.

## Metrics and label policy

The metric-key allowlist is `workflow`, `environment`, `job`, `module`, `scope`, `outcome`, `quality`. `MetricPolicy` limits workflow/environment identifiers to 64 characters and each explicit job/module catalog to 256 entries. Unmapped jobs/modules use `other`. Step names, arbitrary job names, paths, URLs, repository, run ID, SHA and digest never become metric labels. Catalog configuration must remain stable across runs; the caller supplies it from trusted workflow configuration, not artifact fields. Fixed outcome and quality enums prevent untrusted result strings from creating series.

| Metric | Unit/type | Source and missing-data behavior |
| --- | --- | --- |
| `toolkit_ci_workflow_observed_window_seconds` | seconds, delta histogram | Source observed job window; includes its partial/available quality. Not workflow wall-clock. |
| `toolkit_ci_job_duration_seconds` | seconds, delta histogram | Valid source job durations; unavailable/invalid intervals omitted. |
| `toolkit_ci_step_duration_seconds` | seconds, delta histogram | Valid source step durations, grouped by configured job; no step-name labels. |
| `toolkit_ci_module_duration_seconds` | seconds, delta histogram | Complete module command durations only; no invented module span. |
| `toolkit_ci_work_seconds` | seconds, gauge | Source sum of valid job work, or sum of complete module durations; partial coverage is labeled. All-missing work is omitted. |
| `toolkit_ci_outcome` | count, gauge | Observation count grouped by workflow/job/step/module and bounded outcome. This is not a cumulative counter. |
| `toolkit_ci_collection_quality` | count, gauge | Evidence/artifact quality and job/step/module timing completeness. Missing artifacts still emit quality. |

Multiple samples in the same label set form one histogram point. Histograms preserve count, sum, min and max with a single catch-all bucket; v1 does not support bucket-derived quantiles. Outcome/quality gauges count observations in this manifest and must not be interpreted as lifetime totals. Consumers must retain the manifest when individual samples matter.

Metric timestamps use the observed window's source completion when available. Histogram start time uses the observed window's source start. With no valid job window, metric observation time is the supplied persisted `observed_at_ns`; histogram start remains absent. Reuse this timestamp during replay. Changing it for an otherwise identical all-untimed manifest changes the payload plan and is rejected by the replay store. Unavailable workflow wall-clock, queue and DAG critical path never receive a numeric metric.

## Reconstructed traces

The source's valid `started_at`/`completed_at` instants are converted to integer Unix nanoseconds without float conversion. Timestamp timezone offsets are respected and retained fractional precision is not rounded to the duration metric's millisecond precision. An invalid/missing interval produces a quality issue and no span. A valid step whose job interval is unavailable remains an unparented span; no synthetic job is inserted.

The workflow span spans only the first through last valid source job interval and is explicitly marked `toolkit.ci.timing=observed_job_window` and `toolkit.ci.reconstructed=true`. It is not exact workflow duration or a dependency graph. Jobs and steps form observation hierarchy, not propagated application trace context. Module artifacts have duration but lack normalized command timestamps, so v1 exports module metrics without inventing module spans.

The mapping follows the [OpenTelemetry CI/CD span conventions](https://opentelemetry.io/docs/specs/semconv/cicd/cicd-spans/) reviewed against semantic conventions 1.44.0: workflow kind SERVER, task kind INTERNAL; pipeline/task result attributes; task names/IDs/links. Source `cancelled`, `timed_out`, `skipped` become `cancellation`, `timeout`, `skip`. Failures/timeouts/system errors have ERROR status and bounded `error.type`; successful spans have OK; cancellation/skip/unknown retain UNSET. `toolkit.ci.source_conclusion` retains the source conclusion. The conventions are release candidate; future changes require an explicit mapping-contract revision.

## Transport limits and response handling

Serialization uses [OTLP/HTTP JSON](https://opentelemetry.io/docs/specs/otlp/): POST `/v1/metrics` and `/v1/traces`, JSON content type, lower-camel-case protobuf fields, decimal strings for 64-bit integers, integer enums and hex trace/span IDs. `ExportConfig.endpoint` is the base URL, optionally including a prefix such as `/otlp`. HTTPS is required except for `localhost`, `127.0.0.1`, and `::1`. URL credentials, query and fragment are rejected. The stdlib transport validates TLS, follows no redirects and uses no environment proxy configuration. Authentication headers are consumer-supplied and excluded from representations and checkpoints.

Defaults are 128 points/spans per batch, 1 MiB/request, 256 batches, 16 MiB total, a 64 KiB response cap, 5-second request timeout, 30-second export budget, 3 attempts and 0.25-second exponential backoff with injected jitter capped at 5 seconds. Every batch is built and checked before the first request. Maximum configurable bounds are 512 items, 4 MiB/request, 512 batches, 30-second request timeout, 120-second export budget and 5 attempts. A single oversized item fails before transport; no silent truncation occurs.

Retry only connection/socket failures and HTTP 429/502/503/504. Other HTTP errors, malformed acknowledgements and receiver partial rejection are not retried. `Retry-After` seconds or HTTP dates are respected; a delay outside the remaining/configured budget stops delivery instead of shortening the server's requested delay. Body reads use the remaining request deadline, preventing trickling responses from resetting the timeout indefinitely. Standard-library DNS/header parsing is governed by OS and socket behavior, so the budget is not a process-kill hard deadline. Injected transports must honor their supplied timeout. The transport, sleep, monotonic clock and jitter functions are injectable for deterministic verification.

## Replay and failure boundaries

`SQLiteReplayStore` is consumer-owned durable state. Retain it between post-run processes and restore it before replay. It keys each destination by evidence identity and endpoint; it stores hashes, a payload-plan digest, lease ownership and per-batch acknowledgement states. No source JSON, URLs or credentials are stored. Concurrent exports sharing the database see `busy`. A process lost before releasing its lease can resume after the configured export budget plus 5 seconds; already acknowledged batches remain suppressed.

An HTTP full-success acknowledgement checkpoints that exact batch. If metrics succeed and traces fail, retry sends only the unacknowledged traces. A receiver partial rejection is terminal for that batch because retrying it can recount its accepted subset. Other metric and trace batches continue in the same call. Partial checkpoints survive interruption: replay skips them and resumes any remaining batches, including legacy export-level partial records. After all batches reach accepted or terminal-partial state, replay makes no network requests. Any terminal-partial batch keeps the aggregate result `partial`; a later failure retains its own `reason` so operators can distinguish a completed partial export from pending delivery.

`request_attempts` counts HTTP attempts in the current call, including retries; `attempted_batches` counts distinct batches sent in that call. `total_batches` is the full plan size. `acknowledged_batches` (also exposed as `succeeded_batches`) and `terminal_partial_batches` include durable checkpoints from previous calls. `pending_batches` is total minus succeeded minus terminal-partial. These counters distinguish partial rejection from unrelated unsent data and remain accurate on completed replay. Changing batch partition, label policy or serialization for an existing identity fails as `replay_plan_mismatch`; review such migrations explicitly. The store defaults to 100,000 export identities and fails closed when full; retention/removal is consumer-owned, with no automatic eviction of replay protection.

This is acknowledgement-based replay suppression, not exactly-once delivery. The receiver may accept a request whose acknowledgement is lost; retry can duplicate it. Separate stores also cannot coordinate. Source manifest/digest remains the deduplication authority, and downstream retention and histogram aggregation semantics still matter. A changed manifest intentionally creates new evidence identity; v1 does not retract old observations automatically.

## Verification status

Tests use the #118 failed/cancelled/missing fixture and cross-check literal source timestamps, durations and outcomes. They exercise digest/identity inconsistencies, forbidden labels, incomplete evidence, batch/byte bounds, durable restart, concurrent replay, partial receiver rejection, timeout/retry/deadline behavior, malformed acknowledgement and an actual local HTTP receiver (including a trickling response). `bash scripts/verify_toolkit.sh` covers Python 3.9 compatibility and the repository suite.

This branch does not include #119's local stack. Collector, Prometheus and Tempo cross-checks are performed after integration with that branch; passing the lightweight HTTP fixture alone is not evidence of backend ingestion or a deployed dashboard. Consumer workflow triggers, credentials and dashboard UI remain outside #120.
