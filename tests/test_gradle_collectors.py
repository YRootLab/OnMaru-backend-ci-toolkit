from pipeline_toolkit.collectors.gradle import collect_gradle_profiler
from pipeline_toolkit.collectors.junit import collect_junit
from pipeline_toolkit.collectors.pytest import collect_pytest_xml
from pipeline_toolkit.collectors.system import collect_time
from pipeline_toolkit.contracts import Quality

def test_gradle_profiler_preserves_duration_cpu_memory_and_provenance():
    evidence = collect_gradle_profiler("tests/fixtures/gradle/profile.csv")[0]
    assert evidence.quality == Quality.SUCCESS
    assert evidence.value == 1250
    assert "cpu_ms=900" in evidence.warnings
    assert "peak_memory_mb=256" in evidence.warnings
    assert evidence.raw_artifact.uri.endswith("profile.csv")

def test_gradle_missing_and_malformed_inputs_are_explicit():
    assert collect_gradle_profiler("missing.csv")[0].quality == Quality.MISSING
    assert collect_gradle_profiler("tests/fixtures/gradle/malformed.csv")[0].quality == Quality.INVALID

def test_system_metrics_preserve_cpu_when_available():
    evidence = collect_time("tests/fixtures/system/time-full.txt")
    assert any("cpu_user_seconds=2.5" in item.warnings for item in evidence)

def test_junit_and_pytest_expose_counts_failures_and_skips():
    junit = collect_junit("tests/fixtures/junit/success.xml")[0]
    pytest = collect_pytest_xml("tests/fixtures/pytest/results.xml")
    assert "tests=2" in junit.warnings and "failures=0" in junit.warnings and "skipped=1" in junit.warnings
    assert "failures=0" in pytest.warnings and "skipped=0" in pytest.warnings
