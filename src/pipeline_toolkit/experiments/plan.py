from __future__ import annotations

import base64
import re
from pathlib import Path

import yaml

from .contract import ExperimentError, POLICY_VERSION, REPOSITORY, WORKFLOW, WORKFLOW_PATH, positive_id, require, run_url, scope, sha

PREFIX = "repos/" + REPOSITORY


def _local_identity(github, root):
    remote = github.git(root, "remote", "get-url", "origin")
    allowed = (f"https://github.com/{REPOSITORY}", f"https://github.com/{REPOSITORY}.git", f"git@github.com:{REPOSITORY}", f"git@github.com:{REPOSITORY}.git", f"ssh://git@github.com/{REPOSITORY}.git")
    require(remote in allowed, "wrong_repository")
    require(not github.git(root, "status", "--porcelain=v1", "--untracked-files=all"), "dirty_tree")
    branch = github.git(root, "branch", "--show-current")
    require(re.fullmatch(r"feature/[A-Za-z0-9][A-Za-z0-9._/-]*", branch) is not None and ".." not in branch and "//" not in branch, "feature_branch_required")
    return branch, sha(github.git(root, "rev-parse", "HEAD"))


def _remote_ref(github, branch):
    document = github.api(PREFIX + "/git/ref/heads/" + branch)
    require(document.get("ref") == "refs/heads/" + branch and isinstance(document.get("object"), dict) and document["object"].get("type") == "commit", "invalid_ref")
    return sha(document["object"].get("sha"))


def create_plan(github, root: Path, requested_scope: str, reason: str) -> dict:
    scope(requested_scope)
    require(isinstance(reason, str) and 1 <= len(reason.strip()) <= 512 and not any(ord(char) < 32 for char in reason), "invalid_reason")
    branch, candidate = _local_identity(github, root)
    actor = github.authenticate()
    baseline = _remote_ref(github, "develop")
    require(_remote_ref(github, branch) == candidate, "candidate_not_pushed")
    require(baseline != candidate, "equal_refs")
    workflow = github.api(PREFIX + "/actions/workflows/" + WORKFLOW)
    require(workflow.get("state") == "active" and workflow.get("path") == WORKFLOW_PATH, "workflow_unavailable")
    workflow_id = positive_id(workflow.get("id"))
    source = github.api(PREFIX + "/contents/" + WORKFLOW_PATH + "?ref=" + baseline)
    try:
        require(source.get("type") == "file" and source.get("encoding") == "base64", "workflow_unavailable")
        document = yaml.load(base64.b64decode(source["content"], validate=False), Loader=yaml.BaseLoader)
        inputs = document["on"]["workflow_dispatch"]["inputs"]
        require(all(key in inputs for key in ("baseline_ref", "candidate_ref", "scope", "reason")), "workflow_contract_mismatch")
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        if isinstance(exc, ExperimentError):
            raise
        raise ExperimentError("workflow_contract_mismatch") from exc
    payload = {"ref": "develop", "inputs": {"baseline_ref": baseline, "candidate_ref": candidate, "scope": requested_scope, "reason": reason}}
    return {"version": 1, "policy_version": POLICY_VERSION, "repository": REPOSITORY, "actor": actor, "branch": branch, "baseline_ref": baseline, "candidate_ref": candidate, "scope": requested_scope, "workflow_id": workflow_id, "workflow": WORKFLOW, "required_samples": 3, "threshold": 0.15, "dry_run": True, "dispatch_payload": payload, "integration_gate": ["https://github.com/" + REPOSITORY + "/issues/555", "https://github.com/" + REPOSITORY + "/issues/556"]}


def dispatch(github, root: Path, requested_scope: str, reason: str, *, bootstrap_integration: bool = False) -> dict:
    plan = create_plan(github, root, requested_scope, reason)
    gate_states = {}
    for issue in (555, 556):
        state = github.api(PREFIX + f"/issues/{issue}").get("state")
        require(state in ("open", "closed"), "integration_gate_unavailable")
        gate_states[str(issue)] = state
    require(gate_states["555"] == "closed", "integration_gate_open")
    if bootstrap_integration:
        require(gate_states["556"] == "open", "integration_bootstrap_not_required")
    else:
        require(gate_states["556"] == "closed", "integration_gate_open")
    # Do not silently replace an approved immutable plan if a branch moved.
    branch, candidate = _local_identity(github, root)
    require(branch == plan["branch"] and candidate == plan["candidate_ref"] and _remote_ref(github, "develop") == plan["baseline_ref"] and _remote_ref(github, branch) == candidate, "refs_moved")
    response = github.api(PREFIX + "/actions/workflows/" + WORKFLOW + "/dispatches", payload=plan["dispatch_payload"])
    run_id = positive_id(response.get("workflow_run_id"))
    require(response.get("html_url") == run_url(run_id), "dispatch_identity_missing")
    return dict(
        plan,
        dry_run=False,
        integration_gate_status={"bootstrap": bootstrap_integration, "issues": gate_states},
        experiment_run={"id": run_id, "attempt": 1, "url": run_url(run_id)},
    )
