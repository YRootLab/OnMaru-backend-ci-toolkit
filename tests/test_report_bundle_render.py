from pipeline_toolkit.report_bundle import ReportBundleInput, ReportFact
from pipeline_toolkit.report_bundle.render import (
    render_developer_draft,
    render_developer_prompt,
    render_easy_draft,
    render_easy_prompt,
)


def _bundle() -> ReportBundleInput:
    return ReportBundleInput(
        title="OnMaru CI observation",
        observed_at="2026-09-24",
        summary="Measured the current CI path.",
        facts=(
            ReportFact(
                name="parallel candidate",
                value=316.41,
                unit="seconds",
                status="failed",
                source_url="https://github.com/org/repo/actions/runs/2",
                comparable=True,
            ),
            ReportFact(
                name="serial baseline",
                value=454,
                unit="seconds",
                status="success",
                source_url="https://github.com/org/repo/actions/runs/1",
                comparable=True,
            ),
        ),
        limitations=("The parallel candidate failed.",),
        next_steps=("Collect three successful same-SHA samples.",),
    )


def test_easy_draft_uses_plain_language_and_marks_failed_candidate_as_unconfirmed():
    rendered = render_easy_draft(_bundle())

    assert "코드를 합치기 전 자동 확인" in rendered
    assert "개선 성과로 사용하지 않음" in rendered
    assert "이번 측정은 끝까지 성공하지 못해" in rendered
    assert "status=failed" not in rendered
    assert "comparable=true" not in rendered
    assert "[실행 기록 보기](https://github.com/org/repo/actions/runs/1)" in rendered
    assert "21% 빨라졌다" not in rendered


def test_developer_prompt_preserves_source_links_and_comparability_rule():
    rendered = render_developer_prompt(_bundle())

    assert "https://github.com/org/repo/actions/runs/1" in rendered
    assert "success and comparable" in rendered


def test_renderers_sort_facts_and_keep_ineligible_facts_out_of_improvement_evidence():
    base = _bundle()
    bundle = ReportBundleInput(
        title=base.title,
        observed_at=base.observed_at,
        summary=base.summary,
        facts=base.facts + (
            ReportFact(
                name="cancelled candidate",
                value=300,
                unit="seconds",
                status="failed",
                source_url="https://github.com/org/repo/actions/runs/3",
                comparable=False,
            ),
        ),
        limitations=base.limitations,
        next_steps=base.next_steps,
    )

    developer = render_developer_draft(bundle)
    easy = render_easy_draft(bundle)
    easy_prompt = render_easy_prompt(bundle)

    assert developer.index("cancelled candidate") < developer.index("parallel candidate")
    assert "serial baseline: 454 seconds" in developer
    assert "parallel candidate: 316.41 seconds" in developer
    assert "parallel candidate" in developer.split("## Limitations", 1)[1]
    assert "parallel candidate" not in developer.split("## Eligible evidence", 1)[1].split("## Limitations", 1)[0]
    assert "개선 성과로 사용하지 않음" in easy
    assert "API key" not in easy_prompt


def test_successful_but_non_comparable_fact_is_not_easy_improvement_evidence():
    base = _bundle()
    non_comparable = ReportFact(
        name="different SHA candidate",
        value=316.41,
        unit="seconds",
        status="success",
        source_url="https://github.com/org/repo/actions/runs/4",
        comparable=False,
    )
    bundle = ReportBundleInput(
        title=base.title,
        observed_at=base.observed_at,
        summary=base.summary,
        facts=(base.facts[1], non_comparable),
        limitations=base.limitations,
        next_steps=base.next_steps,
    )

    rendered = render_easy_draft(bundle)

    confirmed, limitations = rendered.split("## 아직 성과로 말할 수 없는 부분", 1)
    assert "different SHA candidate" not in confirmed
    assert "different SHA candidate" in limitations
    assert "개선 성과로 사용하지 않음" in limitations
    assert "comparable=false" not in rendered


def test_easy_draft_escapes_markdown_structure_in_evidence_link_destination():
    base = _bundle()
    unsafe_url = "https://evidence.example/run)[untrusted-link](https://attacker.example)"
    bundle = ReportBundleInput(
        title=base.title,
        observed_at=base.observed_at,
        summary=base.summary,
        facts=(
            ReportFact(
                name="unsafe evidence",
                value=454,
                unit="seconds",
                status="success",
                source_url=unsafe_url,
                comparable=True,
            ),
        ),
        limitations=base.limitations,
        next_steps=base.next_steps,
    )

    rendered = render_easy_draft(bundle)

    assert "[untrusted-link](https://attacker.example)" not in rendered
    assert (
        "[실행 기록 보기](https://evidence.example/run%29%5Buntrusted-link%5D%28https://attacker.example%29)"
        in rendered
    )
