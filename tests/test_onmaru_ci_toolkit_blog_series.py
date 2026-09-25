from pathlib import Path


SERIES = {
    "foundations": Path("docs/reports/2026-09-26-onmaru-ci-series-01-actions-ci-cd-tests.md"),
    "boundary": Path("docs/reports/2026-09-26-onmaru-ci-series-02-reusable-workflow-boundary.md"),
    "rollout": Path("docs/reports/2026-09-26-onmaru-ci-series-03-parallel-rollout-evidence.md"),
}


def test_blog_series_covers_the_complete_cross_repository_pipeline_story():
    texts = {name: path.read_text() for name, path in SERIES.items()}

    assert "GitHub Actions" in texts["foundations"]
    assert "CI" in texts["foundations"] and "CD" in texts["foundations"]
    assert "40자리" in texts["boundary"]
    assert "SHA-1" in texts["boundary"]
    assert "reusable workflow" in texts["boundary"]
    assert "fan-out" in texts["rollout"]
    assert "fan-in" in texts["rollout"]
    assert "shadow check" in texts["rollout"]
    assert "400초" in texts["rollout"]


def test_blog_series_keeps_current_and_target_pipeline_states_honest():
    rollout = SERIES["rollout"].read_text()
    boundary = SERIES["boundary"].read_text()

    assert "현재 required check는 직렬 `verify`" in rollout
    assert "아직 공식 개선률을 선언하지 않는다" in rollout
    assert "서비스 소스와 배포 자격 증명은 OnMaru-backend" in boundary
    assert "CPU·메모리(RSS)" in rollout
    assert sum(path.read_text().count("```mermaid") for path in SERIES.values()) >= 3
