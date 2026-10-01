# Secret-free local metric and trace stack

Issue [Toolkit #119](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/119) provides a disposable development fixture for OTLP metrics and traces. Docker Compose runs Collector → Prometheus for metrics and Collector → Tempo for traces. Grafana provisions both datasources with metric exemplar → trace and trace → metric links. Dashboard delivery is tracked separately in #121.

Run commands from the Toolkit repository root. Prerequisites are Python 3.9+ and Docker with Compose v2 supporting `up --wait` (Docker Desktop on macOS/Windows or a Linux Docker engine). First startup downloads the pinned images and builds two small probe-enabled images; no cloud account, API key or environment secret is needed.

```bash
docker compose -f observability/local/compose.yaml config --quiet
docker compose -f observability/local/compose.yaml up --build -d --wait --wait-timeout 180
docker compose -f observability/local/compose.yaml ps
python3 scripts/local_observability_smoke.py --health-only
python3 scripts/local_observability_smoke.py
```

The health command checks Collector's health extension, Prometheus and Tempo readiness, Grafana's database, and the provisioned datasource links. Full smoke sends OTLP/HTTP JSON with one cumulative counter and one sampled trace. It waits for the counter value `1`, the fixture span queried by its fresh trace ID, and the matching Prometheus exemplar. Success prints JSON with `status: passed`, `trace_id`, and `trace_url`. HTTP 200 with OTLP rejected spans/data points, an empty query result or a missing exemplar is a failure. Nonzero exit status makes the tool suitable for optional integration CI.

`--timeout 60` controls the retry budget for each readiness/query phase. Individual HTTP requests have a three-second timeout. `--collector`, `--otlp`, `--prometheus`, `--tempo`, and `--grafana` accept localhost HTTP origins when testing a Compose port override; remote destinations and credential-bearing URLs are rejected. The fixture uses a constant service name and fresh trace IDs in exemplars/spans, rather than high-cardinality metric labels.

## Ports and Grafana queries

Every published port binds to `127.0.0.1`. Receiver addresses `0.0.0.0` inside containers allow Compose services to communicate; they do not publish an external host listener. Tempo's OTLP ports and Collector's Prometheus exporter port are available only on the Compose network.

| Host port | Endpoint | Purpose |
| --- | --- | --- |
| 4317 | `127.0.0.1:4317` | Collector OTLP/gRPC |
| 4318 | `http://127.0.0.1:4318/v1/metrics`, `/v1/traces` | Collector OTLP/HTTP |
| 13133 | `http://127.0.0.1:13133/` | Collector health |
| 9090 | `http://127.0.0.1:9090` | Prometheus query UI/API; `/-/ready` |
| 3200 | `http://127.0.0.1:3200` | Tempo query API; `/ready` |
| 3000 | `http://127.0.0.1:3000` | Grafana; `/api/health` |

Open Grafana and select Explore → **Local Prometheus** (`local-prometheus`), then query `toolkit_local_fixture_total`. The counter includes a `service_name="toolkit-local-fixture"` label. Enable exemplars in the graph query to follow the exemplar's `trace_id` to **Local Tempo** (`local-tempo`). In Tempo, query the trace ID printed by smoke; its span is `local-stack-fixture`. The trace-to-metrics link queries the same metric using the trace's `service.name` mapped to `service_name`.

Grafana uses anonymous **Editor** access so Explore is available in current OSS Grafana, hides its login form, disables basic authentication and skips initial admin creation. Local users can query and create/edit disposable dashboards. Provisioned datasources are read-only and datasource administration requires Admin; no credentials are configured in them. This fixture is intended for local development data and should be reachable only from the development machine. A production deployment requires its own authenticated services and storage design.

API queries can also be run directly (replace the trace ID with the smoke output):

```bash
curl --fail --get 'http://127.0.0.1:9090/api/v1/query' --data-urlencode 'query=toolkit_local_fixture_total'
curl --fail 'http://127.0.0.1:3200/api/traces/TRACE_ID_FROM_SMOKE'
curl --fail 'http://127.0.0.1:3000/api/datasources/uid/local-prometheus'
curl --fail 'http://127.0.0.1:3000/api/datasources/uid/local-tempo'
```

## Resource limits and lifecycle

Pinned upstream images are Collector Contrib `0.162.0`, Prometheus `v3.15.0`, Tempo `2.10.8`, Grafana `13.2.3`, and BusyBox `1.37.0-musl`. Collector's upstream release publishes architecture-specific tags, so BuildKit selects `0.162.0-arm64` or `0.162.0-amd64` using `TARGETARCH`. Tempo uses the maintained 2.10 patch line with its single-binary ingester/compactor configuration. Collector and Tempo use local Dockerfiles that copy a static BusyBox binary into the upstream image so their healthchecks can execute an actual HTTP probe. Image/configuration updates must repeat Compose startup and signal/query smoke checks.

| Service | Container memory cap | Data volume | Storage / retention bounds |
| --- | --- | --- | --- |
| Collector | 256 MiB | None | Memory limiter 192 MiB; bounded 256-batch trace queue; exporter drops stale metric series after 5 minutes |
| Prometheus | 256 MiB | `prometheus-data` | 256 MiB tmpfs; TSDB retention 1 hour or 128 MB, whichever triggers first |
| Tempo | 384 MiB | `tempo-data` | 256 MiB tmpfs for WAL and blocks; block retention 1 hour, compacted blocks 5 minutes |
| Grafana | 256 MiB | `grafana-data` | 64 MiB tmpfs for disposable SQLite/UI state |

Compose prefixes volume names with project `toolkit-local-observability`. All three use the Linux `local` driver with `type=tmpfs`, an explicit size cap and mode `1777` so upstream non-root users can write. These are memory-backed disposable volumes, including on Docker Desktop's Linux VM. Their contents can disappear when unmounted during stop/recreate; there is no durability promise. Together they allow at most 576 MiB of mounted data storage, plus process memory and bounded Docker logs (two 5 MB files per service). Container memory limits also account for tmpfs usage, so filling a volume may reach the memory cap first.

Prometheus retention is asynchronous and its limit excludes WAL/head overhead; the tmpfs cap also bounds that overhead. Tempo retention is applied to completed blocks and is not a precise trace expiry timer. Tempo additionally limits ingest to 1 MiB/s with a 2 MiB burst, 1,000 active traces and 1 MiB per trace. These limits make this a small fixture stack; sustained ingestion can exhaust the capped storage or cause rejection before retention runs. Stop/clean/restart the fixture when testing retention or recovering from a full volume. Full smoke tests are safe to repeat; fixture metric series expire from Collector after five minutes without a new send, while historical samples remain until Prometheus retention runs.

Stop/remove the project's containers and network:

```bash
docker compose -f observability/local/compose.yaml down
```

Explicitly clean all **three local fixture volumes**:

```bash
docker compose -f observability/local/compose.yaml down --volumes
```

This deletes the project's metric history, trace WAL/blocks and Grafana UI state. It cannot be recovered. Repository configuration files and unrelated Docker projects are unaffected. Images/build cache are retained for faster startup. Do not use global Docker pruning for this cleanup.

For unhealthy services or smoke failures:

```bash
docker compose -f observability/local/compose.yaml ps -a
docker compose -f observability/local/compose.yaml logs --tail=100 collector prometheus tempo grafana
```

The Collector probe confirms its health extension is listening; downstream delivery is proven by full smoke. Startup `--wait` fails if a service cannot start or pass its readiness probe. Resolve host port collisions before starting another instance. A volume-full or ingestion-limit failure should be diagnosed from logs and handled with scoped fixture cleanup. First startup on a slow network may need a longer `--wait-timeout` after images are downloaded.

## Verification without Docker

```bash
python3 -m pytest -q tests/test_local_observability.py
bash scripts/verify_toolkit.sh
```

The canonical Toolkit verification discovers the configuration, OTLP payload, HTTP query, partial-success and localhost-only contracts automatically. It does not start Docker or contact cloud services. A separate opt-in integration job should run Compose `config`, startup with `--wait`, both smoke commands, and scoped `down --volumes` in its cleanup/finally step. A skipped Docker integration check is not evidence of live health or signal delivery.

Configuration references: [Collector Prometheus exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.162.0/exporter/prometheusexporter/README.md), [Tempo v2.10 configuration](https://grafana.com/docs/tempo/v2.10.x/configuration/), [Grafana datasource provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/), and [Prometheus storage retention](https://prometheus.io/docs/prometheus/latest/storage/).
