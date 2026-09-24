"""Deterministic dual-audience renderers for canonical report facts."""

from .model import ReportBundleInput, ReportFact, is_performance_eligible


def render_developer_draft(bundle: ReportBundleInput) -> str:
    """Render a fact-preserving technical report draft without performance inference."""
    eligible, ineligible = _partition_facts(bundle)
    return _document([
        f"# {bundle.title}",
        "",
        f"Observed at: {bundle.observed_at}",
        "",
        "## Summary",
        bundle.summary,
        "",
        "## Evidence quality",
        "Only facts with status `success` and `comparable=true` may support a performance claim.",
        "",
        "## Eligible evidence",
        *_fact_lines(eligible),
        "",
        "## Limitations",
        *_ineligible_lines(ineligible),
        *_plain_lines(bundle.limitations),
        "",
        "## Next steps",
        *_plain_lines(bundle.next_steps),
    ])


def render_easy_draft(bundle: ReportBundleInput) -> str:
    """Render a plain-language draft that never presents unqualified speed claims."""
    eligible, ineligible = _partition_facts(bundle)
    return _document([
        f"# {bundle.title}",
        "",
        "## 어떤 일이 있었나",
        "코드를 합치기 전 자동 확인에 걸린 시간을 살펴봤습니다.",
        bundle.summary,
        "",
        "## 확인된 수치",
        *_easy_fact_lines(eligible),
        "",
        "## 아직 성과로 말할 수 없는 부분",
        *_easy_ineligible_lines(ineligible),
        *_plain_lines(bundle.limitations),
        "",
        "## 다음에 확인할 일",
        *_plain_lines(bundle.next_steps),
    ])


def render_developer_prompt(bundle: ReportBundleInput) -> str:
    """Render a technical-audience prompt packet from validated facts only."""
    return _prompt_packet(
        bundle,
        audience_rule=(
            "Write for developers. Preserve values, units, statuses, comparability, and source links. "
            "A performance claim is allowed only when status is success and comparable is true "
            "(success and comparable)."
        ),
    )


def render_easy_prompt(bundle: ReportBundleInput) -> str:
    """Render a plain-language prompt packet from validated facts only."""
    return _prompt_packet(
        bundle,
        audience_rule=(
            "Write for non-developers in plain Korean. Explain CI as code checks before merging. "
            "Do not calculate or claim an improvement unless a fact is success and comparable. "
            "For every other fact, include the exact sentence: 개선 성과로 사용하지 않음."
        ),
    )


def _prompt_packet(bundle: ReportBundleInput, audience_rule: str) -> str:
    eligible, ineligible = _partition_facts(bundle)
    return _document([
        "# Report-writing prompt packet",
        "",
        "## Audience rule",
        audience_rule,
        "",
        "## Validated context",
        f"Title: {bundle.title}",
        f"Observed at: {bundle.observed_at}",
        f"Summary: {bundle.summary}",
        "",
        "## Eligible facts",
        *_fact_lines(eligible),
        "",
        "## Facts that cannot support improvement claims",
        *_ineligible_lines(ineligible),
        "",
        "## Limitations",
        *_plain_lines(bundle.limitations),
        "",
        "## Next steps",
        *_plain_lines(bundle.next_steps),
    ])


def _partition_facts(bundle: ReportBundleInput) -> tuple[tuple[ReportFact, ...], tuple[ReportFact, ...]]:
    ordered = tuple(sorted(bundle.facts, key=lambda fact: (fact.status, fact.name, fact.source_url)))
    return (
        tuple(fact for fact in ordered if is_performance_eligible(fact)),
        tuple(fact for fact in ordered if not is_performance_eligible(fact)),
    )


def _fact_lines(facts: tuple[ReportFact, ...]) -> list[str]:
    return [_fact_line(fact) for fact in facts] or ["- No eligible facts were supplied."]


def _easy_fact_lines(facts: tuple[ReportFact, ...]) -> list[str]:
    return [
        f"- {fact.name}: {_number(fact.value)} {fact.unit} "
        f"[실행 기록 보기]({fact.source_url})"
        for fact in facts
    ] or ["- 아직 비교 가능한 성공 측정값이 없습니다."]


def _easy_ineligible_lines(facts: tuple[ReportFact, ...]) -> list[str]:
    return [
        f"- {fact.name}: {_easy_ineligible_reason(fact)} "
        f"[실행 기록 보기]({fact.source_url})"
        for fact in facts
    ] or ["- 아직 성과로 말할 수 없는 측정값이 없습니다."]


def _easy_ineligible_reason(fact: ReportFact) -> str:
    if fact.status == "failed":
        return "이번 측정은 끝까지 성공하지 못해, 개선 성과로 사용하지 않음."
    if fact.status == "cancelled":
        return "이번 측정은 중간에 멈춰, 개선 성과로 사용하지 않음."
    if fact.status == "timeout":
        return "이번 측정은 정해진 시간 안에 끝나지 않아, 개선 성과로 사용하지 않음."
    if fact.status == "missing":
        return "이번 측정 기록을 찾을 수 없어, 개선 성과로 사용하지 않음."
    return "비교 조건이 같지 않아, 개선 성과로 사용하지 않음."


def _ineligible_lines(facts: tuple[ReportFact, ...]) -> list[str]:
    return [
        f"- {fact.name}: {_number(fact.value)} {fact.unit} "
        f"(status={fact.status}, comparable={str(fact.comparable).lower()}, source={fact.source_url}) "
        "— 개선 성과로 사용하지 않음."
        for fact in facts
    ] or ["- No ineligible facts were supplied."]


def _fact_line(fact: ReportFact) -> str:
    return (
        f"- {fact.name}: {_number(fact.value)} {fact.unit} "
        f"(status={fact.status}, comparable={str(fact.comparable).lower()}, source={fact.source_url})"
    )


def _plain_lines(entries: tuple[str, ...]) -> list[str]:
    return [f"- {entry}" for entry in entries]


def _number(value: float) -> str:
    return format(value, "g")


def _document(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"
