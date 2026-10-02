from __future__ import annotations

import io
import binascii
import base64
import hashlib
import struct
import time
import zipfile
import zlib

from .compare import compare_collection, validate_observation, validate_run
from .contract import ExperimentError, MAX_BYTES, REPOSITORY, TEST_PLAN_PATH, WORKFLOW, WORKFLOW_PATH, load_json_bytes, positive_id, require, run_url, safe_link, source_identity, validate_header

PREFIX = "repos/" + REPOSITORY


def _manifest_bytes(raw):
    """One bounded ZIP member; never let advertised sizes bound inflation."""
    require(len(raw) <= MAX_BYTES, "unsafe_manifest_archive")
    try:
        end = raw.rfind(b"PK\x05\x06")
        require(end >= 0 and end + 22 <= len(raw), "unsafe_manifest_archive")
        _, disk, directory_disk, disk_count, count, directory_size, directory_offset, comment = struct.unpack_from("<I4H2IH", raw, end)
        require(disk == directory_disk == 0 and disk_count == count == 1 and end + 22 + comment == len(raw) and directory_offset + directory_size == end, "unsafe_manifest_archive")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            require(len(entries) == 1, "unsafe_manifest_archive")
            entry = entries[0]
            require(entry.filename == entry.orig_filename == "experiment-manifest.json" and entry.header_offset == 0 and entry.file_size <= MAX_BYTES and entry.flag_bits & ~0x808 == 0 and entry.compress_type in (0, 8) and (entry.external_attr >> 16) & 0o170000 in (0, 0o100000) and not entry.external_attr & 0x10 and archive.start_dir == directory_offset, "unsafe_manifest_archive")
            signature, version, flags, method, _, _, crc, compressed_size, size, name_size, extra_size = struct.unpack_from("<IHHHHHIIIHH", raw)
            require(signature == 0x04034b50 and version == entry.extract_version and version <= 20 and (flags, method) == (entry.flag_bits, entry.compress_type), "unsafe_manifest_archive")
            central_values = (entry.CRC, entry.compress_size, entry.file_size)
            require((crc, compressed_size, size) == ((0, 0, 0) if flags & 8 else central_values), "unsafe_manifest_archive")
            start = 30 + name_size + extra_size
            data_end = start + entry.compress_size
            require(raw[30:30 + name_size] == b"experiment-manifest.json" and start <= data_end <= directory_offset, "unsafe_manifest_archive")
            if flags & 8:
                # Locate by validated directory offsets, not a signature scan:
                # compressed bytes and an unsigned CRC can contain PK\x07\x08.
                descriptor_size = directory_offset - data_end
                require(descriptor_size in (12, 16), "unsafe_manifest_archive")
                descriptor_start = data_end
                if descriptor_size == 16:
                    require(raw[data_end:data_end + 4] == b"PK\x07\x08", "unsafe_manifest_archive")
                    descriptor_start += 4
                require(struct.unpack_from("<III", raw, descriptor_start) == central_values, "unsafe_manifest_archive")
            else:
                require(data_end == directory_offset, "unsafe_manifest_archive")
            # ZIP64 and extra fields carrying contradictory size claims are not
            # part of this deliberately narrow consumer archive contract.
            require(extra_size == 0 and not entry.extra, "unsafe_manifest_archive")
            crc, compressed_size, size = central_values
        output = bytearray()
        inflater = zlib.decompressobj(-15) if method == 8 else None
        for offset in range(start, data_end, 65536):
            pending = raw[offset:min(offset + 65536, data_end)]
            while pending:
                chunk = inflater.decompress(pending, min(65536, MAX_BYTES - len(output) + 1)) if inflater else pending
                require(len(output) + len(chunk) <= MAX_BYTES, "unsafe_manifest_archive")
                output.extend(chunk)
                pending = inflater.unconsumed_tail if inflater else b""
                if inflater:
                    require(not inflater.unused_data, "unsafe_manifest_archive")
        require(inflater is None or inflater.eof, "unsafe_manifest_archive")
        require(len(output) == size and binascii.crc32(output) == crc, "unsafe_manifest_archive")
        return bytes(output)
    except (zipfile.BadZipFile, struct.error, zlib.error, RuntimeError, OSError, NotImplementedError) as exc:
        raise ExperimentError("invalid_manifest_archive") from exc


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
    payload = _manifest_bytes(raw)
    document = load_json_bytes(payload)
    return document, safe_link(run_url(run_id) + f"/artifacts/{artifact_id}", artifact_run=run_id), payload


def _verify_source(github, item, manifest):
    identity = source_identity(item.get("source_identity"))
    commit = github.api(PREFIX + "/git/commits/" + identity["application_source_commit"])
    require(commit.get("sha") == identity["application_source_commit"] and isinstance(commit.get("tree"), dict) and commit["tree"].get("sha") == identity["application_source_tree"], "source_identity_unverified")
    document = github.api(PREFIX + "/contents/" + TEST_PLAN_PATH + "?ref=" + identity["application_source_commit"])
    require(document.get("type") == "file" and document.get("encoding") == "base64" and isinstance(document.get("content"), str) and len(document["content"]) <= MAX_BYTES, "source_identity_unverified")
    try:
        raw = base64.b64decode(document["content"].replace("\n", ""), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ExperimentError("source_identity_unverified") from exc
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(blob == document.get("sha") and hashlib.sha256(raw).hexdigest() == identity["test_plan_sha256"], "source_identity_unverified")
    plan = load_json_bytes(raw)
    require(plan.get("scope") == manifest["scope"] and plan.get("suite") == item.get("suite"), "source_identity_unverified")
    return {"status": "verified", **identity}


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
        manifest, link, payload = _manifest(github, receipt, run_id, attempt)
        validate_header(manifest)
        require(all(manifest.get(key) == receipt.get(key) for key in ("baseline_ref", "candidate_ref", "scope", "repository", "policy_version")) and manifest.get("experiment_run_id") == run_id and manifest.get("experiment_run_attempt") == attempt, "manifest_identity_mismatch")
        attestation = "unavailable"
        try:
            github.verify_manifest(payload, receipt["baseline_ref"])
            attestation = "verified"
        except ExperimentError as exc:
            if exc.code in ("wait_timeout", "command_timeout", "command_output_limit"):
                raise
        observations = manifest.get("observations")
        require(isinstance(observations, list) and len(observations) <= 100, "invalid_collection")
        runs = {}
        artifact_checks = {}
        identity_checks = {}
        source_cache = {}
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
                    try:
                        source = source_identity(item.get("source_identity"))
                    except ExperimentError:
                        identity_checks[key] = None
                        continue
                    cache_key = (*source.values(), manifest["scope"], item.get("suite"))
                    if cache_key not in source_cache:
                        try:
                            source_cache[cache_key] = _verify_source(github, item, manifest)
                        except ExperimentError as exc:
                            if exc.code in ("wait_timeout", "command_timeout", "command_output_limit"):
                                raise
                            source_cache[cache_key] = None
                    identity_checks[key] = source_cache[cache_key]
            except ExperimentError as exc:
                if exc.code in ("wait_timeout", "command_timeout", "command_output_limit"):
                    raise
                key = f"{item.get('run_id')}:{item.get('run_attempt')}"
                runs.setdefault(key, None)
                artifact_checks[key] = "unavailable"
        collection = {"manifest": manifest, "manifest_url": link, "runs": runs, "artifact_checks": artifact_checks, "manifest_attestation": attestation, "identity_checks": identity_checks}
        return compare_collection(collection, verification="github_run_attempts")
    finally:
        github.deadline = None
