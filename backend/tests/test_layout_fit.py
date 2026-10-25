from app.pipeline.svg_designer import (
    DESIGN_WIDTH,
    PAD,
    _choose_layout,
    generate_legal_snaps_svg,
)
from app.schemas import InfographicContentPlan, TakeawayItem


def _long_plan() -> InfographicContentPlan:
    return InfographicContentPlan(
        headline="All India Judges Association versus Union of India and the Judicial Service",
        subtitle="Supreme Court | (2002) 4 SCC 247",
        header_icon="scales",
        overview_text=(
            "The Supreme Court upheld the constitutional legitimacy of the three-year practice "
            "requirement for Civil Judge Junior Division candidates, holding that practical "
            "experience is essential to judicial competence and directing every State and Union "
            "Territory to align its recruitment rules within six months."
        ),
        takeaways=[
            TakeawayItem(
                icon_type="gavel",
                description=(
                    "The Court held that substantial courtroom experience is necessary before a "
                    "law graduate can adjudicate independently in the subordinate judiciary."
                ),
            ),
            TakeawayItem(
                icon_type="court",
                description=(
                    "The judgment distinguishes academic knowledge from the practical skill of "
                    "conducting proceedings, recording evidence and drafting reasoned orders."
                ),
            ),
            TakeawayItem(
                icon_type="book",
                description=(
                    "Article 233(2) of the Constitution requires seven years of practice for senior "
                    "judicial posts, which informed the Court's view of the junior cadre."
                ),
            ),
            TakeawayItem(
                icon_type="prohibited",
                description=(
                    "States must amend their judicial service rules to restore the three-year "
                    "practice requirement and remove inconsistent eligibility standards."
                ),
            ),
        ],
        comparison_title="Provisions Engaged",
        comparison_old_title="STATUTORY PROVISIONS",
        comparison_old_items=[
            "Article 233(2) of the Constitution of India",
            "Article 14 of the Indian Constitution",
            "Article 16 of the Indian Constitution",
        ],
        comparison_new_title="COURT'S ANALYSIS",
        comparison_new_items=[
            "The Supreme Court affirmed the constitutional legitimacy of the experience rule.",
            "The Court emphasised practical courtroom skill over purely academic preparation.",
            "The Court relied on Article 233(2) and the Shetty Commission recommendations.",
            "The Court directed uniform recruitment standards across States and Union Territories.",
        ],
        comparison_footnote="Legal Snaps verified 8/8 claims against the retrieved source text.",
        footer_brand="Legal Snaps",
        footer_date="May 20, 2025",
        source_url="https://example.invalid/indian-judgment",
        publisher="Example Publisher",
        analysis_source="huggingface:Qwen/Qwen2.5-72B-Instruct",
    )


def test_long_plan_fits_portrait_and_square_canvases():
    plan = _long_plan()
    for width, height in ((1080, 1350), (1200, 1200), (800, 1240)):
        dh = DESIGN_WIDTH * (height / width)
        layout = _choose_layout(plan, dh, 64, True, DESIGN_WIDTH - 2 * PAD)
        limit = dh - 64 - 34
        assert layout.total_h <= limit, (width, height, layout.spec, layout.total_h, limit)

        svg = generate_legal_snaps_svg(plan, width=width, height=height)
        assert f'viewBox="0 0 {DESIGN_WIDTH}' in svg


def test_landscape_degrades_without_overflowing_its_footer():
    plan = _long_plan()
    width, height = 1200, 675
    dh = DESIGN_WIDTH * (height / width)
    layout = _choose_layout(plan, dh, 44, True, DESIGN_WIDTH - 2 * PAD)
    limit = dh - 44 - 34
    # Landscape omits the comparison column at the compact spec so the rest fits.
    assert layout.has_comparison is False or layout.total_h <= limit
    svg = generate_legal_snaps_svg(plan, width=width, height=height)
    assert "Legal Snaps" in svg
