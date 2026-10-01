# CI observations dashboard

[Toolkit #121](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/121) consumes the [local stack](local-stack.md) and [OTLP v1 contract](otlp-export.md). The source evidence manifest remains authoritative; no panel changes a required CI verdict.

## Import and reproduce

`observability/queries/ci-benchmark.json` is the canonical PromQL/TraceQL contract. `scripts/build_ci_dashboard.py` generates `observability/dashboards/ci-benchmark.json`; edit the contract/generator and regenerate, never hand-edit generated JSON. The test suite checks drift. Stable datasource UIDs are `local-prometheus` and `local-tempo`.

```sh
python3 scripts/build_ci_dashboard.py
python3 scripts/build_ci_dashboard.py --check
docker compose -f observability/local/compose.yaml config --quiet
docker compose -f observability/local/compose.yaml up -d --build --wait
PYTHONPATH=src python3 scripts/ci_dashboard_smoke.py --timeout 45
```

Open `http://127.0.0.1:3000/d/toolkit-ci-benchmark`. File provisioning imports it into **CI observations** and checks for definition updates every 30 seconds. The JSON also works with Grafana's import screen where these UIDs exist. Cloud UID changes must update panel targets and encoded Tempo Explore links together; this repository includes no Cloud credentials.

Grafana keeps the image's bundled plugins with `GF_PLUGINS_PREINSTALL_DISABLED=true` and `GF_PLUGINS_PREINSTALL_AUTO_UPDATE=false`. Analytics update flags alone do not stop Grafana 13's background plugin installer. An automatic update can fill the 64 MiB disposable volume and unregister Prometheus while Grafana health remains green.

The smoke exports contemporary **synthetic** success/failure manifests through the real #118 normalizer and #120 transformer/exporter. It verifies literal source timings (8s workflow window/job, 6s step/module), every PromQL query, both TraceQL searches, nonempty Grafana frames, real drilldown field names and replay suppression. It checks provisioning rather than assuming valid JSON means Grafana imported it. Synthetic run IDs are not real GitHub runs: the smoke checks destination construction without contacting GitHub or claiming real artifacts exist.

Clean up only this disposable project after inspection:

```sh
docker compose -f observability/local/compose.yaml down --volumes --remove-orphans
```

This removes the project's containers, network and three tmpfs volumes. Fixture telemetry is intentionally unrecoverable; a real manifest must have separate durable storage. Images and other projects remain intact.

## Query interpretation and drilldowns

There are no label-discovery or textbox variables. Metric scope is fixed to `workflow="ci"`, `environment="test"`; traces also filter the OnMaru repository. Job/step grouping uses `ci_job`, preserving Prometheus target labels `job`/`instance`. Catalog changes require series-budget and replay-plan review. Top-20 panels and limit-20 searches bound displayed results, not ingested cardinality.

| Panel family | Meaning and limitations |
| --- | --- |
| Workflow window | Histogram sum/count mean of observed first-to-last job window, by coverage quality; not workflow wall-clock, queue or critical path. |
| Job/step/module duration | Histogram sum/count mean by configured catalog. Missing timing stays absent. One catch-all bucket cannot support percentiles. |
| Work | Latest retained job/module gauges, kept separate; adding overlapping scopes double-counts work. |
| Outcomes | Observation-count gauge snapshot, not lifetime totals or run failure rate. Do not use rate, increase or sum over scrapes. |
| Collection quality | Evidence/artifact/job/step/module quality includes missing/invalid/partial/unavailable. No-data remains unknown. |
| Export failures/lag | Explicit visibility gaps. `ExportResult` and delivery timestamps are consumer-local and not exported by v1. Healthy scrape targets or fresh CI metrics cannot prove export success. |

Gauge label sets can retain values from different manifests until Collector's five-minute expiry; concurrent runs overwrite shared label sets. Backend histogram temporality, resets and replay affect snapshots. These graphs show exported observations, not exact per-run history. Use manifests/traces for individual values and the experiment comparator for three-sample decisions. The local 2s scrape is for fixtures, not a Cloud recommendation.

The two Tempo tables distinguish success from all non-success outcomes, including cancellation/skip/unknown that ERROR status alone misses. TraceQL selects run ID, attempt, digest and result. Overrides use actual Tempo frame fields `traceIdHidden` (explicitly made visible) and `cicd.pipeline.run.id`, not query-language `span.` prefixes. The fixed repository, digit-only run ID predicate and percent-encoded value keep URLs on the intended host/path; links do not interpolate source URL attributes.

**Tempo trace** opens that trace in Tempo. **Actions run** opens its source run. **Manifest artifacts** opens its `#artifacts` section: download retained evidence and check `toolkit.ci.manifest.digest` plus attempt. OTLP v1 provides a digest but no verified artifact ID; inventing an exact artifact-download URL would be misleading. Consumer #554/#555 must verify real success/failure retention and permissions. Untimed workflows have no synthetic workflow span and may be absent from tables. The trace schema lacks environment, so trace panels scope to repository/workflow only; do not claim test-only isolation if workflow labels are reused.

Queries follow [TraceQL's scoped-attribute/select contract](https://grafana.com/docs/tempo/latest/traceql/construct-traceql-queries/) and links follow [Grafana's data-link fields](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/configure-data-links/). Upgrade validation must include live frame names and drilldowns.

## Budgets and enforcement boundaries

Operational limits below are **rollout admission requirements**, not dashboard-enforced quotas. The consumer owner must enforce catalog/run budgets before Cloud export. Exporter/backend hard limits remain separate. Exceeding a limit must leave explicit local rejection/partial diagnostics, never silent truncation.

| Dimension | Operational budget and implementation bounds |
| --- | --- |
| Catalog | One workflow/environment, ≤16 configured CI jobs and ≤16 modules plus `other`; no identity/path/test/step-name metric labels. Producer hard caps are 256 jobs/modules and 64-character identifiers. |
| CI series | Admission cap 2,000 active series per workflow/environment, warning at 1,600. Conservative signal upper bound for 16+`other` catalogs is 1,682; reserve 318 for metadata/approved health signals. Count actual backend series before rollout. |
| Spans | Operational ≤16 jobs ×64 steps +16 job roots +1 workflow =1,041 spans/run. Transformer hard cap: 8,192 combined workflow/job/step/module observations; 256 jobs and 256 steps/job. No invented module spans. |
| Trace bytes/rate | Local Tempo: ≤1 MiB/trace, 1 MiB/s, 2 MiB burst, 1,000 active traces. Span counts do not guarantee byte bounds; check serialized trace/attribute size and retain rejection diagnostics. |
| Batch | Defaults: 128 points/spans, 1 MiB/request, 256 batches, 16 MiB/export. Configurable ceilings: 512 items, 4 MiB/request, 512 batches. Evidence input ≤16 MiB. |
| Time/retry | Default 3 attempts/request, 5s/request, 30s/export; configurable ceilings 5 attempts, 30s/request, 120s/export. No retry storms or automatic CI reruns. |
| Daily plan | ≤100 observed runs/day and ≤100 MiB/day serialized trace payload before compression. At span cap: ≤104,100 spans/day. Measure bytes; explicit experiments consume six runs plus orchestration. |
| Local retention | Prometheus 1h/128 MB TSDB in 256 MiB tmpfs; Tempo 1h blocks in 256 MiB tmpfs; Grafana 64 MiB tmpfs. WAL and delayed compaction still consume space. Container memory: Collector/Prometheus/Tempo/Grafana 256/256/384/256 MiB. |
| Cloud retention | Initial approved target ≤30 days metrics and ≤7 days traces, subject to purchased plan. Verify actual tenant defaults/overrides; this repo does not provision Cloud retention. Keep manifests independently for the audit/replay horizon. |
| Replay store | Default 100,000 identities, no automatic eviction. Retain beyond the replay window; deleting acknowledged identities re-enables delivery and needs explicit owner review. |
| Queries | Default last hour/30s refresh, 20 trace matches and one matching span/trace, top 20 catalog series. Expand ranges only for bounded investigations. |

Series calculation: each classic histogram label set has sum/count/+Inf bucket =3 series. Conservative duration bound is `18 + 3×17×6×3 =936`; work `2×6=12`; outcomes `8×(1+3×17)=416`; quality `2×6+3×17×6=318`; total **1,682**. Some enum combinations are narrower, providing headroom. At the producer's 256-entry maximum the same model gives **24,722**, exceeding this admission budget. Top-k queries do not solve that storage cost.

## Cloud Mimir/Tempo limits and cost checklist

Before rollout, record tenant/region, datasource UIDs, accepted metric naming and temporality, timestamp-age/out-of-order acceptance, active-series limits, ingestion rate/burst, label length/count, maximum trace bytes, query budgets and actual retention. Verify the same success/failure fixture through the chosen Cloud OTLP route. Cloud translation may add suffixes or change temporality; update and revalidate canonical queries if names differ. HTTP 200 alone does not establish backend retention.

[Cloud metric billing](https://grafana.com/docs/grafana-cloud/platform/pricing-and-usage/metrics/) considers active series and data points per minute. Record included DPM, contractual rates and month-to-date usage in the billing UI. At 2,000 series a 60s scrape yields 2,000 DPM; the local 2s interval yields 60,000 DPM. Post-run OTLP has a different delivery pattern. Review actual use at 50%, 80% and 100% of the owner's approved monthly cap; suspend optional export at the cap while retaining evidence.

Use [Cloud trace pricing/usage](https://grafana.com/docs/grafana-cloud/platform/pricing-and-usage/traces/) and tenant billing to confirm ingestion, retention, sampling and allowance. Measure accepted/dropped spans and bytes rather than estimating from span count alone. No fixed dollar rate or universally available tenant limit is assumed. The consumer owner must supply the numerical monthly spend cap and escalation destination before Cloud transmission.

## Alerts, outages and replay

Initial consumer-local warning thresholds: failed/partial export, pending batches older than 15m, source-completion-to-ack lag above 15m, and invalid/missing artifacts. Review thresholds against CI duration. The dashboard does not deploy alerts for nonexistent metrics. A future independent health adapter must use finite workflow/environment/status/reason labels, fit the series budget and preserve diagnostics when the destination is down. Backend absence may be monitored separately, but idle periods with no CI runs are normal.

On failure retain manifest/digest, persisted collection time, `ExportResult` and SQLite replay state. CI conclusion remains unchanged. Diagnose authentication, rate/size limits, timestamp retention, query mismatch and partial acceptance independently. Do not mark missing telemetry green or rerun benchmarks automatically. Local lag is acknowledgement minus source completion; absent completion/ack means unknown/pending, not zero and not scrape age.

Recover by replaying the same manifest, observation time and destination/checkpoints under bounded retries. Acknowledged batches remain suppressed; terminal partial batches are not resent blindly; unrelated pending batches can resume. Lost acknowledgements can duplicate accepted data, so this is not exactly-once accounting. Label/catalog/batch changes may produce `replay_plan_mismatch`; review migration instead of deleting state. Backends can reject old source timestamps; retain local evidence and disclose that gap rather than replacing timestamps with now.
