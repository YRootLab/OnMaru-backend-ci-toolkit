from __future__ import annotations

import copy
import contextlib
import io
import json
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).parents[1]
REPOSITORY = "YRootLab/OnMaru-backend"
PREFIX = "repos/" + REPOSITORY
POLICY = "pipeline-experiment/2"
BASELINE = "a" * 40
APP_COMMIT = "c" * 40
APP_TREE = "d" * 40
TEST_PLAN = b'{"scope":"ci","suite":"full-java"}'
TEST_DIGEST = hashlib.sha256(TEST_PLAN).hexdigest()


def _source_identity():
    return {"application_source_commit": APP_COMMIT, "application_source_tree": APP_TREE, "test_plan_sha256": TEST_DIGEST}


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _run_record(run_id, commit, title):
    return {"id": run_id, "run_attempt": 1, "head_sha": commit, "status": "completed", "conclusion": "success", "event": "workflow_dispatch", "repository": {"full_name": REPOSITORY}, "head_repository": {"full_name": REPOSITORY}, "path": ".github/workflows/pipeline-benchmark-experiment.yml", "display_title": title, "html_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}"}


@pytest.fixture
def environment(tmp_path):
    repo = tmp_path / "consumer"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "checkout", "-qb", "feature/cache")
    _git(repo, "commit", "-qm", "fixture", "--allow-empty")
    _git(repo, "remote", "add", "origin", "https://github.com/YRootLab/OnMaru-backend.git")
    candidate = _git(repo, "rev-parse", "HEAD")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake = fake_bin / "gh"
    shutil.copyfile(ROOT / "tests/fixtures/experiments/fake_gh.py", fake)
    fake.chmod(0o755)
    observations = []
    runs = {}
    for side, values, first_id, commit in (("baseline", (99, 100, 101), 1, BASELINE), ("candidate", (115, 116, 117), 11, candidate)):
        for index, value in enumerate(values, 1):
            run_id = first_id + index - 1
            runs[str(run_id)] = _run_record(run_id, commit, f"pipeline-experiment/900/{side}/{index}")
            observations.append({"side": side, "ordinal": index, "run_id": run_id, "run_attempt": 1, "commit_sha": commit, "value": value, "suite": "full-java", "environment_identity": {"runner_image": "ubuntu-24.04", "java_version": "21", "python_version": "3.9", "cache_state": "cold", "database_fixture": "postgres-16", "cpu_memory_profile": "4cpu-16gb", "dependency_mode": "locked", "config_catalog_hash": "sha256:fixture"}, "manifest_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}/artifacts/{run_id + 1000}", "grafana_url": "https://fixture.grafana.net/d/ci"})
    manifest = {"version": 1, "policy_version": POLICY, "repository": REPOSITORY, "baseline_ref": BASELINE, "candidate_ref": candidate, "scope": "ci", "experiment_run_id": 900, "experiment_run_attempt": 1, "observations": observations}
    for item in observations:
        item["source_identity"] = _source_identity()
    scenario = {"baseline": BASELINE, "candidate": candidate, "parent": _run_record(900, BASELINE, "experiment"), "manifest": manifest, "runs": runs}
    scenario_path = tmp_path / "scenario.json"
    calls = tmp_path / "calls.jsonl"
    env = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ["PATH"], PYTHONPATH=str(ROOT / "src"), EXPERIMENT_SCENARIO=str(scenario_path), EXPERIMENT_CALLS=str(calls))

    def invoke(action="dry-run", *options):
        scenario_path.write_text(json.dumps(scenario))
        command = [sys.executable, "-m", "pipeline_toolkit.cli", "experiment", action, *options]
        if action in ("dry-run", "dispatch"):
            command.extend(["--repo-root", str(repo), "--scope", "ci", "--reason", "measure cache"])
        # Keep the external gh executable fake and git real. Calling the CLI
        # entry point here lets canonical coverage measure the tested code;
        # the standalone process test below also verifies module invocation.
        from pipeline_toolkit.cli import main
        out = io.StringIO(); err = io.StringIO()
        with patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(command[3:])
        return subprocess.CompletedProcess(command, code, out.getvalue(), err.getvalue())

    return {"repo": repo, "scenario": scenario, "calls": calls, "invoke": invoke, "tmp": tmp_path, "env": env}


def _json(result):
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stderr == ""
    return json.loads(result.stdout)


def _calls(env):
    return [json.loads(line) for line in env["calls"].read_text().splitlines()] if env["calls"].exists() else []


def _receipt(env):
    result = _json(env["invoke"]("dispatch"))
    receipt = env["tmp"] / "receipt.json"
    receipt.write_text(json.dumps(result))
    return receipt


def test_dry_run_pins_remote_refs_and_never_dispatches(environment):
    first = environment["invoke"]()
    plan = _json(first)
    assert first.stdout == environment["invoke"]().stdout
    assert plan["dry_run"] is True
    assert plan["policy_version"] == "pipeline-experiment/2"
    assert plan["baseline_ref"] == "a" * 40
    assert plan["candidate_ref"] == environment["scenario"]["candidate"]
    assert plan["dispatch_payload"] == {"ref": "develop", "inputs": {"baseline_ref": BASELINE, "candidate_ref": environment["scenario"]["candidate"], "scope": "ci", "reason": "measure cache"}}
    assert all(call["args"][call["args"].index("--method") + 1] == "GET" for call in _calls(environment) if call["args"][0] == "api")


def test_standalone_cli_dry_run_matches_entry_point(environment):
    expected = environment["invoke"]()
    command = [sys.executable, "-m", "pipeline_toolkit.cli", "experiment", "dry-run", "--repo-root", str(environment["repo"]), "--scope", "ci", "--reason", "measure cache"]
    actual = subprocess.run(command, env=environment["env"], capture_output=True, text=True, timeout=10)
    assert actual.returncode == 0
    assert actual.stdout == expected.stdout
    assert actual.stderr == ""


@pytest.mark.parametrize("change,code", [("dirty", "dirty_tree"), ("wrong_repo", "wrong_repository"), ("branch", "feature_branch_required"), ("candidate_moved", "candidate_not_pushed"), ("same_sha", "equal_refs"), ("no_workflow", "workflow_unavailable"), ("fork", "untrusted_repository"), ("auth", "command_failed"), ("missing_baseline", "invalid_ref")])
def test_preflight_rejects_unsafe_state_without_network_mutation(environment, change, code):
    scenario = environment["scenario"]
    if change == "dirty": (environment["repo"] / "untracked").write_text("dirty")
    elif change == "wrong_repo": _git(environment["repo"], "remote", "set-url", "origin", "https://github.com/fork/OnMaru-backend.git")
    elif change == "branch": _git(environment["repo"], "checkout", "-qb", "fix/cache")
    elif change == "candidate_moved": scenario["candidate"] = "b" * 40
    elif change == "same_sha": scenario["baseline"] = scenario["candidate"]
    elif change == "no_workflow": scenario["overrides"] = {PREFIX + "/actions/workflows/pipeline-benchmark-experiment.yml": {"state": "disabled_manually"}}
    elif change == "fork": scenario["overrides"] = {PREFIX: {"full_name": REPOSITORY, "fork": True}}
    elif change == "auth": scenario["unauthenticated"] = True
    elif change == "missing_baseline": scenario["baseline"] = "develop"
    result = environment["invoke"]("dispatch")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == code
    assert not any("POST" in call["args"] for call in _calls(environment))


def test_dispatch_respects_integration_gate_and_records_exact_run(environment):
    environment["scenario"]["gate_state"] = "open"
    result = environment["invoke"]("dispatch")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "integration_gate_open"
    assert not any("POST" in call["args"] for call in _calls(environment))
    environment["scenario"]["gate_state"] = "closed"
    receipt = _json(environment["invoke"]("dispatch"))
    assert receipt["experiment_run"] == {"id": 900, "attempt": 1, "url": f"https://github.com/{REPOSITORY}/actions/runs/900"}
    posts = [call for call in _calls(environment) if "POST" in call["args"]]
    assert len(posts) == 1
    assert posts[0]["body"] == receipt["dispatch_payload"]


def test_wait_collects_exact_attempts_and_calls_comparator(environment):
    receipt = _receipt(environment)
    environment["scenario"]["pending_polls"] = 1
    result = _json(environment["invoke"]("wait", "--receipt", str(receipt), "--poll-interval", "0.01"))
    assert result["classification"] == "comparable"
    assert result["verdict"] == "approval_review"
    assert result["comparison"]["sample_values"] == {"baseline": [99, 100, 101], "candidate": [115, 116, 117]}
    assert result["comparison"]["sample_range"] == {"baseline": 2, "candidate": 2}
    assert result["comparison"]["baseline_median"] == 100
    assert result["comparison"]["candidate_median"] == 116
    assert result["comparison"]["relative_delta"] == 0.16
    assert result["exclusions"] == []
    assert len(result["links"]["actions"]) == 7
    assert len(result["links"]["manifests"]) == 7
    assert result["links"]["grafana"] == ["https://fixture.grafana.net/d/ci"]
    assert {record["run_id"] for record in result["observations"]} == {1, 2, 3, 11, 12, 13}
    assert all(record["run_attempt"] == 1 for record in result["observations"])
    assert sum("POST" in call["args"] for call in _calls(environment)) == 1
    source = environment["tmp"] / "collection.json"
    source.write_text(json.dumps(result["collection"]))
    replay = _json(environment["invoke"]("compare", "--input", str(source)))
    assert replay["comparison"] == result["comparison"]
    assert replay["verification"] == "offline_replay"


@pytest.mark.parametrize("change,reason", [("two", "sample_count_mismatch"), ("four", "sample_count_mismatch"), ("duplicate", "duplicate_run_id"), ("failed", "run_failure"), ("cancelled", "run_cancelled"), ("attempt", "run_identity_mismatch"), ("sha", "run_identity_mismatch"), ("suite", "source_identity_unverified"), ("cache", "comparability_key_mismatch"), ("missing", "run_unavailable"), ("value", "invalid_observation"), ("foreign", "run_identity_mismatch")])
def test_invalid_samples_are_excluded_without_repeated_benchmarks(environment, change, reason):
    receipt = _receipt(environment)
    scenario = environment["scenario"]
    samples = scenario["manifest"]["observations"]
    if change == "two": del samples[-1]
    elif change == "four": samples.append(copy.deepcopy(samples[-1]) | {"run_id": 14, "ordinal": 4})
    elif change == "duplicate": samples[-1]["run_id"] = 12
    elif change in ("failed", "cancelled"): scenario["runs"]["13"]["conclusion"] = "failure" if change == "failed" else "cancelled"
    elif change == "attempt": scenario["runs"]["13"]["run_attempt"] = 2
    elif change == "sha": scenario["runs"]["13"]["head_sha"] = "f" * 40
    elif change == "suite": samples[-1]["suite"] = "subset"
    elif change == "cache": samples[-1]["environment_identity"]["cache_state"] = "warm"
    elif change == "missing": del scenario["runs"]["13"]
    elif change == "value": samples[-1]["value"] = float("nan")
    elif change == "foreign": scenario["runs"]["13"]["head_repository"]["full_name"] = "fork/repo"
    result = _json(environment["invoke"]("wait", "--receipt", str(receipt)))
    assert result["classification"] == "inconclusive"
    assert result["verdict"] == "inconclusive"
    assert reason in {excluded["reason"] for excluded in result["exclusions"]}
    assert sum("POST" in call["args"] for call in _calls(environment)) == 1


@pytest.mark.parametrize("scope", ["cd", "production", "ci;touch /tmp/injected"])
def test_scope_is_fail_closed(environment, scope):
    environment["tmp"].joinpath("scenario.json").write_text(json.dumps(environment["scenario"]))
    command = [sys.executable, "-m", "pipeline_toolkit.cli", "experiment", "dispatch", "--repo-root", str(environment["repo"]), "--scope", scope, "--reason", "measurement"]
    result = subprocess.run(command, env=environment["env"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "unsupported_scope"
    assert not any("POST" in call["args"] for call in _calls(environment))


def _collection(environment):
    scenario = environment["scenario"]
    return {"manifest": copy.deepcopy(scenario["manifest"]), "manifest_url": f"https://github.com/{REPOSITORY}/actions/runs/900/artifacts/500", "runs": {f"{key}:1": copy.deepcopy(value) for key, value in scenario["runs"].items()}, "artifact_checks": {f"{key}:1": "verified" for key in scenario["runs"]}, "manifest_attestation": "verified", "identity_checks": {f"{key}:1": {"status": "verified", **_source_identity()} for key in scenario["runs"]}}


@pytest.mark.parametrize("change,reason", [("missing", "source_identity_unavailable"), ("unverified", "source_identity_unverified"), ("forged", "source_identity_unverified"), ("source", "application_source_mismatch"), ("tests", "test_scope_mismatch"), ("attestation", "manifest_attestation_unavailable")])
def test_source_and_test_scope_must_be_separately_verified(environment, change, reason):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    item = collection["manifest"]["observations"][-1]
    if change == "missing": del item["source_identity"]
    elif change == "unverified": del collection["identity_checks"]["13:1"]
    elif change == "forged": item["source_identity"]["application_source_tree"] = "e" * 40
    elif change == "source":
        item["source_identity"]["application_source_tree"] = "e" * 40
        collection["identity_checks"]["13:1"]["application_source_tree"] = "e" * 40
    elif change == "tests":
        item["source_identity"]["test_plan_sha256"] = "f" * 64
        collection["identity_checks"]["13:1"]["test_plan_sha256"] = "f" * 64
    elif change == "attestation": collection["manifest_attestation"] = "unavailable"
    result = compare_collection(collection)
    assert result["classification"] == result["verdict"] == "inconclusive"
    assert result["comparison"]["policy_outcome"] == "none"
    assert reason in {record["reason"] for record in result["exclusions"]}


def test_verified_source_and_scope_survive_replay(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    result = compare_collection(_collection(environment))
    assert result["collection"]["identity_checks"]["13:1"] == {"status": "verified", **_source_identity()}
    assert result["observations"][-1]["source_identity"] == _source_identity()
    assert compare_collection(result["collection"])["comparison"] == result["comparison"]


@pytest.mark.parametrize("change,reason", [("attestation", "manifest_attestation_unavailable"), ("tree", "source_identity_unverified"), ("plan", "source_identity_unverified"), ("missing", "source_identity_unavailable")])
def test_online_collection_rejects_spoofed_source_evidence(environment, change, reason):
    receipt = _receipt(environment)
    scenario = environment["scenario"]
    if change == "attestation": scenario["attestation_failure"] = True
    elif change == "missing": del scenario["manifest"]["observations"][-1]["source_identity"]
    elif change == "tree": scenario["overrides"] = {PREFIX + "/git/commits/" + APP_COMMIT: {"sha": APP_COMMIT, "tree": {"sha": "e" * 40}}}
    elif change == "plan": scenario["overrides"] = {PREFIX + "/contents/.github/pipeline-benchmark-test-plan.json?ref=" + APP_COMMIT: {"type": "file", "encoding": "base64", "content": "e30=", "sha": "f" * 40}}
    result = _json(environment["invoke"]("wait", "--receipt", str(receipt)))
    assert result["classification"] == "inconclusive"
    assert reason in {record["reason"] for record in result["exclusions"]}


def test_online_collection_independently_verifies_source_test_plan_and_signer(environment):
    receipt = _receipt(environment)
    result = _json(environment["invoke"]("wait", "--receipt", str(receipt)))
    calls = _calls(environment)
    assert len([call for call in calls if call["args"][:2] == ["attestation", "verify"]]) == 1
    assert any(call["args"][1] == PREFIX + "/git/commits/" + APP_COMMIT for call in calls if call["args"][0] == "api")
    assert result["collection"]["manifest_attestation"] == "verified"
    assert result["collection"]["identity_checks"]["13:1"] == {"status": "verified", **_source_identity()}
    assert result["classification"] == "comparable"


def test_workflow_refs_can_differ_while_verified_application_tree_is_equal(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    collection["manifest"]["observations"][-1]["source_identity"]["application_source_commit"] = "e" * 40
    collection["identity_checks"]["13:1"]["application_source_commit"] = "e" * 40
    result = compare_collection(collection)
    assert result["baseline_ref"] != result["candidate_ref"]
    assert result["classification"] == "comparable"
    assert result["exclusions"] == []


def test_replay_strips_unknown_raw_fields_and_sanitizes_invalid_numbers(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    collection["manifest"]["raw_consumer_source"] = "DO_NOT_ECHO"
    collection["runs"]["1:1"]["token"] = "DO_NOT_ECHO"
    collection["manifest"]["observations"][-1]["value"] = float("inf")
    result = compare_collection(collection)
    serialized = json.dumps(result, allow_nan=False)
    assert "DO_NOT_ECHO" not in serialized
    assert result["classification"] == "inconclusive"
    assert result["comparison"]["policy_outcome"] == "none"
    assert compare_collection(result["collection"])["exclusions"] == result["exclusions"]


@pytest.mark.parametrize("field,value", [("manifest_url", "https://evil.invalid/actions/runs/1"), ("grafana_url", "https://user:secret@fixture.grafana.net/d/ci"), ("grafana_url", "https://fixture.grafana.net:bad/d/ci"), ("value", True), ("value", -1), ("value", 10 ** 400), ("ordinal", 0), ("run_attempt", True), ("commit_sha", "develop"), ("environment_identity", {"runner_image": "ubuntu"})], ids=["wrong_manifest_link", "grafana_credentials", "grafana_bad_port", "boolean_value", "negative_value", "unrepresentable_number", "bad_ordinal", "boolean_attempt", "mutable_sha", "partial_environment"])
def test_offline_invalid_observation_never_becomes_regression(environment, field, value):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    collection["manifest"]["observations"][-1][field] = value
    result = compare_collection(collection)
    assert result["classification"] == "inconclusive"
    assert result["comparison"]["policy_outcome"] == "none"
    assert result["exclusions"]


@pytest.mark.parametrize("field,value", [("repository", None), ("head_repository", []), ("id", True), ("display_title", "unrelated measurement"), ("status", "in_progress"), ("conclusion", "timed_out")])
def test_replay_validates_run_metadata_and_correlation(environment, field, value):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    collection["runs"]["1:1"][field] = value
    result = compare_collection(collection)
    assert result["classification"] == "inconclusive"
    assert result["comparison"]["policy_outcome"] == "none"


def test_exact_three_gate_does_not_select_best_three_of_four(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    fourth = copy.deepcopy(collection["manifest"]["observations"][-1])
    fourth.update(run_id=14, ordinal=4, value=95)
    collection["manifest"]["observations"].append(fourth)
    result = compare_collection(collection)
    assert result["classification"] == "inconclusive"
    assert result["comparison"]["classification"] == "inconclusive"
    assert result["comparison"]["policy_outcome"] == "none"


def test_no_regression_and_markdown_replay_preserve_evidence_links(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    for item in collection["manifest"]["observations"]:
        if item["side"] == "candidate": item["value"] = 110
    assert compare_collection(collection)["verdict"] == "no_regression"
    source = environment["tmp"] / "collection.json"
    source.write_text(json.dumps(collection))
    result = environment["invoke"]("compare", "--input", str(source), "--format", "markdown")
    assert result.returncode == 0
    assert "observations [99, 100, 101]; median 100; range 2" in result.stdout
    assert "Relative delta: 0.1" in result.stdout
    assert "https://fixture.grafana.net/d/ci" in result.stdout


@pytest.mark.parametrize("kind,code", [("oversized", "command_output_limit"), ("sleep", "command_timeout"), ("stderr_secret", "command_failed")])
def test_process_boundary_limits_output_time_and_does_not_leak_stderr(environment, monkeypatch, kind, code):
    from pipeline_toolkit.experiments.github import BoundedProcess
    from pipeline_toolkit.experiments.contract import ExperimentError
    environment["scenario"][kind] = 0.5 if kind == "sleep" else True
    environment["tmp"].joinpath("scenario.json").write_text(json.dumps(environment["scenario"]))
    for key in ("PATH", "EXPERIMENT_SCENARIO", "EXPERIMENT_CALLS"): monkeypatch.setenv(key, environment["env"][key])
    with pytest.raises(ExperimentError) as caught:
        BoundedProcess().run(["gh", "api", "user", "--method", "GET"], timeout=0.1 if kind == "sleep" else 3)
    assert caught.value.code == code
    assert "DO_NOT_PRINT" not in str(caught.value)


@pytest.mark.parametrize("change,code", [("parent_failed", "experiment_failure"), ("archive_path", "unsafe_manifest_archive"), ("manifest_sha", "manifest_identity_mismatch"), ("expired", "invalid_artifact"), ("no_manifest", "manifest_unavailable"), ("pagination", "partial_artifact_listing")])
def test_collection_rejects_wrong_or_unsafe_artifact(environment, change, code):
    receipt = _receipt(environment)
    scenario = environment["scenario"]
    if change == "parent_failed": scenario["parent"]["conclusion"] = "failure"
    elif change == "archive_path": scenario["archive_filename"] = "../experiment-manifest.json"
    elif change == "manifest_sha": scenario["manifest"]["candidate_ref"] = "f" * 40
    else:
        artifact = {"id": 500, "name": "pipeline-experiment-manifest-1", "expired": change == "expired", "size_in_bytes": 100, "workflow_run": {"id": 900, "head_sha": BASELINE}}
        scenario["overrides"] = {PREFIX + "/actions/runs/900/artifacts?per_page=100": {"total_count": 2 if change == "pagination" else 1, "artifacts": [] if change == "no_manifest" else [artifact]}}
        if change == "no_manifest": scenario["overrides"][PREFIX + "/actions/runs/900/artifacts?per_page=100"]["total_count"] = 0
    result = environment["invoke"]("wait", "--receipt", str(receipt))
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == code


def test_wait_deadline_bounds_polling_without_dispatch_or_rerun(environment):
    receipt = _receipt(environment)
    environment["scenario"]["pending_polls"] = 999
    result = environment["invoke"]("wait", "--receipt", str(receipt), "--timeout", "0.5", "--poll-interval", "0.01")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] in ("wait_timeout", "command_timeout")
    assert sum("POST" in call["args"] for call in _calls(environment)) == 1


def test_reason_is_json_data_not_shell_code(environment):
    reason = "$(touch SHOULD_NOT_EXIST); `echo secret`"
    environment["tmp"].joinpath("scenario.json").write_text(json.dumps(environment["scenario"]))
    command = [sys.executable, "-m", "pipeline_toolkit.cli", "experiment", "dispatch", "--repo-root", str(environment["repo"]), "--reason", reason]
    result = _json(subprocess.run(command, env=environment["env"], cwd=environment["tmp"], capture_output=True, text=True, timeout=10))
    assert result["dispatch_payload"]["inputs"]["reason"] == reason
    assert not (environment["tmp"] / "SHOULD_NOT_EXIST").exists()


def test_consumer_sample_workflow_is_distinct_from_orchestrator_and_comparable(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    for run in collection["runs"].values():
        run["path"] = ".github/workflows/pipeline-benchmark-sample.yml"
    assert compare_collection(collection)["classification"] == "comparable"
    collection["runs"]["13:1"]["path"] = ".github/workflows/unrelated.yml"
    result = compare_collection(collection)
    assert result["classification"] == "inconclusive"
    assert "comparability_key_mismatch" in {item["reason"] for item in result["exclusions"]}


@pytest.mark.parametrize("path", ["../unsafe.yml", ".github/workflows/x.yml@feature/foo", ".github/workflows/x.sh", "; echo secrets", None])
def test_sample_workflow_path_is_bounded_and_restricted(environment, path):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    collection["runs"]["13:1"]["path"] = path
    assert compare_collection(collection)["classification"] == "inconclusive"


def test_dispatch_rejects_ref_movement_instead_of_replacing_plan(environment):
    environment["scenario"]["move_refs"] = True
    result = environment["invoke"]("dispatch")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "refs_moved"
    assert not any("POST" in call["args"] for call in _calls(environment))


@pytest.mark.parametrize("source", [{"type": "file", "encoding": "base64", "content": "bm8gaW5wdXRz"}, {"type": "dir", "encoding": "base64", "content": ""}, {"type": "file", "encoding": "base64", "content": "!!!!!"}])
def test_dry_run_rejects_wrong_workflow_input_contract(environment, source):
    environment["scenario"]["overrides"] = {PREFIX + "/contents/.github/workflows/pipeline-benchmark-experiment.yml?ref=" + BASELINE: source}
    result = environment["invoke"]()
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] in ("workflow_unavailable", "workflow_contract_mismatch")


@pytest.mark.parametrize("content,code", [("[]", "invalid_json"), ("{", "invalid_json"), ("x" * 1048577, "input_too_large"), (None, "input_unavailable")], ids=["list", "broken", "oversized", "missing"])
def test_compare_handles_malformed_bounded_input_without_traceback(environment, content, code):
    source = environment["tmp"] / "invalid.json"
    if content is not None: source.write_text(content)
    result = environment["invoke"]("compare", "--input", str(source))
    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["error"]["code"] == code


@pytest.mark.parametrize("change,code", [("version", "policy_mismatch"), ("repository", "wrong_repository"), ("empty_refs", "invalid_ref"), ("equal", "equal_refs"), ("scope", "unsupported_scope"), ("dry_run", "invalid_receipt"), ("url", "invalid_receipt"), ("timeout", "invalid_limits")])
def test_wait_validates_receipt_before_any_external_call(environment, change, code):
    from pipeline_toolkit.experiments.collect import wait_and_collect
    from pipeline_toolkit.experiments.contract import ExperimentError
    class NoNetwork:
        def authenticate(self): pytest.fail("Invalid receipt reached network")
    receipt = {"version": 1, "policy_version": POLICY, "repository": REPOSITORY, "baseline_ref": BASELINE, "candidate_ref": environment["scenario"]["candidate"], "scope": "ci", "workflow": "pipeline-benchmark-experiment.yml", "dry_run": False, "experiment_run": {"id": 900, "attempt": 1, "url": f"https://github.com/{REPOSITORY}/actions/runs/900"}}
    timeout = 10
    if change == "version": receipt["version"] = True
    elif change == "repository": receipt["repository"] = "fork/repo"
    elif change == "empty_refs": receipt["baseline_ref"] = ""
    elif change == "equal": receipt["candidate_ref"] = BASELINE
    elif change == "scope": receipt["scope"] = "cd"
    elif change == "dry_run": receipt["dry_run"] = True
    elif change == "url": receipt["experiment_run"]["url"] = "https://evil.invalid"
    elif change == "timeout": timeout = float("inf")
    with pytest.raises(ExperimentError) as caught: wait_and_collect(NoNetwork(), receipt, timeout=timeout)
    assert caught.value.code == code


def test_default_experiment_action_is_read_only_dry_run(environment, monkeypatch, capsys):
    from pipeline_toolkit.cli import main
    environment["tmp"].joinpath("scenario.json").write_text(json.dumps(environment["scenario"]))
    monkeypatch.chdir(environment["repo"])
    for key in ("PATH", "EXPERIMENT_SCENARIO", "EXPERIMENT_CALLS"): monkeypatch.setenv(key, environment["env"][key])
    assert main(["experiment"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert not any("POST" in call["args"] for call in _calls(environment))


def test_missing_grafana_link_preserves_comparison_verdict(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    for item in collection["manifest"]["observations"]: item.pop("grafana_url")
    result = compare_collection(collection)
    assert result["verdict"] == "approval_review"
    assert result["links"]["grafana"] == []


def test_failed_run_retains_diagnostic_links_and_absolute_delta_is_reported(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    assert compare_collection(collection)["comparison"]["absolute_delta"] == 16
    collection["runs"]["13:1"]["conclusion"] = "failure"
    result = compare_collection(collection)
    assert f"https://github.com/{REPOSITORY}/actions/runs/13" in result["links"]["actions"]
    assert f"https://github.com/{REPOSITORY}/actions/runs/13/artifacts/1013" in result["links"]["manifests"]


def test_invalid_url_credentials_are_not_echoed_in_replay_collection(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    collection["manifest"]["observations"][-1]["grafana_url"] = "https://user:DO_NOT_ECHO@fixture.grafana.net/d/ci"
    collection["runs"]["1:1"]["html_url"] = "https://user:DO_NOT_ECHO@github.com"
    result = compare_collection(collection)
    assert "DO_NOT_ECHO" not in json.dumps(result)
    assert result["classification"] == "inconclusive"
    assert compare_collection(result["collection"])["exclusions"] == result["exclusions"]


def test_relative_delta_numeric_overflow_is_inconclusive(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    for item in collection["manifest"]["observations"]:
        item["value"] = 1e-308 if item["side"] == "baseline" else 1e308
    result = compare_collection(collection)
    assert result["classification"] == "inconclusive"
    assert result["comparison"]["policy_outcome"] == "none"
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("expired", [True, False])
def test_sample_manifest_artifact_must_exist_and_belong_to_exact_run(environment, expired):
    receipt = _receipt(environment)
    environment["scenario"]["overrides"] = {PREFIX + "/actions/artifacts/1013": {"id": 1013, "name": "pipeline-experiment-sample-1", "expired": expired, "size_in_bytes": 1000, "workflow_run": {"id": 13 if expired else 999, "head_sha": environment["scenario"]["candidate"]}}}
    result = _json(environment["invoke"]("wait", "--receipt", str(receipt)))
    assert result["classification"] == "inconclusive"
    assert "sample_artifact_unavailable" in {item["reason"] for item in result["exclusions"]}


def test_replay_requires_sample_artifact_verification_snapshot(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    from pipeline_toolkit.experiments.contract import ExperimentError
    collection = _collection(environment)
    del collection["artifact_checks"]
    with pytest.raises(ExperimentError) as caught: compare_collection(collection)
    assert caught.value.code == "invalid_collection"


@pytest.mark.parametrize("suffix", ["\nINJECTED", "\rINJECTED", "\tINJECTED", "\x00", "\x7f", "\u2028INJECTED", "\u200b", "/../INJECTED", "/slug/INJECTED", "%0aINJECTED", "[INJECTED](javascript:alert(1))", "`INJECTED`", "<img src=x>", "\\INJECTED"], ids=["newline", "carriage_return", "tab", "nul", "delete", "unicode_newline", "zero_width", "traversal", "extra_segments", "encoded_newline", "markdown", "backticks", "html", "backslash"])
def test_grafana_link_rejects_controls_and_dashboard_path_injection(suffix):
    from pipeline_toolkit.experiments.contract import ExperimentError, safe_link
    with pytest.raises(ExperimentError) as caught:
        safe_link("https://fixture.grafana.net/d/ci" + suffix, grafana=True)
    assert caught.value.code == "invalid_link"


@pytest.mark.parametrize("url", ["\nhttps://fixture.grafana.net/d/ci", " https://fixture.grafana.net/d/ci", "https://fixture.grafana.net/d/", "https://fixture.grafana.net/d/..", "https://sub.fixture.grafana.net/d/ci"])
def test_grafana_link_rejects_noncanonical_tenant_and_dashboard_urls(url):
    from pipeline_toolkit.experiments.contract import ExperimentError, safe_link
    with pytest.raises(ExperimentError): safe_link(url, grafana=True)


def test_valid_dashboard_url_and_slug_render_as_autolink(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    from pipeline_toolkit.experiments.cli import render_summary
    collection = _collection(environment)
    collection["manifest"]["observations"][0]["grafana_url"] = "https://fixture.grafana.net/d/ci_uid/ci-trends"
    summary = render_summary(compare_collection(collection))
    assert "- grafana: <https://fixture.grafana.net/d/ci_uid/ci-trends>" in summary


def test_report_renderer_does_not_render_raw_link_or_exclusion_injection(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    from pipeline_toolkit.experiments.cli import render_summary
    result = compare_collection(_collection(environment))
    result["links"]["grafana"] = ["https://fixture.grafana.net/d/ci\n<img src=x onerror=INJECTED>"]
    result["exclusions"] = [{"reason": "invalid_observation", "side": "<img src=x onerror=INJECTED>\n```\n[click](javascript:alert(1))"}]
    summary = render_summary(result)
    assert "https://fixture.grafana.net/d/ci\n<img" not in summary
    assert "Exclusions:\n\n```json\n" in summary
    assert summary.count("\n```\n") == 1


@pytest.mark.parametrize("candidate_value", [0, 100])
def test_zero_baseline_has_explicit_inconclusive_policy(environment, candidate_value):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    for item in collection["manifest"]["observations"]: item["value"] = 0 if item["side"] == "baseline" else candidate_value
    result = compare_collection(collection)
    assert result["classification"] == "inconclusive"
    assert result["verdict"] == "inconclusive"
    assert result["comparison"]["reason"] == "zero_baseline"
    assert result["comparison"]["policy_outcome"] == "none"
    assert result["comparison"]["relative_delta"] is None


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_failure_rate_counts_authenticated_failures_without_measurement(environment, conclusion):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    collection["runs"]["13:1"]["conclusion"] = conclusion
    item = collection["manifest"]["observations"][-1]
    item["value"] = None
    item["environment_identity"] = None
    result = compare_collection(collection)
    assert result["failure_rate"] == pytest.approx(1 / 6)
    assert result["run_counts"] == {"authenticated_completed": 6, "failed": 1}
    diagnostic = next(entry for entry in result["exclusions"] if entry["run_id"] == 13)
    assert diagnostic["reason"] == "run_" + conclusion
    assert diagnostic["measurement_reason"] == "invalid_observation"
    assert f"https://github.com/{REPOSITORY}/actions/runs/13" in result["links"]["actions"]


def test_failure_rate_deduplicates_authenticated_runs_and_ignores_foreign_failures(environment):
    from pipeline_toolkit.experiments.compare import compare_collection
    collection = _collection(environment)
    collection["runs"]["13:1"]["conclusion"] = "failure"
    collection["manifest"]["observations"].append(copy.deepcopy(collection["manifest"]["observations"][-1]))
    assert compare_collection(collection)["failure_rate"] == pytest.approx(1 / 6)
    collection["runs"]["13:1"]["head_repository"]["full_name"] = "fork/repo"
    result = compare_collection(collection)
    assert result["failure_rate"] == 0
    assert result["run_counts"] == {"authenticated_completed": 5, "failed": 0}


def test_wait_counts_failed_run_even_when_sample_value_and_artifact_are_missing(environment):
    receipt = _receipt(environment)
    environment["scenario"]["runs"]["13"]["conclusion"] = "failure"
    environment["scenario"]["manifest"]["observations"][-1]["value"] = None
    result = _json(environment["invoke"]("wait", "--receipt", str(receipt)))
    assert result["failure_rate"] == pytest.approx(1 / 6)
    assert any(item["reason"] == "run_failure" for item in result["exclusions"])
