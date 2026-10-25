from app.pipeline.content_planner import (
    COMPARISON_LIMIT,
    _short_phrase,
    plan_infographic_content,
)
from app.schemas import LegalRecord, SourceMetadata, ValidationSummary


def _record(**overrides) -> LegalRecord:
    data = dict(
        article_title="Three Years to the Bench",
        case_name="All India Judges Association vs Union of India",
        court_or_tribunal="Supreme Court",
        citation="(2002) 4 SCC 247",
        judgment_date="May 20, 2025",
        is_court_judgment=True,
        relevant_statutes=[
            "Article 233(2) of the Constitution of India",
            "Article 14 of the Indian Constitution",
            "Article 16 of the Indian Constitution",
        ],
        material_facts=[
            "Historically, law graduates could take judicial service exams immediately after graduation."
        ],
        questions_or_issues=[
            "Is the three-year practice requirement constitutional?",
            "Does a lack of uniformity between States invalidate the rule?",
        ],
        legal_reasoning=[
            "The Supreme Court upheld the constitutional legitimacy of the three-year practice requirement.",
            "The Court emphasised practical courtroom experience for judicial officers.",
            "The Court relied on Article 233(2) of the Constitution.",
            "The Court directed States to align their recruitment rules.",
        ],
        holding_or_operative_order=(
            "The Supreme Court upheld the constitutional legitimacy of the three-year practice "
            "requirement for Civil Judge candidates and directed States to align their rules."
        ),
        practical_implications=[
            "States must amend their judicial service rules to restore the practice requirement.",
            "The ruling aims to improve the competence of the subordinate judiciary.",
        ],
    )
    data.update(overrides)
    return LegalRecord(**data)


def _validation(total: int = 8, verified: int = 8) -> ValidationSummary:
    return ValidationSummary(
        total_claims=total,
        verified_claims=verified,
        unverified_claims=total - verified,
    )


def test_takeaways_are_four_declarative_points_without_the_holding_repeat():
    plan = plan_infographic_content(_record(), _validation())

    assert 3 <= len(plan.takeaways) <= 4
    descriptions = [t.description for t in plan.takeaways]
    assert not any("?" in text for text in descriptions)
    assert not any(text.lower().startswith("is ") for text in descriptions)
    assert descriptions[0] != _record().holding_or_operative_order
    assert all(len(text) <= 158 for text in descriptions)


def test_subtitle_is_a_hook_and_citation_moves_to_the_meta_line():
    plan = plan_infographic_content(_record(), _validation())

    assert plan.subtitle == "Three Years to the Bench"
    assert "(2002) 4 SCC 247" in plan.meta_line
    assert "May 20, 2025" in plan.meta_line
    assert plan.footer_date == "May 20, 2025"


def test_publisher_seo_tail_is_removed():
    source = SourceMetadata(
        title="Article",
        url="https://example.invalid/article",
        publisher="Qualegal Advocates & Solicitors | Best Supreme Court Lawyers in Delhi",
        retrieval_time="2026-10-25T00:00:00+00:00",
    )
    plan = plan_infographic_content(_record(), _validation(), source)

    assert plan.publisher == "Qualegal Advocates & Solicitors"


def test_comparison_items_end_on_a_clause_boundary_without_an_ellipsis():
    long_item = (
        "The Court recognised discrepancies among different State Judicial Service Regulations, "
        "and urged alignment to ensure consistent recruitment across the country."
    )
    first = _short_phrase(long_item, COMPARISON_LIMIT)

    assert first == (
        "Recognised discrepancies among different State Judicial Service Regulations"
    )
    assert len(first) <= 100
    assert "…" not in first


def test_comparison_sentence_keeps_a_short_complete_clause():
    item = (
        "The requirement is a reasonable restriction that serves the public interest "
        "and enhances judicial competency."
    )

    assert _short_phrase(item, COMPARISON_LIMIT) == (
        "The requirement is a reasonable restriction"
    )


def test_comparison_does_not_end_on_an_unqualified_right():
    item = "Article 23 prohibits forced labor and ensures the right to life with dignity."

    assert _short_phrase(item, COMPARISON_LIMIT) == "Article 23 prohibits forced labor"


def test_comparison_questions_are_kept_whole():
    question = (
        "Is the three-year practice requirement for Civil Judge (Junior Division) "
        "candidates constitutional?"
    )
    plan = plan_infographic_content(
        _record(
            relevant_statutes=[],
            questions_or_issues=[question, "Does a lack of uniformity invalidate it?"],
        ),
        _validation(),
    )

    assert plan.comparison_old_items[0] == question
    assert all(item.endswith("?") for item in plan.comparison_old_items)


def test_comparison_values_are_capped_at_three_per_column():
    plan = plan_infographic_content(
        _record(
            relevant_statutes=[f"Article {n} of the Constitution" for n in range(1, 6)],
            legal_reasoning=[f"Reason number {n} explains the Court's approach." for n in range(1, 6)],
        ),
        _validation(),
    )

    assert len(plan.comparison_old_items) == 3
    assert len(plan.comparison_new_items) == 3


def test_takeaway_icons_only_use_the_prohibition_mark_for_prohibitions():
    plan = plan_infographic_content(_record(), _validation())

    assert "prohibited" not in [item.icon_type for item in plan.takeaways]
