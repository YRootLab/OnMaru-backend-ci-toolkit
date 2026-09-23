# OnMaru-backend adoption contract

The consumer repository passes immutable release identity into the reusable workflow:

```yaml
jobs:
  benchmark:
    uses: YRootLab/OnMaru-modular-backend-pipeline-toolkit/.github/workflows/reusable-benchmark.yml@develop
    with:
      release-tag: ${{ github.ref_name }}
      commit-sha: ${{ github.sha }}
      image-digest: ${{ vars.STAGING_IMAGE_DIGEST }}
      environment: staging
      suite: backend-release
      config-hash: ${{ vars.BENCHMARK_CONFIG_HASH }}
```

The tag is a lookup key; the commit SHA and image digest are the immutable identity. A staging smoke step must compare the deployed digest with `image-digest` before publishing comparison evidence. Production promotion remains behind a protected environment approval.

Raw and normalized artifacts belong in GitHub Artifacts or configured object storage. The consumer service database is not modified. Missing artifacts, mismatched digests, fork pull requests, and insufficient samples are warning/inconclusive outcomes rather than silent success.

Fork pull requests use read-only `contents` permissions and must not receive release or deployment secrets. Release workflows should run only from trusted refs and use an explicitly protected environment.
