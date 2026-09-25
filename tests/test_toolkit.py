from datetime import datetime, timedelta, timezone
from pipeline_toolkit.collectors import collect_junit
from pipeline_toolkit.collectors.pytest import collect_pytest
from pipeline_toolkit.collectors.system import collect_time
from pipeline_toolkit.compare import compare_samples
from pipeline_toolkit.contracts import Artifact, BenchmarkRun, Evidence, Quality, Release, validate
from pipeline_toolkit.provenance import ArtifactManifest
from pipeline_toolkit.pipeline import Job, critical_path
from pipeline_toolkit.reports import render_html, render_json
from pipeline_toolkit.runners import Command, CommandRunner

def test_contract_rejects_unknown_schema():
    try: validate(Evidence("x", 1, "s", Quality.SUCCESS, "test", schema_version="9"))
    except ValueError: pass
    else: assert False

def test_command_runner_uses_arrays_and_redacts():
    result = CommandRunner({"/bin/echo"}, ("secret",)).run(Command("/bin/echo", ("token=secret",)))
    assert result.reason == "success" and "[REDACTED]" in result.stdout

def test_dag_parallel_work_and_wall_clock():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    jobs = [Job("a", started_at=t, completed_at=t+timedelta(seconds=5)), Job("b", ("a",), t+timedelta(seconds=5), t+timedelta(seconds=8)), Job("c", ("a",), t+timedelta(seconds=5), t+timedelta(seconds=9))]
    metrics = critical_path(jobs)
    assert metrics.work_seconds == 12 and metrics.wall_clock_seconds == 9 and metrics.critical_path_seconds == 9

def test_comparison_inconclusive_and_regression():
    assert compare_samples([1], [2])["status"] == "inconclusive"
    assert compare_samples([1, 1], [2, 2])["status"] == "regressed"

def test_render_is_deterministic_and_escaped():
    report = {"status": "success", "detail": "<script>"}
    assert render_json(report) == render_json(report)
    assert "&lt;script&gt;" in render_html(report)

def test_release_requires_immutable_identity():
    release = Release("org/repo", "v1", "a" * 40, "sha256:" + "b" * 64)
    validate(release)

def test_benchmark_run_and_manifest_are_traceable():
    release = Release("org/repo", "v1", "a" * 40, "sha256:" + "b" * 64)
    run = BenchmarkRun("run-1", release, "staging", "unit", "config", "runner", (Artifact("raw", "c" * 64, "raw"),))
    validate(run)
    manifest = ArtifactManifest.from_files({"fixture": "tests/fixtures/junit/success.xml"})
    assert manifest.artifacts[0].sha256

def test_collectors_preserve_quality_and_provenance():
    assert collect_junit("tests/fixtures/junit/success.xml")[0].quality == Quality.SUCCESS
    assert collect_pytest("tests/fixtures/pytest/output.txt")[0].value == .42
    assert collect_time("tests/fixtures/system/time.txt")[0].value == 1.25
