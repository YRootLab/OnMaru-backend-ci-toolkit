from pathlib import Path


REPORT = Path("docs/reports/2026-09-26-onmaru-backend-ci-cd-parallel-guide.md")


def test_pipeline_report_separates_current_serial_ci_from_the_target_parallel_design():
    text = REPORT.read_text()

    assert "현재 required check로 운영 중인 것은 직렬 `verify`" in text
    assert "목표 구조" in text
    assert "#364" in text
    assert "#365" in text
    assert "실제 개선률을 아직 선언하지 않는다" in text


def test_pipeline_report_states_measurement_limits_and_keeps_visualization_compact():
    text = REPORT.read_text()

    assert "동일 commit SHA" in text
    assert "CPU·메모리(RSS)는 GitHub Actions API만으로 수집할 수 없다" in text
    assert "0으로 기록하지 않는다" in text
    assert "CD lead time" in text
    assert text.count("```mermaid") == 1
