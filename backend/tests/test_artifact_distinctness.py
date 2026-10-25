"""
Proves that distinct legal records produce distinct infographics at the deterministic
layer (planner + SVG), with no network or API access.

This is the offline counterpart to tests/test_live_integration.py: it cannot prove a real
source was fetched, but it does prove nothing in the rendering path reuses another
article's content.
"""
from app.schemas import (
    ClaimValidation,
    InfographicContentPlan,
    LegalRecord,
    SourceMetadata,
    ValidationSummary,
)
from app.pipeline.content_planner import plan_infographic_content
from app.pipeline.svg_designer import generate_legal_snaps_svg


def build_record(**overrides) -> LegalRecord:
    base = dict(
        article_title="Placeholder",
        court_or_tribunal="Supreme Court of India",
        case_name="Placeholder v. Placeholder",
        citation="(2024) 1 SCC 1",
        judgment_date="1 January 2024",
        relevant_statutes=["Article 14 of the Constitution"],
        material_facts=["A fact unique to this record."],
        questions_or_issues=["Whether the measure is proportionate."],
        legal_reasoning=["The measure failed the proportionality test."],
        holding_or_operative_order="The impugned rule is struck down.",
        exact_quotations=[],
        practical_implications=["Departments must redraft the rule."],
        is_court_judgment=True,
        analysis_source="huggingface:Qwen/Qwen2.5-72B-Instruct",
    )
    base.update(overrides)
    return LegalRecord(**base)


def build_source(title: str, url: str) -> SourceMetadata:
    return SourceMetadata(
        title=title, url=url, publisher="indiankanoon.org",
        retrieval_time="2026-10-24T00:00:00Z", text_length=12000,
    )


def validate_all(verified: bool = True) -> ValidationSummary:
    return ValidationSummary(
        total_claims=3, verified_claims=3 if verified else 0,
        unverified_claims=0 if verified else 3,
        has_critical_unverified=not verified,
        claims=[
            ClaimValidation(claim_id="holding", claim_text="x", claim_type="holding", verified=verified)
        ],
    )


SUKANYA = build_record(
    article_title="Sukanya Shantha v. Union of India",
    case_name="Sukanya Shantha v. Union of India",
    citation="(2024) SCC OnLine SC 1520",
    judgment_date="3 October 2024",
    relevant_statutes=["Article 14 of the Constitution", "Article 21 of the Constitution"],
    material_facts=["Caste-based division of labour was enforced inside prison barracks."],
    questions_or_issues=["Whether caste-based segregation in prisons violates Articles 14, 15 and 21."],
    legal_reasoning=["Segregation by caste perpetuates stigma and offends human dignity."],
    holding_or_operative_order="Caste-based assignment of prison labour is unconstitutional.",
    practical_implications=["Prison manuals must be revised within six months."],
)

PUTTASWAMY = build_record(
    article_title="Justice K.S. Puttaswamy (Retd.) v. Union of India",
    case_name="Justice K.S. Puttaswamy (Retd.) v. Union of India",
    citation="(2017) 10 SCC 1",
    judgment_date="24 August 2017",
    relevant_statutes=["Article 21 of the Constitution"],
    material_facts=["A nine-judge bench considered informational privacy."],
    questions_or_issues=["Whether the right to privacy is a fundamental right."],
    legal_reasoning=["Privacy is intrinsic to life and personal liberty."],
    holding_or_operative_order="The right to privacy is protected under Article 21.",
    practical_implications=["State action must satisfy the proportionality standard."],
)


def render(record: LegalRecord, url: str) -> str:
    plan = plan_infographic_content(
        record, validate_all(), build_source(record.article_title, url)
    )
    return generate_legal_snaps_svg(plan, width=800, height=1240)


def test_two_articles_render_factually_different_infographics():
    sukanya_svg = render(SUKANYA, "https://indiankanoon.org/doc/sukanya")
    puttaswamy_svg = render(PUTTASWAMY, "https://indiankanoon.org/doc/91938676")

    assert sukanya_svg != puttaswamy_svg

    assert "SUKANYA SHANTHA" in sukanya_svg.upper()
    assert "PUTTASWAMY" in puttaswamy_svg.upper()

    # Neither article's distinctive content leaks into the other's artifact.
    assert "PUTTASWAMY" not in sukanya_svg.upper()
    assert "SUKANYA" not in puttaswamy_svg.upper()
    assert "prison labour" in sukanya_svg.lower() or "caste" in sukanya_svg.lower()
    assert "privacy" in puttaswamy_svg.lower()

    assert "2017" in puttaswamy_svg
    assert "(2024) SCC ONLINE SC 1520" in sukanya_svg.upper()


def test_artifacts_record_their_own_source_and_analysis_provenance():
    svg = render(PUTTASWAMY, "https://indiankanoon.org/doc/91938676")
    assert "indiankanoon.org" in svg
    assert "huggingface:Qwen/Qwen2.5-72B-Instruct" in svg


def test_plan_defaults_contain_no_article_specific_text():
    """The schema previously defaulted to one article's headlines, which could surface
    in any infographic whose planner did not set a field."""
    plan = InfographicContentPlan(headline="Any", overview_text="Any")
    assert plan.comparison_title == ""
    assert plan.comparison_old_title == ""
    assert plan.footer_date is None
    assert "Criminal Laws" not in plan.model_dump_json()


def test_unverified_claims_are_flagged_on_the_artifact():
    plan = plan_infographic_content(
        PUTTASWAMY, validate_all(verified=False), build_source("Puttaswamy", "https://example.test/p")
    )
    assert plan.verification_note is not None
    svg = generate_legal_snaps_svg(plan)
    assert "could not be verified" in svg


def test_infographic_without_a_comparison_section_still_renders():
    sparse = build_record(
        case_name="Sparse v. Record",
        relevant_statutes=[],
        questions_or_issues=[],
        material_facts=[],
        practical_implications=[],
        legal_reasoning=[],
        holding_or_operative_order="The appeal is dismissed.",
    )
    svg = render(sparse, "https://example.test/sparse")
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
