import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_pipeline_docs", ROOT / "scripts" / "check_pipeline_docs.py")
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


def test_slugify_matches_github_style_including_hangul():
    assert checker.slugify("Grafana에서 Tempo, Actions까지의 탐색") == "grafana에서-tempo-actions까지의-탐색"
    assert checker.slugify("partial, unavailable, inconclusive, failure의 구분") == "partial-unavailable-inconclusive-failure의-구분"


def test_repository_documentation_passes_the_drift_and_link_check():
    errors, _ = checker.check_all(ROOT, require_d2=False)
    assert errors == []


def test_detects_broken_link_missing_anchor_missing_path_and_missing_alt(tmp_path):
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    (tmp_path / "docs" / "diagrams").mkdir(parents=True)
    (tmp_path / "docs" / "architecture" / "a.md").write_text(
        "# Title\n\n[missing](nope.md)\n[bad anchor](b.md#absent)\n[ok](b.md#real-heading)\n"
        "`src/does/not/exist.py`\n![](../diagrams/x.svg)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "architecture" / "b.md").write_text("# Real heading\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")
    errors = []
    checker.check_markdown(tmp_path, tmp_path / "docs" / "architecture" / "a.md", errors)
    joined = "\n".join(errors)
    assert "broken link: nope.md" in joined
    assert "missing anchor: b.md#absent" in joined
    assert "referenced path does not exist: src/does/not/exist.py" in joined
    assert "image without alt text" in joined
    assert "real-heading" not in joined


def test_fenced_code_is_ignored(tmp_path):
    doc = tmp_path / "README.md"
    doc.write_text("# Root\n\n```\n[broken](nope.md)\n```\n", encoding="utf-8")
    errors = []
    checker.check_markdown(tmp_path, doc, errors)
    assert errors == []


def test_d2_link_targets_must_exist(tmp_path):
    diagrams = tmp_path / "docs" / "diagrams"
    diagrams.mkdir(parents=True)
    source = diagrams / "x.d2"
    source.write_text('a: "A" { link: ../../missing/file.py }\n', encoding="utf-8")
    errors = []
    checker.check_d2_links(tmp_path, source, errors)
    assert any("link target missing: ../../missing/file.py" in e for e in errors)
