from pathlib import Path

import pytest

from pipeline_toolkit.report_bundle.write import plan_outputs, write_outputs


def test_plan_outputs_uses_tracked_and_ignored_defaults(tmp_path: Path) -> None:
    plan = plan_outputs(tmp_path, "2026-09-24", "ci-observation", "both", None)

    assert plan.developer_markdown == tmp_path / "docs/reports/2026-09-24-ci-observation-detailed.md"
    assert plan.easy_markdown == tmp_path / "docs/reports/easy/2026-09-24-ci-observation-easy.md"
    assert plan.developer_prompt == tmp_path / "docs/reports/prompts/generated/2026-09-24-ci-observation-detailed-prompt.md"
    assert plan.easy_prompt == tmp_path / "docs/reports/easy/prompts/generated/2026-09-24-ci-observation-easy-prompt.md"


def test_plan_outputs_selects_requested_audience(tmp_path: Path) -> None:
    plan = plan_outputs(tmp_path, "2026-09-24", "ci-observation", "easy", None)

    assert plan.developer_markdown is None
    assert plan.developer_prompt is None
    assert plan.easy_markdown == tmp_path / "docs/reports/easy/2026-09-24-ci-observation-easy.md"
    assert plan.easy_prompt == tmp_path / "docs/reports/easy/prompts/generated/2026-09-24-ci-observation-easy-prompt.md"


def test_plan_outputs_rejects_escape_slug_and_easy_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        plan_outputs(tmp_path, "2026-09-24", "../escape", "easy", None)

    with pytest.raises(ValueError):
        plan_outputs(tmp_path, "2026-09-24", "ci-observation", "easy", tmp_path / "../escape")


def test_write_outputs_writes_atomically_and_blocks_existing_files(tmp_path: Path) -> None:
    destination = tmp_path / "docs/reports/result.md"
    plan = plan_outputs(tmp_path, "2026-09-24", "ci-observation", "developer", None)
    contents = {destination: "first report\n"}

    assert write_outputs(plan, contents, overwrite=False) == (destination,)
    assert destination.read_text(encoding="utf-8") == "first report\n"
    assert not destination.with_suffix(".md.tmp").exists()

    with pytest.raises(FileExistsError):
        write_outputs(plan, {destination: "replacement\n"}, overwrite=False)

    assert write_outputs(plan, {destination: "replacement\n"}, overwrite=True) == (destination,)
    assert destination.read_text(encoding="utf-8") == "replacement\n"


def test_write_outputs_rejects_destination_outside_root(tmp_path: Path) -> None:
    plan = plan_outputs(tmp_path, "2026-09-24", "ci-observation", "developer", None)

    with pytest.raises(ValueError):
        write_outputs(plan, {tmp_path.parent / "escape.md": "unsafe\n"}, overwrite=False)
