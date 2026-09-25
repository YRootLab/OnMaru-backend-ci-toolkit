from pathlib import Path


def test_readme_explains_the_consumer_boundary_and_pinned_module_workflow_call():
    text = Path("README.md").read_text()

    assert "OnMaru-backend가 소유하는 것" in text
    assert "Toolkit이 제공하는 것" in text
    assert "module-benchmark.yml@<40-character-toolkit-commit-sha>" in text
    assert "toolkit_ref: <40-character-toolkit-commit-sha>" in text
    assert "serial-baseline.json" in text
    assert "런타임 의존성" in text


def test_readme_preserves_comparable_measurement_and_artifact_safety_rules():
    text = Path("README.md").read_text()

    assert "세 번" in text
    assert "runner image" in text
    assert "CPU·메모리" in text
    assert "자격 증명" in text
    assert "0으로 바꾸지 않는다" in text
