# changelog.md

Lightweight human-readable summary of meaningful repository changes.

## [0.1.3](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/compare/v0.1.2...v0.1.3) (2026-10-02)


### Features

* add shard benchmark monitoring evidence ([#112](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/112)) ([4acc0c4](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/4acc0c41bf138c75836935bca90599c59f1d3bac))
* **cli:** orchestrate pipeline benchmark experiments ([#122](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/122)) ([3cca2e3](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/3cca2e3e38968e54e542327a99e17f48584f603c))
* **observability:** add bounded local OTLP stack ([#119](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/119)) ([9a63e2f](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/9a63e2f5f6d95bd7ff2ba1f24d23d985ef216c42))
* **observability:** complete CI telemetry and experiment toolkit ([8b4e5b0](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/8b4e5b02696c21daae6939f24bbc39c91fb4029c))
* **reporting:** provision CI dashboard and query contracts ([#121](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/121)) ([f094fb4](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/f094fb453851e36088031be4b40b8c4ddd13e9c2))
* **telemetry:** add Actions evidence and observability plan ([#123](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/123)) ([0f2be2c](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/0f2be2ce00a8ad2d9d06d3b569558c266b758908))
* **telemetry:** complete Actions attempt evidence and diagnostics ([#118](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/118)) ([6487aeb](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/6487aeb21af8f38621963d77b0c9425f0364d992))
* **telemetry:** export bounded Actions OTLP evidence ([#120](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/120)) ([c23aab8](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/c23aab8a053830050d881816addb6fc0794a8849))
* **telemetry:** normalize Actions timeline evidence ([e726283](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/e7262835c3d5143029c565e73d1f9e5b59c39326))


### Bug Fixes

* **benchmark:** require three valid release runs ([#117](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/117)) ([db3de78](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/db3de78cc0bd46fed0f8384019e27ed59cc2ab08))
* **ci:** benchmark 실행 간 concurrency 격리 ([d84998a](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/d84998a62dc68370af63ee19cdd9d3f67dd22cf0))
* **ci:** benchmark 실행 간 concurrency 격리 ([eca8ec9](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/eca8ec9ea2fef9194a07ab65aaa8758692ac9f18))
* **cli:** harden experiment links and outcome policy ([#122](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/122)) ([f4b5ed8](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/f4b5ed858fa84089875fc605e681cdfb14799ed6))
* **experiments:** bound collection and verify source scope ([#122](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/122), [#115](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/115)) ([dbbe945](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/dbbe9456b7140e9fa7ac725678665d99df031c63))
* **experiments:** validate streaming ZIP descriptors ([#122](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/122), [#115](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/115)) ([178c503](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/178c503a26490dd59ba0130a974c4bfbcaf43d32))
* **observability:** pin image digests and restrict smoke transport ([#119](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/119)) ([e7e49f0](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/e7e49f0567408ad2ac5ed26560650483cc3e7141))
* **reporting:** observe Collector export failures and queue pressure ([#121](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/121)) ([bb4f42b](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/bb4f42b45745652b9d3a499fb8efea707a844d41))
* **telemetry:** avoid Prometheus job label collision ([#120](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/120)) ([27b02f0](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/27b02f02af8c846b950290f3a5eaa3fa060be2f5))
* **telemetry:** preserve module failures and secure run links ([#115](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/115)) ([ee7e0f9](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/ee7e0f99ca7605349e7b6ec48052de1f8805ae39))
* **telemetry:** resume OTLP batches after partial acceptance ([#120](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/120)) ([c6165f1](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/c6165f1b127fd3f3998d4a3301de44cff3a13495))
* **telemetry:** validate aggregate coverage and show module failures ([#118](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/118)) ([d1efe50](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/d1efe50684d612926b4e8c1f7fcdbee68b6af102))

## [0.1.2](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/compare/v0.1.1...v0.1.2) (2026-09-25)


### Bug Fixes

* **github:** module benchmark output 줄바꿈 수정 ([1bb9110](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/1bb9110a7bd7d7aecfef50c66519e21c119a01e8))
* **github:** module benchmark output 줄바꿈 수정 ([bb0f74b](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/bb0f74bff18c934bf79cc393e2e7584397f829c6))

## [0.1.1](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/compare/v0.1.0...v0.1.1) (2026-09-25)


### Features

* add deterministic benchmark report outputs ([#15](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/15)) ([3205bfb](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/3205bfbe3594eda01c46bdecdabab24a28ce6f42))
* add installable toolkit CLI and runtime image ([bf6f559](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/bf6f55933940d4954729ced7e0b74ca31c7935ff))
* add low-cardinality telemetry contract ([3ffc13c](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/3ffc13c4fd8b46c30e58ecd0d13881186408aafe))
* add release and deployment identity contracts ([2625989](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/26259892e1b59960c1eaf5421afa6a1fdc19eb3a))
* add release comparison statistics policy ([eb288e4](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/eb288e41401404172fd183f9dfe7505f0cec7cf6))
* add secure workflow adoption contract ([#14](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/14)) ([2bf8e5e](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/2bf8e5e00c263d6e5faa748da4976545ae83bcd0))
* **cli:** add catalog module plan command ([#42](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/42)) ([add61b2](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/add61b2aa0dff33052a53b2ba40911b163ed10f9))
* complete benchmark collectors ([7722f7d](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/7722f7d95044edbbf5323439a1406c4fd95b638b))
* **contracts:** add module benchmark evidence manifest ([#41](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/41)) ([55e1381](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/55e1381835d708a850f26992778d6c0899a57024))
* **core:** add module catalog execution planner ([86cb93e](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/86cb93eb82b3206e7f8531a06ac9a2f60c8ba780))
* **core:** add release trend manifest contracts ([#69](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/69)) ([4a89bdd](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/4a89bddc8b89189f5a233e794000bd99d68f1216))
* **core:** select comparable release baselines ([#70](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/70)) ([72c077f](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/72c077fba51c887229c352a3663ef4a960469eb1))
* extend collectors dag comparison and report provenance ([#13](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/13)) ([a2178c6](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/a2178c6a6d1a9ae1d3e4aec1cd6e404bef8b2af6))
* **github:** add release trend cli workflow contract ([#72](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/72)) ([a3c4f05](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/a3c4f05308867677616c15417ffa52f465ac765d))
* **github:** add reusable module benchmark workflow ([#47](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/47)) ([d8d67b3](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/d8d67b3102164e0fa340322bef1d3f1d9b081153))
* **github:** materialize release trend evidence ([#79](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/79)) ([dd2b79d](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/dd2b79db9b737585836547bde2b3bae3fdeed439))
* implement release-aware benchmark toolkit foundation ([#12](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/12)) ([981ca95](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/981ca9560c1197b6cf9b4403018314f7a68efe66))
* **reporting:** add restricted recommendation payloads ([#46](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/46)) ([41c4d62](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/41c4d6223a9582001020e7bcdeba36e17667631f))
* **reporting:** compare module benchmark evidence ([#43](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/43)) ([a444e22](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/a444e22809b7917ab36cd3367cba83a8b3542b1c))
* **reporting:** render release trend evidence ([#71](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/71)) ([c247edd](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/c247edd5af361a28b4db570eb700bda6a734dec1))
* **report:** 이중 독자 보고서 번들을 구현한다 ([#58](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/58)) ([f3b85c3](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/f3b85c31180fb9f5e1309d5283849c9c7b5710f6))
* separate workflow DAG timing metrics ([8814fb5](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/8814fb5a74fc0cd94e2986565faf2d2ae9a2844e))
* validate versioned evidence schemas ([463749f](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/463749f921de8b3343950d7ee236fbba186e8923))


### Bug Fixes

* **ci:** isolate module matrix concurrency by module ([#53](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/53)) ([53947d2](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/53947d2e2cdaf4ad8d48a4f99aaff84039ba4c40))
* **ci:** migrate toolkit repository name references ([#51](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/51)) ([cd4e32c](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/cd4e32c22020162c1a161346587b3abd0cdbde16))
* **contracts:** require evidence environment identity ([#45](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/45)) ([3334122](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/333412227698c9494ee63e0b707fdcf06fe6b08c))
* **core:** stabilize release trend history discovery ([#78](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/78)) ([e6978bb](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/e6978bb2819fff267c999ff632ea3ef894dc8f60))
* **github:** pin reusable checkout to caller toolkit ref ([#49](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/49)) ([6a46022](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/6a46022043998ca8c54e2d7d3fec2827eefc4538))
* **github:** run reusable benchmark for caller events ([#81](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/81)) ([56862ed](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/56862ed48797a13e4739b2fdfc2310a773a3a957))
* preserve command execution failure evidence ([bfbdb64](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/bfbdb64f13d678ec9205a96d2f9c04774c3dc7c4))
* **release:** bootstrap release please verification ([#88](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/issues/88)) ([009a9ad](https://github.com/YRootLab/OnMaru-backend-ci-toolkit/commit/009a9ad604526e84e188d1472f77b0a940659e77))

## 2026-09-23

- Initialized project harness operating files.
- Documented Git Flow branch and release policy.
- Added CI and Release Please automation scaffolding.
