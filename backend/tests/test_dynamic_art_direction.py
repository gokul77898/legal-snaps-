"""Regression coverage for article-specific infographic art direction.

These tests guard the two things the art-direction revamp must never lose: every legal
sentence on a poster comes verbatim from the validated record, and two different articles
do not come out wearing the same composition.
"""
import json
import re
from collections import Counter
from xml.etree import ElementTree as ET
from xml.sax import saxutils

import httpx
import pytest
from pydantic import ValidationError

from app.pipeline import hf_ai
from app.pipeline.content_planner import plan_infographic_content
from app.pipeline.design_brief import (
    DesignBriefError,
    record_text,
    resolve_design_brief,
)
from app.pipeline.dynamic_designer import render_dynamic_svg
from app.pipeline.orchestrator import _quality_check, _stored_layout_key
from app.pipeline.svg_designer import generate_legal_snaps_svg
from app.schemas import (
    BriefSourceField,
    DesignBrief,
    DesignSectionKind,
    LayoutFamily,
    LegalRecord,
    SourceMetadata,
    ValidationSummary,
)

PRODUCTION_CANVASES = [(1080, 1350), (1200, 1200), (1200, 675)]
GOLD = "#CFA444"
CHARCOAL = "#4A4C5A"


ARBITRATION = LegalRecord(
    article_title="Supreme Court Reads Down the Arbitrator Appointment Power",
    court_or_tribunal="Supreme Court of India",
    case_name="In Re: Three Arbitration Petitions",
    citation="(2025) 4 SCC 112",
    judgment_date="18 March 2025",
    relevant_statutes=[
        "Section 11(6) of the Arbitration and Conciliation Act, 1996",
        "Section 12(5) of the Arbitration and Conciliation Act, 1996",
        "Fifth Schedule to the Arbitration and Conciliation Act, 1996",
    ],
    material_facts=[
        "Three petitioners sought appointment of an independent arbitrator after the "
        "respondent declined to act on the notice.",
        "The respondent relied on a clause naming the managing director as the sole "
        "appointing authority.",
        "The High Court had declined to interfere, holding the clause was a matter of "
        "party consent.",
    ],
    procedural_history="Petitions under Section 11(6) followed the High Court's refusal.",
    questions_or_issues=[
        "Whether a clause vesting appointment solely in one party's employee is "
        "sustainable after Section 12(5)?",
        "Whether the court may appoint an arbitrator of its own motion when the "
        "mechanism has failed?",
    ],
    arguments_parties=[
        "The petitioners argued that the appointing mechanism had become inoperative by "
        "operation of law.",
        "The respondent argued that party autonomy permitted the named authority to "
        "continue functioning.",
    ],
    legal_reasoning=[
        "The court held that the Fifth Schedule ineligibility attaches to the "
        "relationship, not the individual's competence.",
        "It reasoned that a mechanism which cannot function without bias is no mechanism "
        "at all.",
        "The bench distinguished an earlier ruling on the ground that the clause there "
        "allowed a neutral substitute.",
        "It observed that the petitioners had made a demand which went unanswered for "
        "30 days.",
        "It recorded that the respondent had sought 6 months to complete the mandate.",
    ],
    holding_or_operative_order=(
        "The appointment clause is inoperative; the court appoints a sole arbitrator from "
        "the standing list and directs that the award be rendered within 180 days."
    ),
    precedents_cited=["Perkwood International v. Azmei Trading (2024)"],
    exact_quotations=["Party autonomy cannot be stretched to validate an ineligibility created by statute."],
    practical_implications=[
        "Clauses naming an employee of one party as appointer must now be redrafted.",
        "Parties can approach the court after the 30-day period lapses without a fresh notice.",
        "Institutional arbitration retains a preference where a neutral list exists.",
    ],
    uncertainties=["Whether the ruling applies retrospectively to pending appointments remains untested."],
    is_court_judgment=True,
    analysis_source="huggingface:Qwen/Qwen2.5-72B-Instruct",
)

DATA_PROTECTION = LegalRecord(
    article_title="Delhi High Court on Traceability Orders under the IT Rules",
    court_or_tribunal="Delhi High Court",
    case_name="Ripple Foundation v. Union of India",
    citation="2025 SCC OnLine Del 812",
    judgment_date="2 September 2025",
    relevant_statutes=[
        "Rule 4(2) of the Information Technology (Intermediary Guidelines) Rules, 2021",
        "Section 69 of the Information Technology Act, 2000",
    ],
    material_facts=[
        "The petitioner challenged a traceability direction requiring intermediaries to "
        "identify the first originator of a message.",
        "The platform argued that compliance would break end-to-end encryption for every "
        "user.",
    ],
    procedural_history="The direction was issued by the Ministry and stayed by a division bench.",
    questions_or_issues=[
        "Whether a traceability direction can be issued without satisfying the necessity "
        "and proportionality test?",
        "Whether source identification is a less intrusive measure than blanket metadata "
        "retention?",
    ],
    arguments_parties=[
        "The State argued that traceability is targeted, time-bound and subject to "
        "magisterial review.",
        "The petitioner argued that any client-side break in encryption is disproportionate.",
    ],
    legal_reasoning=[
        "The court read the requirement of proportionality into Rule 4(2) and confined "
        "the order to serious offences.",
        "It held that a direction of general application cannot satisfy a targeted "
        "intrusion test.",
    ],
    holding_or_operative_order=(
        "The traceability direction is set aside for failing the proportionality test; the "
        "rules remain in force subject to the reading down."
    ),
    precedents_cited=["K.S. Puttaswamy v. Union of India (2017)"],
    exact_quotations=["A targeted intrusion cannot be authorised by a general direction."],
    practical_implications=[
        "Intermediaries must log compliance decisions for 120 days.",
        "Requests must be confined to offences carrying a term of five years or more.",
    ],
    uncertainties=["Whether the reading down applies to pending requests is left open."],
    is_court_judgment=True,
    analysis_source="huggingface:Qwen/Qwen2.5-72B-Instruct",
)

VALID = ValidationSummary(total_claims=6, verified_claims=6, unverified_claims=0)
META = SourceMetadata(title="Source report", url="https://example.test/report", publisher="Example Report",
                      retrieval_time="2026-10-25T00:00:00Z")


def section(heading, kind, source, count=2, emphasis="secondary"):
    return {
        "heading": heading,
        "kind": kind,
        "emphasis": emphasis,
        "items": [{"source": source, "index": index} for index in range(count)],
    }


def brief_payload(record=ARBITRATION, family=LayoutFamily.LANDMARK_COVER, **overrides):
    payload = {
        "layout_family": LayoutFamily(family).value,
        "rationale": "The ruling turns on a single operative direction, so it leads the page.",
        "headline_source": "case_name",
        "headline_scale": "dramatic",
        "headline_alignment": "left",
        "hero_visual": "scales",
        "sections": [
            section("Two questions before the bench", "issues", "questions_or_issues"),
            section("Why the mechanism failed", "reasoning", "legal_reasoning"),
            section("What the court ordered", "holding", "holding_or_operative_order", 1, "primary"),
        ],
        "flow_direction": "vertical",
        "whitespace": "balanced",
        "accent_strategy": "gold_rules",
        "icon_motifs": ["scales"],
        "generated_by": "huggingface:test",
    }
    payload.update(overrides)
    if overrides.get("secondary_family") is None and "secondary_family" in overrides:
        payload.pop("secondary_family")
    return payload


def make_brief(record=ARBITRATION, family=LayoutFamily.LANDMARK_COVER, **overrides):
    return DesignBrief.model_validate(brief_payload(record, family, **overrides))


def render(brief, record=ARBITRATION, width=1080, height=1350):
    plan = plan_infographic_content(record, VALID, META, design_brief=brief)
    return render_dynamic_svg(plan, record, brief, width=width, height=height), plan


def visible_text(svg: str) -> str:
    parts = [t.strip() for t in re.findall(r">([^<>]+)<", svg) if t.strip()]
    joined = saxutils.unescape(" ".join(parts), {"&quot;": '"', "&apos;": "'"})
    return " ".join(joined.split())


def structure_fingerprint(svg: str) -> Counter:
    """Counts the drawing primitives that make a composition what it is."""
    root = ET.fromstring(svg)
    counts = Counter()
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag in {"rect", "line", "circle", "polygon", "path", "text"}:
            counts[tag] += 1
    counts["font_sizes"] = len({node.get("font-size") for node in root.iter() if node.get("font-size")})
    counts["gold_fills"] = sum(
        1 for node in root.iter() if node.get("fill") == GOLD or node.get("stroke") == GOLD
    )
    return counts


# ---------------------------------------------------------------------------
# Brief schema and grounding resolver
# ---------------------------------------------------------------------------

def test_hybrid_family_requires_a_distinct_secondary_family():
    with pytest.raises(ValidationError):
        make_brief(family=LayoutFamily.HYBRID)
    with pytest.raises(ValidationError):
        make_brief(
            family=LayoutFamily.HYBRID,
            secondary_family=LayoutFamily.HYBRID.value,
        )
    hybrid = make_brief(family=LayoutFamily.HYBRID, secondary_family=LayoutFamily.TIMELINE.value)
    assert hybrid.secondary_family is LayoutFamily.TIMELINE


def test_chart_led_family_requires_chart_data():
    with pytest.raises(ValidationError):
        make_brief(family=LayoutFamily.CHART_LED)


def test_chart_on_a_non_chart_family_is_discarded():
    chart = {
        "title": "Periods the ruling set",
        "unit": "days",
        "data": [
            {"label": "Notice wait", "value_text": "30 days"},
            {"label": "Award deadline", "value_text": "180 days"},
        ],
    }
    assert make_brief(chart=chart).chart is None


def test_resolver_rejects_pointers_the_record_cannot_fill():
    too_deep = make_brief(
        sections=[
            section("Questions", "issues", "questions_or_issues", 1),
            section("Reasoning", "reasoning", "legal_reasoning", 1),
        ]
    )
    too_deep.sections[0].items[0].index = 9
    with pytest.raises(DesignBriefError, match="index 9"):
        resolve_design_brief(too_deep, ARBITRATION)

    missing_scalar = make_brief(sections=[
        section("Citation", "context", "citation", 1),
        section("Reasoning", "reasoning", "legal_reasoning", 1),
    ])
    bare = ARBITRATION.model_copy(update={"citation": None})
    with pytest.raises(DesignBriefError, match="no value for it"):
        resolve_design_brief(missing_scalar, bare)


def test_resolver_rejects_generic_template_headings():
    for heading in ("Overview", "Key Takeaways", "summary"):
        candidate = make_brief(sections=[
            section(heading, "context", "material_facts", 1),
            section("Reasoning", "reasoning", "legal_reasoning", 1),
        ])
        with pytest.raises(DesignBriefError, match="generic template label"):
            resolve_design_brief(candidate, ARBITRATION)


def test_chart_values_must_be_real_comparable_figures():
    def charted(data, unit="days"):
        return make_brief(
            family=LayoutFamily.CHART_LED,
            sections=[
                section("Facts", "facts", "material_facts", 1),
                section("Consequences", "implications", "practical_implications", 1),
            ],
            chart={"title": "Periods", "unit": unit, "data": data},
        )

    def resolve(data, unit="days"):
        resolve_design_brief(charted(data, unit), ARBITRATION)

    resolve([
        {"label": "Notice", "value_text": "30 days"},
        {"label": "Award", "value_text": "180 days"},
    ])

    with pytest.raises(DesignBriefError, match="not present verbatim"):
        resolve([
            {"label": "Notice", "value_text": "45 days"},
            {"label": "Award", "value_text": "180 days"},
        ])
    with pytest.raises(DesignBriefError, match="no numeric value"):
        resolve([
            {"label": "Notice", "value_text": "one"},
            {"label": "Award", "value_text": "180 days"},
        ])
    with pytest.raises(DesignBriefError, match="mix units"):
        resolve([
            {"label": "Notice", "value_text": "30 days"},
            {"label": "Award", "value_text": "6 months"},
        ])
    with pytest.raises(DesignBriefError, match="two different numeric values"):
        resolve([
            {"label": "Notice", "value_text": "30 days"},
            {"label": "Other", "value_text": "30 days"},
        ])


def test_resolved_brief_carries_record_text_verbatim():
    resolved = resolve_design_brief(make_brief(), ARBITRATION)
    source = record_text(ARBITRATION)
    assert resolved.headline == ARBITRATION.case_name
    for section_ in resolved.sections:
        for item in section_.items:
            assert item.text in source


# ---------------------------------------------------------------------------
# Qwen brief generation: honest success, honest failure
# ---------------------------------------------------------------------------

pytestmark_async = pytest.mark.asyncio


def install_transport(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class PatchedClient(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(hf_ai.httpx, "AsyncClient", PatchedClient)


def chat_body(content):
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]},
    )


class FakeSettings:
    hf_router_base_url = "https://router.test/v1"
    hf_provider_base_url = "https://router.test"
    hf_text_model = "Qwen/Qwen2.5-72B-Instruct"
    hf_image_model = "black-forest-labs/FLUX.1-dev"
    hf_image_provider = "fal-ai"

    def get_effective_hf_token(self) -> str:
        return "hf_test_token"


@pytest.fixture(autouse=True)
def fake_hf_settings(monkeypatch):
    """Never let a brief test reach the real token or the real router."""
    monkeypatch.setattr(hf_ai, "settings", FakeSettings())


@pytest.mark.asyncio
async def test_generate_design_brief_accepts_a_grounded_brief(monkeypatch):
    payload = brief_payload(family=LayoutFamily.TIMELINE.value)
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return chat_body("```json\n" + json.dumps(payload) + "\n```")

    install_transport(monkeypatch, handler)
    brief = await hf_ai.generate_design_brief_with_hf(ARBITRATION, VALID)
    assert brief.layout_family is LayoutFamily.TIMELINE
    assert brief.generated_by.startswith("huggingface:")
    assert "AVAILABLE POINTERS" in seen["body"]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_generate_design_brief_retries_once_with_the_rejection_reason(monkeypatch):
    broken = brief_payload(sections=[
        section("Overview", "context", "material_facts", 1),
        section("Reasoning", "reasoning", "legal_reasoning", 1),
    ])
    fixed = brief_payload(family=LayoutFamily.STATUTORY_MAP.value)
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return chat_body(json.dumps(broken if len(calls) == 1 else fixed))

    install_transport(monkeypatch, handler)
    brief = await hf_ai.generate_design_brief_with_hf(ARBITRATION, VALID)
    assert brief.layout_family is LayoutFamily.STATUTORY_MAP
    assert len(calls) == 2
    assert "generic template label" in calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_ungroundable_brief_fails_instead_of_rendering_a_sample(monkeypatch):
    def handler(request):
        return chat_body(json.dumps(brief_payload(sections=[
            section("Key Takeaways", "implications", "practical_implications", 1),
            section("More", "facts", "material_facts", 1),
        ])))

    install_transport(monkeypatch, handler)
    with pytest.raises(hf_ai.HFProviderError, match="did not return a usable design brief"):
        await hf_ai.generate_design_brief_with_hf(ARBITRATION, VALID)


@pytest.mark.asyncio
async def test_provider_error_on_brief_call_is_not_swallowed(monkeypatch):
    def handler(request):
        return httpx.Response(503, json={"error": "model overloaded"})

    install_transport(monkeypatch, handler)
    with pytest.raises(hf_ai.HFProviderError):
        await hf_ai.generate_design_brief_with_hf(ARBITRATION, VALID)


# ---------------------------------------------------------------------------
# Composition: eight families plus hybrid must look different, not just read different
# ---------------------------------------------------------------------------

def test_every_family_renders_and_declares_its_structure():
    families = {
        LayoutFamily.LANDMARK_COVER: {},
        LayoutFamily.SPLIT_COMPARISON: {},
        LayoutFamily.TIMELINE: {"flow_direction": "vertical"},
        LayoutFamily.DECISION_TREE: {"flow_direction": "stepped"},
        LayoutFamily.STATUTORY_MAP: {"flow_direction": "radial"},
        LayoutFamily.CHART_LED: {
            "sections": [
                section("Facts", "facts", "material_facts", 1),
                section("Consequences", "implications", "practical_implications", 2),
            ],
            "chart": {
                "title": "Periods the ruling set",
                "unit": "days",
                "data": [
                    {"label": "Notice wait", "value_text": "30 days"},
                    {"label": "Award deadline", "value_text": "180 days"},
                ],
            },
        },
        LayoutFamily.PROCESS_FLOW: {"flow_direction": "horizontal"},
        LayoutFamily.ARGUMENT_OUTCOME: {},
        LayoutFamily.BRIEFING_SHEET: {},
        LayoutFamily.HYBRID: {"secondary_family": LayoutFamily.TIMELINE.value},
    }
    fingerprints = {}
    for family, overrides in families.items():
        brief = make_brief(family=family, **overrides)
        svg, _ = render(brief)
        root = ET.fromstring(svg)
        assert root.get("data-layout-family") == family.value
        assert brief.layout_signature in svg
        fingerprints[family.value] = structure_fingerprint(svg)

    values = list(fingerprints.values())
    for index, left in enumerate(values):
        for right in values[index + 1:]:
            assert left != right, "two layout families produced the same structure"


def test_decision_tree_roots_on_the_question_not_a_primary_facts_card():
    brief = make_brief(
        family=LayoutFamily.DECISION_TREE,
        sections=[
            section("The clause in dispute", "facts", "material_facts", 2, "primary"),
            section("What the bench had to decide", "issues", "questions_or_issues", 2),
            section("Why the mechanism failed", "reasoning", "legal_reasoning", 2, "primary"),
            section("The order", "holding", "holding_or_operative_order", 1, "primary"),
        ],
    )
    svg, _ = render(brief)
    text = visible_text(svg)
    assert "WHAT THE BENCH HAD TO DECIDE" in text
    assert "THE ORDER" in text


def test_briefing_sheet_renders_the_dense_multi_band_explainer():
    brief = make_brief(
        family=LayoutFamily.BRIEFING_SHEET,
        headline_alignment="left",
        sections=[
            section("How the scheme worked", "process", "material_facts", 3),
            section("Constitutional questions", "issues", "questions_or_issues", 2),
            section("Why the mechanism failed", "reasoning", "legal_reasoning", 2),
            section("What the court ordered", "holding", "holding_or_operative_order", 1, "primary"),
            section("What changes now", "implications", "practical_implications", 2),
        ],
    )
    svg, _ = render(brief, width=1080, height=1350)
    root = ET.fromstring(svg)
    # All five bands survive at portrait size; dropping one would mean the density brief failed.
    assert root.get("data-sections-rendered") == "5"
    assert root.get("data-layout-scale") is not None
    shown = visible_text(svg)
    for section_ in resolve_design_brief(brief, ARBITRATION).sections:
        assert section_.heading.upper() in shown
    assert "\u2026" not in shown
    # Numbered step cards and the gold holding band are the signature of this family.
    assert root.findall(".//{http://www.w3.org/2000/svg}polygon")
    assert any(
        node.get("fill") == GOLD and float(node.get("width", 0)) > 900
        for node in root.iter("{http://www.w3.org/2000/svg}rect")
    )


def test_briefing_sheet_keeps_every_issue_item_visible():
    brief = make_brief(
        family=LayoutFamily.BRIEFING_SHEET,
        headline_alignment="left",
        sections=[
            section("How the scheme worked", "process", "material_facts", 3),
            section("Four questions before the bench", "issues", "legal_reasoning", 4),
            section("What the court ordered", "holding", "holding_or_operative_order", 1, "primary"),
        ],
    )
    svg, _ = render(brief, width=1080, height=1350)
    shown = visible_text(svg)
    resolved = resolve_design_brief(brief, ARBITRATION)
    issue_section = next(s for s in resolved.sections if s.kind == "issues")
    # A 2x2 card grid must carry all four questions; slicing to three silently misreports
    # the judgment the poster claims to explain.
    assert len(issue_section.items) == 4
    for item in issue_section.items:
        assert " ".join(item.text.split()) in shown
    assert "\u2026" not in shown


def test_briefing_sheet_embeds_model_pictures_for_each_card_sentence():
    brief = make_brief(
        family=LayoutFamily.BRIEFING_SHEET,
        headline_alignment="left",
        sections=[
            section("How the scheme worked", "process", "material_facts", 3),
            section("Four questions before the bench", "issues", "legal_reasoning", 4),
            section("What the court ordered", "holding", "holding_or_operative_order", 1, "primary"),
            section("What changes now", "implications", "practical_implications", 2),
        ],
    )
    plan = plan_infographic_content(ARBITRATION, VALID, META, design_brief=brief)
    resolved = resolve_design_brief(brief, ARBITRATION)
    picture = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
    pictures = {
        " ".join(item.text.split()).lower(): picture
        for section_ in resolved.sections
        if section_.kind not in {"holding", "outcome"}
        for item in section_.items
    }
    svg = render_dynamic_svg(
        plan,
        ARBITRATION,
        brief,
        width=1080,
        height=1350,
        illustrations=pictures,
    )
    root = ET.fromstring(svg)
    embedded = [
        node
        for node in root.iter("{http://www.w3.org/2000/svg}image")
        if node.get("class") == "card-art"
    ]
    # The model's pictures, not a drawn pictogram, must land inside the cards.
    assert len(embedded) >= 3
    assert all(node.get("href", "").startswith("data:image/png;base64,") for node in embedded)
    assert 'class="card-art"' in svg
    shown = visible_text(svg)
    for section_ in resolved.sections:
        for item in section_.items:
            assert " ".join(item.text.split()) in shown


def test_card_picture_prompts_are_written_by_the_models_not_a_keyword_table():
    plan = plan_infographic_content(ARBITRATION, VALID, META, design_brief=make_brief())
    subject_prompt = hf_ai.build_card_subject_prompt(
        plan, ["The scheme kept the donor's identity secret."]
    )
    # Qwen decides what each picture is.
    assert "decide what one picture" in subject_prompt
    assert "Never choose a gavel" in subject_prompt
    image_prompt = hf_ai.build_card_illustration_prompt("a sealed envelope and a covered face", plan)
    assert "sealed envelope and a covered face" in image_prompt
    assert "#CFA444" in image_prompt
    assert "no text" in image_prompt.lower()


@pytest.mark.parametrize("width,height", PRODUCTION_CANVASES)
def test_layouts_fit_their_canvas_without_truncating_legal_copy(width, height):
    for family in LayoutFamily:
        overrides = {}
        if family is LayoutFamily.HYBRID:
            overrides["secondary_family"] = LayoutFamily.TIMELINE.value
        if family is LayoutFamily.CHART_LED:
            continue  # covered with chart data below
        svg, _ = render(make_brief(family=family, **overrides), width=width, height=height)
        assert_svg_is_clean(svg, family.value)


def test_chart_layout_fits_and_plots_record_figures():
    brief = make_brief(
        family=LayoutFamily.CHART_LED,
        sections=[
            section("Facts", "facts", "material_facts", 1),
            section("Consequences", "implications", "practical_implications", 2),
        ],
        chart={
            "title": "Periods the ruling set",
            "unit": "days",
            "data": [
                {"label": "Notice wait", "value_text": "30 days"},
                {"label": "Award deadline", "value_text": "180 days"},
            ],
        },
    )
    for width, height in PRODUCTION_CANVASES:
        svg, _ = render(brief, width=width, height=height)
        assert_svg_is_clean(svg, "chart_led")
        for datum in brief.chart.data:
            assert datum.value_text in visible_text(svg)


def assert_svg_is_clean(svg, family):
    root = ET.fromstring(svg)
    assert root.get("data-layout-family") == family
    bottom = float(root.get("data-content-bottom"))
    limit = float(root.get("data-canvas-bottom"))
    assert bottom <= limit + 1, f"{family} overflows by {bottom - limit:.1f} units"
    assert bottom >= limit * 0.6, f"{family} leaves the canvas mostly empty"
    assert "\u2026" not in visible_text(svg), f"{family} cut a legal sentence short"


def test_poster_text_is_the_articles_own_record_and_nothing_else():
    brief = make_brief()
    svg, _ = render(brief)
    shown = visible_text(svg)
    resolved = resolve_design_brief(brief, ARBITRATION)
    for section_ in resolved.sections:
        assert section_.heading.upper() in shown
        for item in section_.items:
            probe = " ".join(item.text.split())[:44]
            assert re.search("\\s+".join(map(re.escape, probe.split())), shown)
    assert "Lorem" not in shown
    assert DATA_PROTECTION.holding_or_operative_order not in shown


def test_unrelated_articles_do_not_share_a_layout_spec():
    arbitration_brief = make_brief(family=LayoutFamily.DECISION_TREE, flow_direction="stepped")
    privacy_brief = make_brief(
        record=DATA_PROTECTION,
        family=LayoutFamily.ARGUMENT_OUTCOME,
        flow_direction="vertical",
        sections=[
            section("What the State claimed", "argument", "arguments_parties", 2),
            section("Provisions read down", "statutes", "relevant_statutes", 2),
            section("Effect of the order", "outcome", "holding_or_operative_order", 1, "primary"),
        ],
    )
    first, first_plan = render(arbitration_brief)
    second, second_plan = render(privacy_brief, record=DATA_PROTECTION)

    assert arbitration_brief.layout_signature != privacy_brief.layout_signature
    assert structure_fingerprint(first) != structure_fingerprint(second)
    assert first_plan.headline != second_plan.headline
    assert DATA_PROTECTION.holding_or_operative_order in visible_text(second)
    assert ARBITRATION.holding_or_operative_order not in visible_text(second)


def test_identical_layout_specs_are_detected_as_repetition():
    """The regression the revamp exists to prevent: one composition reused for everything."""
    first = make_brief(family=LayoutFamily.TIMELINE)
    second = make_brief(
        record=DATA_PROTECTION,
        family=LayoutFamily.TIMELINE,
        sections=[
            section("Two questions before the bench", "issues", "questions_or_issues"),
            section("Why the mechanism failed", "reasoning", "legal_reasoning"),
            section("What the court ordered", "holding", "holding_or_operative_order", 1, "primary"),
        ],
    )
    assert reused_layout(first, second), "identical structure must be reported as repetition"
    different = make_brief(
        record=DATA_PROTECTION,
        family=LayoutFamily.STATUTORY_MAP,
        flow_direction="radial",
    )
    assert not reused_layout(first, different)


def reused_layout(left: DesignBrief, right: DesignBrief) -> bool:
    return left.layout_signature == right.layout_signature


def test_brand_invariants_hold_on_every_family():
    for family in LayoutFamily:
        if family is LayoutFamily.CHART_LED:
            continue
        overrides = {"secondary_family": LayoutFamily.TIMELINE.value} if family is LayoutFamily.HYBRID else {}
        svg, plan = render(make_brief(family=family, **overrides))
        shown = visible_text(svg)
        assert GOLD in svg, family
        assert CHARCOAL in svg, family
        assert "LEGAL SNAPS" in shown, family
        assert "Legal Snaps" in shown, family
        assert plan.source_url.split("//")[-1].split("/")[0] in shown, family
        assert "Verify against the original order" in shown, family


# ---------------------------------------------------------------------------
# Renderer dispatch and quality gate
# ---------------------------------------------------------------------------

def test_briefless_plans_still_use_the_fixed_legacy_renderer():
    plan = plan_infographic_content(ARBITRATION, VALID, META)
    assert plan.design_brief is None
    svg = generate_legal_snaps_svg(plan)
    assert "data-layout-family" not in svg
    assert ET.fromstring(svg) is not None


def test_brief_cannot_be_rendered_without_the_record_it_cites():
    plan = plan_infographic_content(ARBITRATION, VALID, META, design_brief=make_brief())
    with pytest.raises(ValueError, match="validated LegalRecord"):
        generate_legal_snaps_svg(plan)


def test_quality_check_accepts_a_dynamic_poster_and_flags_a_reused_one():
    brief = make_brief(family=LayoutFamily.STATUTORY_MAP, flow_direction="radial")
    plan = plan_infographic_content(ARBITRATION, VALID, META, design_brief=brief)
    svg = generate_legal_snaps_svg(plan, record=ARBITRATION)
    assert _quality_check(svg, plan, None, 1080, 1350) == []

    other = plan_infographic_content(DATA_PROTECTION, VALID, META, design_brief=brief)
    problems = _quality_check(svg, other, None, 1080, 1350)
    assert any("missing from the rendered SVG" in problem for problem in problems)


# ---------------------------------------------------------------------------
# Variation across articles: a run of similar judgments must not reuse one shape
# ---------------------------------------------------------------------------

def test_layout_key_catches_a_repeated_composition():
    same_shape = make_brief(family=LayoutFamily.ARGUMENT_OUTCOME)
    reused = make_brief(
        family=LayoutFamily.ARGUMENT_OUTCOME,
        sections=[
            section("A different question", "issues", "questions_or_issues"),
            section("Another reading", "reasoning", "legal_reasoning"),
            section("The order", "outcome", "holding_or_operative_order", 1, "primary"),
        ],
    )
    assert same_shape.layout_key == reused.layout_key

    different_family = make_brief(family=LayoutFamily.TIMELINE)
    different_shape = make_brief(
        family=LayoutFamily.ARGUMENT_OUTCOME,
        sections=[
            section("Questions", "issues", "questions_or_issues", 1),
            section("The order", "holding", "holding_or_operative_order", 1, "primary"),
        ],
    )
    assert same_shape.layout_key not in {different_family.layout_key, different_shape.layout_key}


def test_stored_layout_key_matches_the_live_brief_key():
    brief = make_brief(family=LayoutFamily.STATUTORY_MAP, flow_direction="radial")
    job = {"design_brief": brief.model_dump()}
    assert _stored_layout_key(job) == brief.layout_key
    assert _stored_layout_key({"design_brief": None}) is None


@pytest.mark.asyncio
async def test_recent_layouts_are_named_in_the_prompt_and_retried(monkeypatch):
    repeated = brief_payload(family=LayoutFamily.ARGUMENT_OUTCOME.value)
    changed = brief_payload(
        family=LayoutFamily.PROCESS_FLOW.value,
        sections=[
            section("Steps the court laid down", "process", "practical_implications"),
            section("The operative direction", "holding", "holding_or_operative_order", 1, "primary"),
        ],
        flow_direction="horizontal",
    )
    key = make_brief(family=LayoutFamily.ARGUMENT_OUTCOME).layout_key
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body["messages"][-1]["content"])
        return chat_body(json.dumps(repeated if len(calls) == 1 else changed))

    install_transport(monkeypatch, handler)
    brief = await hf_ai.generate_design_brief_with_hf(ARBITRATION, VALID, avoid_layouts=[key])

    assert brief.layout_family is LayoutFamily.PROCESS_FLOW
    assert len(calls) == 2
    assert key in calls[0]
    assert "argument_outcome" in calls[0]
    assert "closed for this article" in calls[1]
    assert "argument_outcome" in calls[1]


@pytest.mark.asyncio
async def test_a_repeated_family_is_rejected_even_with_a_different_section_count(monkeypatch):
    """The exact-key check let landmark_cover return under a new section count."""
    old_key = make_brief(family=LayoutFamily.LANDMARK_COVER).layout_key
    same_family_new_shape = brief_payload(
        family=LayoutFamily.LANDMARK_COVER.value,
        sections=[
            section("Two questions before the bench", "issues", "questions_or_issues"),
            section("What the court ordered", "holding", "holding_or_operative_order", 1, "primary"),
        ],
    )
    changed = brief_payload(family=LayoutFamily.STATUTORY_MAP.value)
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body["messages"][-1]["content"])
        return chat_body(json.dumps(same_family_new_shape if len(calls) == 1 else changed))

    install_transport(monkeypatch, handler)
    brief = await hf_ai.generate_design_brief_with_hf(ARBITRATION, VALID, avoid_layouts=[old_key])

    assert brief.layout_family is LayoutFamily.STATUTORY_MAP
    assert len(calls) == 2
    assert "landmark_cover" in calls[0]
    assert "closed for this article" in calls[1]


@pytest.mark.asyncio
async def test_a_model_that_will_not_budge_is_reshaped_onto_an_open_family(monkeypatch):
    payload = brief_payload(family=LayoutFamily.ARGUMENT_OUTCOME.value)
    key = make_brief(family=LayoutFamily.ARGUMENT_OUTCOME).layout_key
    calls = []

    def handler(request):
        calls.append(request)
        return chat_body(json.dumps(payload))

    install_transport(monkeypatch, handler)
    brief = await hf_ai.generate_design_brief_with_hf(ARBITRATION, VALID, avoid_layouts=[key])

    # The composition changes, but every pointer into the validated record survives, so
    # the poster still says only what the record says.
    assert brief.layout_family is not LayoutFamily.ARGUMENT_OUTCOME
    assert len(calls) == 4
    resolved = resolve_design_brief(brief, ARBITRATION)
    assert [len(section_.items) for section_ in resolved.sections] == [2, 2, 1]


@pytest.mark.asyncio
async def test_a_judgment_brief_without_the_decision_is_retried(monkeypatch):
    without_holding = brief_payload(
        family=LayoutFamily.DECISION_TREE.value,
        sections=[
            section("The clause in dispute", "facts", "material_facts"),
            section("Why the mechanism failed", "reasoning", "legal_reasoning"),
        ],
    )
    with_holding = brief_payload(family=LayoutFamily.DECISION_TREE.value)
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body["messages"][-1]["content"])
        return chat_body(json.dumps(without_holding if len(calls) == 1 else with_holding))

    install_transport(monkeypatch, handler)
    brief = await hf_ai.generate_design_brief_with_hf(ARBITRATION, VALID)

    assert any(section.kind is DesignSectionKind.HOLDING for section in brief.sections)
    assert len(calls) == 2
    assert "no holding or outcome section" in calls[1]


@pytest.mark.asyncio
async def test_the_decision_is_restored_when_the_model_never_adds_it(monkeypatch):
    without_holding = brief_payload(
        family=LayoutFamily.DECISION_TREE.value,
        sections=[
            section("The clause in dispute", "facts", "material_facts"),
            section("Why the mechanism failed", "reasoning", "legal_reasoning"),
        ],
    )

    def handler(request):
        return chat_body(json.dumps(without_holding))

    install_transport(monkeypatch, handler)
    brief = await hf_ai.generate_design_brief_with_hf(ARBITRATION, VALID)

    holding = next(section for section in brief.sections if section.kind is DesignSectionKind.HOLDING)
    assert brief.layout_family is LayoutFamily.DECISION_TREE
    resolved = resolve_design_brief(brief, ARBITRATION)
    assert any(
        item.text == ARBITRATION.holding_or_operative_order for section_ in resolved.sections for item in section_.items
    )
    assert holding.items[0].source is BriefSourceField.HOLDING


def test_duplicate_section_headings_are_rejected():
    duplicated = make_brief(sections=[
        section("Legal reasoning", "reasoning", "legal_reasoning", 1),
        section("LEGAL REASONING", "reasoning", "legal_reasoning", 1, "primary"),
    ])
    with pytest.raises(DesignBriefError, match="used twice"):
        resolve_design_brief(duplicated, ARBITRATION)


def test_brief_carries_the_editorial_metadata_contract():
    brief = make_brief(
        article_title="In Re: Three Arbitration Petitions",
        content_type="Supreme Court judgment",
        central_issue="Can a party employee remain the sole appointing authority?",
        main_takeaway="The appointment clause is inoperative.",
        diagram_type="stepped legal test",
        illustration_concept="An appointing hand tied by a statutory thread",
        visual_emphasis="the failed appointment mechanism",
        source_attribution="Supreme Court of India, 2025",
        uncertainties=["Whether the ruling reaches pending appointments"],
    )
    assert brief.article_title == "In Re: Three Arbitration Petitions"
    assert brief.illustration_concept.startswith("An appointing hand")
    assert brief.uncertainties == ["Whether the ruling reaches pending appointments"]


def test_design_brief_prompt_carries_the_house_style_guide():
    prompt = hf_ai.build_design_brief_prompt(ARBITRATION, VALID)

    assert "#CFA444" in prompt and "#4A4C5A" in prompt
    assert "Poppins" in prompt
    assert "8px" in prompt
    assert "never use pure black" in prompt.lower()
    assert "call-to-action" in prompt.lower()
    # The shared prompt fixes the style, never one article's copy: the reference brief's
    # criminal-laws sample must not leak into every future poster.
    assert "Bharatiya" not in prompt


def test_artwork_prompt_follows_the_article_concept_not_a_fixed_tableau():
    brief = make_brief(
        family=LayoutFamily.ARGUMENT_OUTCOME,
        illustration_concept="Three sealed petition files converging on one gold line",
    )
    plan = plan_infographic_content(ARBITRATION, VALID, META, design_brief=brief)
    prompt = hf_ai.build_artwork_prompt(plan)

    assert "Three sealed petition files converging on one gold line" in prompt
    assert "#CFA444" in prompt and "white" in prompt.lower()
    assert "woman advocate" not in prompt
    # The image model must never be asked to paint legal text or data.
    assert "no text" in prompt.lower()
    # Sensitive legal subject matter must not turn into a violent scene.
    assert "never depict weapons" in prompt.lower()
    assert "violence" in prompt.lower()


def test_artwork_is_placed_beside_the_headline_for_non_landmark_families():
    brief = make_brief(family=LayoutFamily.ARGUMENT_OUTCOME)
    plan = plan_infographic_content(ARBITRATION, VALID, META, design_brief=brief)
    svg = render_dynamic_svg(
        plan,
        ARBITRATION,
        brief,
        width=1080,
        height=1350,
        artwork_base64_data_uri="data:image/png;base64,AAAA",
    )
    root = ET.fromstring(svg)
    images = [node for node in root.iter() if node.tag.endswith("image")]
    assert len(images) == 1
    assert images[0].attrib["href"] == "data:image/png;base64,AAAA"
    # The artwork belongs in the right margin, not on top of the headline column.
    assert float(images[0].attrib["x"]) > 700


def test_landmark_centred_headline_stays_inside_its_narrowed_column():
    brief = make_brief(
        family=LayoutFamily.LANDMARK_COVER,
        headline_alignment="center",
    )
    plan = plan_infographic_content(ARBITRATION, VALID, META, design_brief=brief)
    svg = render_dynamic_svg(
        plan,
        ARBITRATION,
        brief,
        width=1080,
        height=1350,
        artwork_base64_data_uri="data:image/png;base64,AAAA",
    )
    root = ET.fromstring(svg)
    image = next(node for node in root.iter() if node.tag.endswith("image"))
    image_x = float(image.attrib["x"])
    # The display headline is the largest centred text block. It must be centred on the
    # left column that the spot illustration leaves free, not on the whole canvas.
    headline_xs = []
    for block in root.iter():
        if not block.tag.endswith("text"):
            continue
        if block.attrib.get("text-anchor") != "middle":
            continue
        if float(block.attrib.get("font-size", 0)) < 40:
            continue
        for line in block:
            if line.tag.endswith("tspan") and "x" in line.attrib:
                headline_xs.append(float(line.attrib["x"]))
    assert headline_xs, "expected a centred display headline"
    assert max(headline_xs) < image_x - 150
