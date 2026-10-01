from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import replace

from pipeline_toolkit.compare.module_benchmark import EvaluationTarget, compare_module_benchmarks
from pipeline_toolkit.contracts.module_evidence import EnvironmentIdentity, ModuleBenchmarkEvidence, ResourceUsage, RunProvenance, validate_module_evidence

from .contract import ExperimentError, POLICY_VERSION, REPOSITORY, SOURCE_FIELDS, WORKFLOW_PATH, positive_id, require, run_url, safe_link, sha, source_identity, validate_header


def validate_run(run, run_id, attempt, commit, title=None, workflow_path=None):
    require(isinstance(run, dict), "run_unavailable")
    require(isinstance(run.get("repository"), dict) and isinstance(run.get("head_repository"), dict), "run_identity_mismatch")
    path = run.get("path")
    require(isinstance(path, str) and len(path) <= 256 and re.fullmatch(r"\.github/workflows/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.ya?ml", path) is not None, "run_identity_mismatch")
    require(workflow_path is None or path == workflow_path, "run_identity_mismatch")
    require(type(run.get("id")) is int and type(run.get("run_attempt")) is int and run["id"] == run_id and run["run_attempt"] == attempt and run.get("head_sha") == commit and run.get("event") == "workflow_dispatch" and run["repository"].get("full_name") == REPOSITORY and run["head_repository"].get("full_name") == REPOSITORY and run.get("html_url") == run_url(run_id), "run_identity_mismatch")
    if title is not None:
        require(run.get("display_title") == title, "run_identity_mismatch")


def _observation_identity(item, manifest):
    require(isinstance(item, dict) and item.get("side") in ("baseline", "candidate"), "invalid_observation")
    run_id = positive_id(item.get("run_id")); attempt = positive_id(item.get("run_attempt"))
    require(type(item.get("ordinal")) is int and item["ordinal"] in (1, 2, 3), "invalid_observation")
    require(sha(item.get("commit_sha")) == manifest[item["side"] + "_ref"], "run_identity_mismatch")
    return run_id, attempt


def validate_observation(item, manifest):
    run_id, attempt = _observation_identity(item, manifest)
    value = item.get("value")
    try:
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "invalid_observation")
    except OverflowError as exc:
        raise ExperimentError("invalid_observation") from exc
    require(isinstance(item.get("suite"), str) and 1 <= len(item["suite"]) <= 128, "invalid_observation")
    manifest_link = safe_link(item.get("manifest_url"), artifact_run=run_id)
    if item.get("grafana_url") is not None:
        safe_link(item["grafana_url"], grafana=True)
    try:
        identity = EnvironmentIdentity(**item["environment_identity"])
        # Suite is part of the comparator's job identity; SHA is provenance,
        # not a comparability key, because the two commits must differ.
        evidence = ModuleBenchmarkEvidence(module_id="pipeline-" + manifest["scope"], run_id=str(run_id), metric_name="workflow_wall_clock_seconds", metric_value=value, unit="seconds", resource=ResourceUsage(), provenance=RunProvenance(REPOSITORY, item["commit_sha"], WORKFLOW_PATH, item["suite"]), artifact_uri=manifest_link, environment_identity=identity)
        validate_module_evidence(evidence)
    except (KeyError, TypeError, ValueError) as exc:
        raise ExperimentError("invalid_observation") from exc
    return evidence, run_id, attempt


def _scalar(value):
    if type(value) in (str, int, bool) or value is None:
        return value if not isinstance(value, str) or len(value) <= 2048 else None
    return value if type(value) is float and math.isfinite(value) else None


def _link_or_invalid(value, **kwargs):
    try:
        return safe_link(value, **kwargs)
    except (ExperimentError, ValueError):
        return "invalid"


def _replay_collection(collection):
    """Allowlist replay data; never echo arbitrary artifact or GitHub fields."""
    manifest = collection["manifest"]
    result = {key: manifest.get(key) for key in ("version", "policy_version", "repository", "baseline_ref", "candidate_ref", "scope", "experiment_run_id", "experiment_run_attempt")}
    result["observations"] = []
    for item in manifest["observations"]:
        copied = {key: _scalar(item.get(key)) for key in ("side", "ordinal", "run_id", "run_attempt", "commit_sha", "value", "suite", "manifest_url", "grafana_url")}
        copied["manifest_url"] = _link_or_invalid(copied["manifest_url"], artifact_run=copied["run_id"])
        if copied["grafana_url"] is not None:
            copied["grafana_url"] = _link_or_invalid(copied["grafana_url"], grafana=True)
        identity = item.get("environment_identity")
        copied["environment_identity"] = {key: _scalar(identity.get(key)) for key in EnvironmentIdentity.__dataclass_fields__} if isinstance(identity, dict) else None
        source = item.get("source_identity")
        copied["source_identity"] = {key: _scalar(source.get(key)) for key in SOURCE_FIELDS} if isinstance(source, dict) else None
        result["observations"].append(copied)
    runs = {}
    for item in result["observations"]:
        key = f"{item['run_id']}:{item['run_attempt']}"
        run = collection["runs"].get(key)
        copied = {field: _scalar(run.get(field)) for field in ("id", "run_attempt", "head_sha", "status", "conclusion", "event", "path", "display_title", "html_url")} if isinstance(run, dict) else None
        if copied is not None:
            copied["html_url"] = _link_or_invalid(copied["html_url"])
            for field in ("repository", "head_repository"):
                copied[field] = {"full_name": _scalar(run[field].get("full_name"))} if isinstance(run.get(field), dict) else None
        runs[key] = copied
    checks = collection.get("identity_checks")
    checks = checks if isinstance(checks, dict) else {}
    identities = {}
    for key in runs:
        check = checks.get(key)
        identities[key] = {field: _scalar(check.get(field)) for field in (*SOURCE_FIELDS, "status")} if isinstance(check, dict) else None
    return {"manifest": result, "runs": runs, "manifest_url": collection.get("manifest_url"), "artifact_checks": {key: "verified" if collection["artifact_checks"].get(key) == "verified" else "unavailable" for key in runs}, "manifest_attestation": "verified" if collection.get("manifest_attestation") == "verified" else "unavailable", "identity_checks": identities}


def _links(observations, experiment_id, manifest_url):
    links = {"actions": {run_url(experiment_id)}, "manifests": {manifest_url} if manifest_url else set(), "grafana": set()}
    for item in observations:
        try:
            run_id = positive_id(item["run_id"])
            links["actions"].add(run_url(run_id))
            links["manifests"].add(safe_link(item["manifest_url"], artifact_run=run_id))
        except ExperimentError:
            pass
        if item.get("grafana_url"):
            try:
                links["grafana"].add(safe_link(item["grafana_url"], grafana=True))
            except ExperimentError:
                pass
    return {kind: sorted(values) for kind, values in links.items()}


def compare_collection(collection: dict, *, verification="offline_replay") -> dict:
    require(isinstance(collection.get("manifest"), dict), "invalid_collection")
    manifest = collection["manifest"]
    validate_header(manifest)
    experiment_id = positive_id(manifest.get("experiment_run_id"))
    experiment_attempt = positive_id(manifest.get("experiment_run_attempt"))
    observations = manifest.get("observations")
    require(isinstance(observations, list) and len(observations) <= 100 and all(isinstance(item, dict) for item in observations), "invalid_collection")
    runs = collection.get("runs")
    require(isinstance(runs, dict) and isinstance(collection.get("artifact_checks"), dict), "invalid_collection")
    if collection.get("manifest_url") is not None:
        safe_link(collection["manifest_url"], artifact_run=experiment_id)
    collection = _replay_collection(collection)
    manifest = collection["manifest"]
    observations = manifest["observations"]
    runs = collection["runs"]
    exclusions = []
    eligible = {"baseline": [], "candidate": []}
    accepted = []
    completed_runs = set()
    failed_runs = set()
    expected_identity = None
    conclusions = ("success", "failure", "cancelled", "timed_out", "skipped", "neutral", "action_required", "stale", "startup_failure")
    ids = Counter(str(item.get("run_id")) for item in observations)
    ordinals = Counter((str(item.get("side")), str(item.get("ordinal"))) for item in observations)
    for side in eligible:
        if sum(item.get("side") == side for item in observations) != 3:
            exclusions.append({"side": side, "run_id": None, "run_attempt": None, "reason": "sample_count_mismatch"})
    for item in observations:
        try:
            run_id, attempt = _observation_identity(item, manifest)
            run = runs.get(f"{run_id}:{attempt}")
            validate_run(run, run_id, attempt, item["commit_sha"], f"pipeline-experiment/{experiment_id}/{item['side']}/{item['ordinal']}")
            require(run.get("status") == "completed", "run_incomplete")
            conclusion = run.get("conclusion")
            # Execution outcome is authenticated independently of metric and
            # artifact eligibility. Failed runs commonly have no measurement.
            if conclusion in conclusions:
                completed_runs.add((run_id, attempt))
                if conclusion in ("failure", "cancelled", "timed_out", "startup_failure"):
                    failed_runs.add((run_id, attempt))
            require(conclusion == "success", "run_" + (conclusion if conclusion in conclusions else "unknown"))
            require(ids[str(run_id)] == 1 and run_id != experiment_id, "duplicate_run_id")
            require(ordinals[(item["side"], str(item["ordinal"]))] == 1, "duplicate_ordinal")
            evidence, _, _ = validate_observation(item, manifest)
            require(collection["artifact_checks"].get(f"{run_id}:{attempt}") == "verified", "sample_artifact_unavailable")
            identity = source_identity(item.get("source_identity"))
            require(collection["manifest_attestation"] == "verified", "manifest_attestation_unavailable")
            check = collection["identity_checks"].get(f"{run_id}:{attempt}")
            require(isinstance(check, dict) and check.get("status") == "verified" and all(check.get(field) == identity[field] for field in SOURCE_FIELDS), "source_identity_unverified")
            if expected_identity is None:
                expected_identity = identity
            require(identity["application_source_tree"] == expected_identity["application_source_tree"], "application_source_mismatch")
            require(identity["test_plan_sha256"] == expected_identity["test_plan_sha256"], "test_scope_mismatch")
            evidence = replace(evidence, provenance=replace(evidence.provenance, workflow=run["path"]))
            eligible[item["side"]].append(evidence)
            accepted.append(item)
        except ExperimentError as exc:
            diagnostic = {"side": item.get("side"), "run_id": item.get("run_id"), "run_attempt": item.get("run_attempt"), "reason": exc.code}
            if exc.code in ("run_failure", "run_cancelled", "run_timed_out", "run_startup_failure"):
                try:
                    validate_observation(item, manifest)
                except ExperimentError as measurement_error:
                    diagnostic["measurement_reason"] = measurement_error.code
            exclusions.append(diagnostic)
    comparison = compare_module_benchmarks(eligible["baseline"], eligible["candidate"], target=EvaluationTarget.RELEASE).to_dict()
    comparison["absolute_delta"] = comparison["candidate_median"] - comparison["baseline_median"] if comparison["baseline_median"] is not None and comparison["candidate_median"] is not None else None
    if comparison["baseline_median"] == 0:
        exclusions.append({"side": None, "run_id": None, "run_attempt": None, "reason": "zero_baseline"})
    if comparison["relative_delta"] is not None and not math.isfinite(comparison["relative_delta"]):
        comparison["relative_delta"] = None
        exclusions.append({"side": None, "run_id": None, "run_attempt": None, "reason": "numerical_overflow"})
    if comparison["reason"] == "comparability_key_mismatch":
        exclusions.append({"side": None, "run_id": None, "run_attempt": None, "reason": "comparability_key_mismatch"})
    classification = "inconclusive" if exclusions else comparison["classification"]
    if exclusions:
        comparison.update(classification="inconclusive", reason=exclusions[0]["reason"], policy_outcome="none")
    if classification == "comparable":
        verdict = "approval_review" if comparison["policy_outcome"] == "approval_hold" else "no_regression"
    else:
        verdict = classification
    return {
        "version": 1,
        "policy_version": POLICY_VERSION,
        "repository": REPOSITORY,
        "baseline_ref": manifest["baseline_ref"],
        "candidate_ref": manifest["candidate_ref"],
        "scope": manifest["scope"],
        "experiment_run": {"id": experiment_id, "attempt": experiment_attempt, "url": run_url(experiment_id)},
        "verification": verification,
        "classification": classification,
        "verdict": verdict,
        "comparison": comparison,
        "observations": accepted,
        "exclusions": exclusions,
        "failure_rate": len(failed_runs) / len(completed_runs) if completed_runs else None,
        "run_counts": {"authenticated_completed": len(completed_runs), "failed": len(failed_runs)},
        "links": _links(observations, experiment_id, collection.get("manifest_url")),
        "collection": collection,
        "limitations": [
            "Three observations do not establish statistical significance.",
            "This experiment does not modify required checks or an automatic deployment gate.",
        ],
    }
