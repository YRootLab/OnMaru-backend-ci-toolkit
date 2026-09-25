from pipeline_toolkit.collectors.pytest import collect_pytest_xml
from pipeline_toolkit.collectors.docker import collect_buildkit
from pipeline_toolkit.contracts import Quality

def test_pytest_xml_exposes_counts_and_slowest_tests():
    evidence = collect_pytest_xml("tests/fixtures/pytest/results.xml")
    assert evidence.quality == Quality.SUCCESS
    assert evidence.value == 2.5
    assert "tests=2" in evidence.warnings
    assert "slowest=test_slow:2.0" in evidence.warnings

def test_buildkit_missing_duration_is_partial_not_success():
    evidence = collect_buildkit("tests/fixtures/docker/partial.json")[0]
    assert evidence.quality == Quality.PARTIAL
    assert "cache_hit=true" in evidence.warnings
