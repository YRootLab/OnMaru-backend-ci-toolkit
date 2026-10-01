from __future__ import annotations

import io
import time
import zipfile

from .compare import compare_collection, validate_observation, validate_run
from .contract import ExperimentError, MAX_BYTES, REPOSITORY, WORKFLOW, WORKFLOW_PATH, load_json_bytes, positive_id, require, run_url, safe_link, validate_header

PREFIX = "repos/" + REPOSITORY


def _manifest(github, receipt, run_id, attempt):
    metadata = github.api(PREFIX + f"/actions/runs/{run_id}/artifacts?per_page=100")
    artifacts = metadata.get("artifacts")
    require(isinstance(artifacts, list) and all(isinstance(item, dict) for item in artifacts) and type(metadata.get("total_count")) is int and metadata["total_count"] == len(artifacts) and len(artifacts) <= 100, "partial_artifact_listing")
    selected = [item for item in artifacts if item.get("name") == f"pipeline-experiment-manifest-{attempt}"]
    require(len(selected) == 1, "manifest_unavailable")
    artifact = selected[0]
    artifact_id = positive_id(artifact.get("id"))
    require(artifact.get("expired") is False and type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= MAX_BYTES and isinstance(artifact.get("workflow_run"), dict) and artifact["workflow_run"].get("id") == run_id and artifact["workflow_run"].get("head_sha") == receipt["baseline_ref"], "invalid_artifact")
    raw = github.raw(PREFIX + f"/actions/artifacts/{artifact_id}/zip")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            require(len(entries) == 1 and entries[0].filename == "experiment-manifest.json" and entries[0].file_size <= MAX_BYTES and not entries[0].flag_bits & 1 and (entries[0].external_attr >> 16) & 0o170000 != 0o120000, "unsafe_manifest_archive")
            document = load_json_bytes(archive.read(entries[0]))
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as exc:
        raise ExperimentError("invalid_manifest_archive") from exc
    return document, safe_link(run_url(run_id) + f"/artifacts/{artifact_id}", artifact_run=run_id)


def _sample_artifact(github, item, manifest):
    _, run_id, attempt = validate_observation(item, manifest)
    artifact_id = int(item["manifest_url"].rsplit("/", 1)[1])
    artifact = github.api(PREFIX + f"/actions/artifacts/{artifact_id}")
    require(artifact.get("id") == artifact_id and artifact.get("name") == f"pipeline-experiment-sample-{attempt}" and artifact.get("expired") is False and type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= MAX_BYTES and isinstance(artifact.get("workflow_run"), dict) and artifact["workflow_run"].get("id") == run_id and artifact["workflow_run"].get("head_sha") == item["commit_sha"], "sample_artifact_unavailable")


def wait_and_collect(github, receipt, *, timeout=1800.0, poll_interval=5.0, sleep=time.sleep) -> dict:
    validate_header(receipt)
    require(receipt.get("dry_run") is False and receipt.get("workflow") == WORKFLOW, "invalid_receipt")
    identity = receipt.get("experiment_run")
    require(isinstance(identity, dict), "invalid_receipt")
    run_id = positive_id(identity.get("id")); attempt = positive_id(identity.get("attempt"))
    require(identity.get("url") == run_url(run_id), "invalid_receipt")
    require(type(timeout) in (int, float) and 0 < timeout <= 3600 and type(poll_interval) in (int, float) and 0.01 <= poll_interval <= 30, "invalid_limits")
    github.deadline = time.monotonic() + timeout
    try:
        github.authenticate()
        for _ in range(1000):
            require(time.monotonic() < github.deadline, "wait_timeout")
            run = github.api(PREFIX + f"/actions/runs/{run_id}/attempts/{attempt}")
            validate_run(run, run_id, attempt, receipt["baseline_ref"], workflow_path=WORKFLOW_PATH)
            if run.get("status") == "completed":
                break
            sleep(min(poll_interval, max(0, github.deadline - time.monotonic())))
        else:
            raise ExperimentError("poll_limit")
        require(run.get("conclusion") == "success", "experiment_" + str(run.get("conclusion") or "unknown"))
        manifest, link = _manifest(github, receipt, run_id, attempt)
        validate_header(manifest)
        require(all(manifest.get(key) == receipt.get(key) for key in ("baseline_ref", "candidate_ref", "scope", "repository", "policy_version")) and manifest.get("experiment_run_id") == run_id and manifest.get("experiment_run_attempt") == attempt, "manifest_identity_mismatch")
        observations = manifest.get("observations")
        require(isinstance(observations, list) and len(observations) <= 100, "invalid_collection")
        runs = {}
        artifact_checks = {}
        for item in observations:
            if not isinstance(item, dict):
                raise ExperimentError("invalid_collection")
            try:
                sample_id = positive_id(item.get("run_id")); sample_attempt = positive_id(item.get("run_attempt"))
                key = f"{sample_id}:{sample_attempt}"
                if key not in runs:
                    runs[key] = github.api(PREFIX + f"/actions/runs/{sample_id}/attempts/{sample_attempt}")
                    _sample_artifact(github, item, manifest)
                    artifact_checks[key] = "verified"
            except ExperimentError as exc:
                if exc.code in ("wait_timeout", "command_timeout", "command_output_limit"):
                    raise
                key = f"{item.get('run_id')}:{item.get('run_attempt')}"
                runs.setdefault(key, None)
                artifact_checks[key] = "unavailable"
        collection = {"manifest": manifest, "manifest_url": link, "runs": runs, "artifact_checks": artifact_checks}
        return compare_collection(collection, verification="github_run_attempts")
    finally:
        github.deadline = None
