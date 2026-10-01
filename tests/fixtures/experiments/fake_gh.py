#!/usr/bin/env python3
"""Strict fake GitHub boundary; never makes a network request."""
import base64
import io
import hashlib
import json
import os
import sys
import time
import zipfile
from pathlib import Path

scenario_path = Path(os.environ["EXPERIMENT_SCENARIO"])
scenario = json.loads(scenario_path.read_text())
args = sys.argv[1:]
body = sys.stdin.read() if "--input" in args else None
with Path(os.environ["EXPERIMENT_CALLS"]).open("a") as log:
    log.write(json.dumps({"args": args, "body": json.loads(body) if body else None}) + "\n")
if scenario.get("sleep"):
    time.sleep(scenario["sleep"])
if scenario.get("oversized"):
    sys.stdout.write("X" * 2000000)
    sys.exit(0)
if scenario.get("stderr_secret"):
    print("token=DO_NOT_PRINT_THIS_SECRET", file=sys.stderr)
    sys.exit(1)
if args[:2] == ["auth", "status"]:
    sys.exit(1 if scenario.get("unauthenticated") else 0)
if args[:2] == ["attestation", "verify"]:
    assert Path(args[2]).read_bytes() == json.dumps(scenario["manifest"]).encode()
    assert args[args.index("--repo") + 1] == "YRootLab/OnMaru-backend"
    assert args[args.index("--signer-workflow") + 1] == "YRootLab/OnMaru-backend/.github/workflows/pipeline-benchmark-experiment.yml"
    assert args[args.index("--signer-digest") + 1] == scenario["baseline"]
    assert args[args.index("--source-digest") + 1] == scenario["baseline"]
    assert "--deny-self-hosted-runners" in args
    sys.exit(1 if scenario.get("attestation_failure") else 0)
if not args or args[0] != "api":
    sys.exit("Unexpected fake gh command")
endpoint = args[1]
method = args[args.index("--method") + 1]
repo = "YRootLab/OnMaru-backend"
prefix = "repos/" + repo
overrides = scenario.get("overrides", {})
if endpoint in overrides:
    response = overrides[endpoint]
elif endpoint.startswith(prefix + "/git/commits/"):
    response = {"sha": endpoint.rsplit("/", 1)[1], "tree": {"sha": "d" * 40}}
elif endpoint.startswith(prefix + "/contents/.github/pipeline-benchmark-test-plan.json?ref="):
    plan = b'{"scope":"ci","suite":"full-java"}'
    response = {"type": "file", "encoding": "base64", "content": base64.b64encode(plan).decode(), "sha": hashlib.sha1(b"blob " + str(len(plan)).encode() + b"\0" + plan).hexdigest()}
elif endpoint == "user":
    response = {"login": "fixture-user"}
elif endpoint == prefix:
    response = {"full_name": repo, "fork": False}
elif endpoint.startswith(prefix + "/git/ref/heads/"):
    ref = endpoint.split("/heads/", 1)[1]
    scenario["ref_reads"] = scenario.get("ref_reads", 0) + 1
    scenario_path.write_text(json.dumps(scenario))
    resolved = scenario["baseline"] if ref == "develop" else scenario["candidate"]
    if scenario.get("move_refs") and scenario["ref_reads"] > 2: resolved = "f" * 40
    response = {"ref": "refs/heads/" + ref, "object": {"type": "commit", "sha": resolved}}
elif endpoint == prefix + "/actions/workflows/pipeline-benchmark-experiment.yml":
    response = {"id": 700, "path": ".github/workflows/pipeline-benchmark-experiment.yml", "state": "active"}
elif endpoint.startswith(prefix + "/contents/.github/workflows/pipeline-benchmark-experiment.yml?ref="):
    workflow = "on:\n  workflow_dispatch:\n    inputs:\n      baseline_ref: {}\n      candidate_ref: {}\n      scope: {}\n      reason: {}\n"
    response = {"type": "file", "encoding": "base64", "content": base64.b64encode(workflow.encode()).decode()}
elif endpoint in (prefix + "/issues/555", prefix + "/issues/556"):
    response = {"state": scenario.get("gate_state", "closed")}
elif endpoint == prefix + "/actions/workflows/pipeline-benchmark-experiment.yml/dispatches" and method == "POST":
    response = {"workflow_run_id": 900, "run_url": "https://api.github.com/" + prefix + "/actions/runs/900", "html_url": "https://github.com/" + repo + "/actions/runs/900"}
elif endpoint == prefix + "/actions/runs/900/attempts/1":
    count = scenario.get("poll_count", 0)
    scenario["poll_count"] = count + 1
    scenario_path.write_text(json.dumps(scenario))
    response = scenario["parent"] | {"status": "in_progress" if count < scenario.get("pending_polls", 0) else "completed"}
elif endpoint == prefix + "/actions/runs/900/artifacts?per_page=100":
    response = {"total_count": 1, "artifacts": [{"id": 500, "name": "pipeline-experiment-manifest-1", "expired": False, "size_in_bytes": 10000, "workflow_run": {"id": 900, "head_sha": scenario["baseline"]}}]}
elif endpoint == prefix + "/actions/artifacts/500/zip":
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(scenario.get("archive_filename", "experiment-manifest.json"), json.dumps(scenario["manifest"]))
    sys.stdout.buffer.write(buffer.getvalue())
    sys.exit(0)
elif endpoint.startswith(prefix + "/actions/artifacts/"):
    artifact_id = int(endpoint.rsplit("/", 1)[1])
    sample_id = artifact_id - 1000
    response = {"id": artifact_id, "name": "pipeline-experiment-sample-1", "expired": False, "size_in_bytes": 1000, "workflow_run": {"id": sample_id, "head_sha": scenario["baseline"] if sample_id < 10 else scenario["candidate"]}}
elif endpoint.startswith(prefix + "/actions/runs/") and "/attempts/" in endpoint:
    run_id = endpoint.split("/runs/")[1].split("/")[0]
    response = scenario["runs"].get(run_id)
else:
    sys.exit("Unexpected fake gh endpoint: " + endpoint)
if response is None:
    sys.exit("Fake endpoint not found")
print(json.dumps(response))
