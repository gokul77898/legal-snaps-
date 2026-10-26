import asyncio
import base64
import json
import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, get_origin

import httpx
from huggingface_hub import AsyncInferenceClient
from pydantic import ValidationError

from app.config import settings
from app.schemas import (
    BriefItem,
    BriefSourceField,
    DesignBrief,
    DesignSection,
    DesignSectionKind,
    InfographicContentPlan,
    LayoutFamily,
    LegalRecord,
    ValidationSummary,
)
from app.pipeline.design_brief import (
    DesignBriefError,
    available_sources,
    record_value_map,
    resolve_design_brief,
)

logger = logging.getLogger(__name__)


class HFProviderError(RuntimeError):
    """Raised when a Hugging Face Inference Provider call cannot be completed.

    The pipeline turns this into a failed job. Analysis is never satisfied by a regex
    parser, a sample record, or any other local stand-in.
    """


ANALYSIS_MAX_TOKENS = 6000
ANALYSIS_TIMEOUT_SECONDS = 300.0
ANALYSIS_ATTEMPTS = 2
ARTWORK_TIMEOUT_SECONDS = 240.0

# Explainer cards carry a picture per sentence. Qwen names the picture, Krea draws it;
# neither the renderer nor this module picks the subject from a keyword table.
CARD_ART_MAX_ITEMS = 12
CARD_ART_CONCURRENCY = 4
CARD_ART_SIDE = 512
CARD_ART_STORED_SIDE = 320
CARD_SUBJECT_MAX_TOKENS = 1400
CARD_SUBJECT_ATTEMPTS = 2


ANALYSIS_JSON_SCHEMA_HINT = """{
  "article_title": "short title of this specific article or case",
  "court_or_tribunal": "string or null",
  "case_name": "string or null - exactly the party names, one line, no judge list",
  "citation": "string or null - only when this document itself is that decision",
  "case_number": "string or null",
  "bench_composition": ["judge names if the text lists them, otherwise []"],
  "judgment_date": "string or null - the decision date, never the article publication date",
  "relevant_statutes": ["provisions this document actually decides or explains"],
  "material_facts": ["facts stated in the text"],
  "procedural_history": "string or null",
  "questions_or_issues": ["legal issues framed in the text"],
  "arguments_parties": [],
  "legal_reasoning": ["reasoning steps stated in the text"],
  "holding_or_operative_order": "the operative conclusion stated in the text",
  "precedents_cited": ["case names the text cites"],
  "exact_quotations": ["verbatim passages copied from the text"],
  "practical_implications": ["consequences stated in the text"],
  "supporting_source_passages": ["short verbatim excerpts backing the holding"],
  "unverified_fields": ["names of fields the text does not support"],
  "uncertainties": ["what the text fails to establish"],
  "is_court_judgment": "true only when this document IS a judgment, otherwise false",
  "legislation_or_article_type": "court-judgment | news-article | statute | law-review | government-order"
}"""


def build_analysis_prompt(corpus: str, title: str, source_url: Optional[str]) -> str:
    return f"""You are a senior legal researcher preparing structured data for an infographic.

Analyse ONLY the DOCUMENT below. Write nothing that is not supported by it.

Rules:
1. Report the specific matter in this document. Never reuse generic phrasing.
2. A law-firm article, news report, commentary, statute or government order that DISCUSSES a
   decision is not itself a judgment. Set is_court_judgment to false and name the type in
   legislation_or_article_type. Set it true only when the document contains the court's own
   caption, coram and operative order. For commentary leave court_or_tribunal and judgment_date
   null and bench_composition as an empty list unless the document states them.
3. case_name must be a single short line of party names. Do not put judge names, headings,
   cover pages or table-of-contents text into it.
4. citation and case_number identify only the decision this document itself is. For commentary
   put the discussed decision's citation in precedents_cited and leave citation null.
   judgment_date is the decision date, never the article publication date; otherwise null.
   Add every absent identifier to unverified_fields.
5. exact_quotations must be copied verbatim from the document. Do not paraphrase them.
6. holding_or_operative_order is the document's own conclusion, not a party's argument. If the
   document reports only arguments, say so in uncertainties.
7. Distinguish quoted precedent from this document's reasoning: cases merely cited belong in
   precedents_cited, not in relevant_statutes.
8. Anything the document does not establish goes into uncertainties. Do not fill gaps from
   general knowledge of Indian or comparative law.
9. Each item in legal_reasoning and practical_implications is one declarative sentence under
   28 words. Questions belong only in questions_or_issues, never in legal_reasoning.
10. Provide 3-5 comprehensive, distinct items for material_facts (describing the factual mechanism or dispute), 2-4 distinct items for questions_or_issues (identifying specific constitutional articles or statutory sections examined), 3-5 distinct items for legal_reasoning (the court's core ratio and legal principles), and 2-4 distinct items for practical_implications (impact on law, rights, and governance). This provides the essential substance needed for an informative editorial infographic.

Return ONLY one JSON object with exactly these keys. No prose, no markdown fences, no
comments, and no trailing text. Every key must be present: use [] for an empty list and
null only for absent optional text:
{ANALYSIS_JSON_SCHEMA_HINT}

SOURCE URL: {source_url or "not recorded"}
REQUESTED TOPIC: {title}

DOCUMENT:
{corpus}
"""


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:400] or "no error body"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail")
            if message:
                return str(message)[:400]
        if isinstance(error, str):
            return error[:400]
        if payload.get("message"):
            return str(payload["message"])[:400]
    return json.dumps(payload)[:400]


async def _hf_request(
    path: str,
    payload: Dict[str, Any],
    timeout: float,
) -> httpx.Response:
    token = settings.get_effective_hf_token()
    if not token:
        raise HFProviderError(
            "No Hugging Face token configured. Set HF_TOKEN in backend/.env "
            "(or run `hf auth login`) to use the inference providers."
        )

    url = (
        path
        if path.startswith("http")
        else f"{settings.hf_router_base_url.rstrip('/')}/{path.lstrip('/')}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as e:
        raise HFProviderError(f"Hugging Face request to {path} timed out after {timeout:.0f}s.") from e
    except httpx.HTTPError as e:
        raise HFProviderError(f"Hugging Face request to {path} failed: {e}") from e

    if response.status_code != 200:
        raise HFProviderError(
            f"Hugging Face {path} returned {response.status_code}: {_extract_error_detail(response)}"
        )
    return response


async def _hf_chat_completion(payload: Dict[str, Any]) -> Dict[str, Any]:
    response = await _hf_request("chat/completions", payload, ANALYSIS_TIMEOUT_SECONDS)
    try:
        return response.json()
    except ValueError as e:
        raise HFProviderError(
            f"Hugging Face chat endpoint returned non-JSON: {response.text[:200]}"
        ) from e


def _extract_completion_text(body: Dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise HFProviderError(
            f"Hugging Face returned no choices: {json.dumps(body)[:300]}"
        )

    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")

    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )

    if not isinstance(content, str) or not content.strip():
        raise HFProviderError("Hugging Face returned an empty completion.")

    if choice.get("finish_reason") == "length":
        raise HFProviderError(
            "Hugging Face stopped at the token limit before finishing the JSON document."
        )
    return content


def _parse_json_object(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise HFProviderError(f"Hugging Face returned no JSON object. Received: {cleaned[:200]}")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as e:
        raise HFProviderError(f"Hugging Face returned malformed JSON: {e}") from e


def _normalise_null_lists(data: Dict[str, Any]) -> Dict[str, Any]:
    """Treat a null list field as an empty list.

    The model occasionally sends null for list fields that the prompt marks optional
    (for example bench_composition when the source is a news article). Null means the
    source did not provide the information, not that the record is invalid.
    """
    if not isinstance(data, dict):
        raise ValueError("Hugging Face response must be a JSON object.")
    normalised = dict(data)
    for name, field in LegalRecord.model_fields.items():
        if get_origin(field.annotation) is list and normalised.get(name, ...) is None:
            normalised[name] = []
    return normalised


def _scrub_unsupported_quotations(record: LegalRecord, source_text: str) -> List[str]:
    """Drop quotations the source does not contain, so a paraphrase is never shown as a quote."""
    from app.pipeline.legal_validator import normalize_text

    norm_source = normalize_text(source_text)
    kept: List[str] = []
    dropped: List[str] = []
    for quote in record.exact_quotations:
        (kept if normalize_text(quote) in norm_source else dropped).append(quote)
    record.exact_quotations = kept
    return dropped


def _analysis_messages(prompt: str, feedback: Optional[str]) -> List[Dict[str, str]]:
    user_content = prompt
    if feedback:
        user_content = (
            f"{prompt}\n\n"
            "VALIDATION FEEDBACK FOR YOUR PREVIOUS ATTEMPT:\n"
            f"{feedback}\n"
            "Return the complete JSON object again. Every key in the schema must be present; "
            "use [] for empty lists and null for absent optional text. Do not omit "
            "holding_or_operative_order."
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a legal-research data extraction engine. You reply with a single "
                "valid JSON object only, never with prose or markdown."
            ),
        },
        {"role": "user", "content": user_content},
    ]


async def analyze_legal_with_hf(
    text: str,
    title: str,
    source_url: Optional[str] = None,
) -> LegalRecord:
    """
    Analyse the retrieved document with the configured Qwen model and return a
    schema-validated LegalRecord.

    Raises HFProviderError on a missing token, a provider error, or output that fails
    schema validation. There is no local fallback.
    """
    prompt = build_analysis_prompt(text, title, source_url)
    feedback: Optional[str] = None
    record: Optional[LegalRecord] = None

    for attempt in range(ANALYSIS_ATTEMPTS):
        body = await _hf_chat_completion({
            "model": settings.hf_text_model,
            "messages": _analysis_messages(prompt, feedback),
            "temperature": 0.1,
            "max_tokens": ANALYSIS_MAX_TOKENS,
        })

        try:
            data = _normalise_null_lists(_parse_json_object(_extract_completion_text(body)))
            if (
                not isinstance(data.get("holding_or_operative_order"), str)
                or not data["holding_or_operative_order"].strip()
            ):
                raise ValueError("holding_or_operative_order is missing or empty")
            record = LegalRecord.model_validate(data)
            break
        except (HFProviderError, ValidationError, ValueError) as e:
            feedback = str(e)
            if attempt + 1 < ANALYSIS_ATTEMPTS:
                logger.warning(
                    "Analysis attempt %s rejected; retrying once: %s",
                    attempt + 1,
                    feedback,
                )
                continue

    if record is None:
        raise HFProviderError(
            "Hugging Face output did not match the legal record schema after "
            f"{ANALYSIS_ATTEMPTS} attempts: {feedback}"
        )

    dropped = _scrub_unsupported_quotations(record, text)
    if dropped:
        record.unverified_fields = list(record.unverified_fields) + [
            f"exact_quotations ({len(dropped)} removed: not verbatim in source)"
        ]
        record.uncertainties = list(record.uncertainties) + [
            f"Removed quotation absent from source: {q[:90]}" for q in dropped
        ]

    record.analysis_source = f"huggingface:{settings.hf_text_model}"
    logger.info(
        "Legal record for '%s' analysed via %s",
        record.case_name or record.article_title, record.analysis_source,
    )
    return record


DESIGN_BRIEF_MAX_TOKENS = 3200
DESIGN_BRIEF_ATTEMPTS = 2

DESIGN_BRIEF_SCHEMA_HINT = """{
  "layout_family": "landmark_cover | split_comparison | timeline | decision_tree | statutory_map | chart_led | process_flow | argument_outcome | briefing_sheet | hybrid",
  "secondary_family": "one of the same values, or null (required only for hybrid)",
  "rationale": "why this structure fits THIS document, one sentence",
  "article_title": "the article or case name exactly as the record states it",
  "content_type": "e.g. supreme court judgment, high court judgment, statutory analysis, news report",
  "central_issue": "the legal question this document actually decides, in your own short phrase",
  "main_takeaway": "the operative outcome in your own short phrase (metadata only, never rendered)",
  "diagram_type": "the diagram the viewer will see, e.g. two-panel comparison, stepped legal test, radial provision map",
  "illustration_concept": "one concrete article-specific visual metaphor; avoid a generic gavel, courthouse or scales unless the record makes it essential",
  "visual_emphasis": "which legal point the composition should make most prominent",
  "source_attribution": "court/tribunal or publisher, and year, taken from the record",
  "uncertainties": ["facts the record leaves unclear or unsupported"],
  "headline_source": "case_name | article_title",
  "headline_scale": "compact | standard | dramatic",
  "headline_alignment": "left | center",
  "hero_visual": "none | scales | gavel | timeline | map | tree | chart | flow | columns",
  "sections": [
    {
      "heading": "short editorial label naming the actual legal idea (never 'Overview' or 'Key Takeaways')",
      "kind": "context | facts | issues | reasoning | statutes | holding | implications | timeline | comparison | process | argument | outcome",
      "emphasis": "primary | secondary | quiet",
      "items": [{"source": "record field name", "index": 0}]
    }
  ],
  "flow_direction": "vertical | horizontal | stepped | radial",
  "whitespace": "tight | balanced | airy",
  "accent_strategy": "gold_rules | gold_panels | dark_panels | outline",
  "icon_motifs": ["optional short motif words"],
  "chart": null,
  "design_notes": "optional note to the renderer, or null"
}"""

CHART_SCHEMA_HINT = """{
  "title": "what the numbers measure",
  "unit": "optional unit such as days, months or %",
  "data": [
    {"label": "short bar label", "value_text": "the figure exactly as the record writes it, e.g. 60 days"}
  ]
}"""


# The fixed house style every poster is judged against. The wording comes from the Legal
# Snaps style guide prompt; the article-specific example copy from that brief is deliberately
# not included, because each poster must carry its own validated article content.
LEGAL_SNAPS_STYLE_GUIDE = """LEGAL SNAPS HOUSE STYLE (fixed for every poster; you choose composition only):
- Palette: white canvas, gold #CFA444 for highlights, section bars and icons, charcoal
  #4A4C5A for headings and body copy, warm ivory panels. Never use pure black text. Gold
  marks the new, decisive or operative material; charcoal carries the established position.
- Typography: Poppins only. One bold display line for the headline and one regular weight
  for body copy, with at most three distinct sizes on the finished poster. Body copy stays
  legible at phone width, with strong contrast against its background.
- Layout: strict 8px spacing rhythm, 8px corner radius on cards and panels, a subtle shadow,
  and clean alignment. Every component should feel scannable rather than decorative.
- Reading order: bold headline, a one-sentence gold hook directly beneath it, a short gist
  when the record supplies one, 3-4 scannable takeaway, comparison or step blocks, one
  article-specific illustration, then source attribution and the solid-gold call-to-action
  footer with the Legal Snaps wordmark and date.
- Old versus new: when the record contrasts two regimes, provisions or positions, present
  them as clearly labelled parallel columns and emphasise the differences with iconography
  or the gold accent, never with colour alone.
- Copy: every heading, bullet and label must be concise, spell-checked, grammatically
  complete and free of orphaned words or truncated sentences. Never add filler text.
- Hierarchy: the title is the loudest element, the illustration supports rather than
  competes with it, and the legal substance fills the page. No empty decorative bands."""


def _recent_families(
    avoid_layouts: Optional[Sequence[str]], limit: int = 3
) -> List[str]:
    """Most recent distinct layout families, excluding the flagship briefing_sheet."""
    families: List[str] = []
    for key in avoid_layouts or []:
        family = str(key).split("/", 1)[0].strip()
        if family and family != "briefing_sheet" and family not in families:
            families.append(family)
        if len(families) >= limit:
            break
    return families


def _has_chronological_milestones(record: LegalRecord) -> bool:
    """True only if procedural history or material facts contain real verified dates/years."""
    date_regex = re.compile(r"\b(?:19|20)\d{2}\b")
    if record.procedural_history and date_regex.search(record.procedural_history):
        return True
    dates_in_facts = sum(1 for f in record.material_facts if date_regex.search(f))
    return dates_in_facts >= 2


def _family_is_viable(family: str, record: LegalRecord, section_count: int) -> bool:
    """Whether a family can carry this record without inventing a chart or chronology."""
    statutes = [s for s in record.relevant_statutes if str(s).strip()]
    arguments = [a for a in record.arguments_parties if str(a).strip()]
    issues = [i for i in record.questions_or_issues if str(i).strip()]
    if family == "chart_led":
        return False  # only permitted when verified numerical data exists
    if family == "hybrid":
        return section_count >= 3
    if family == "timeline":
        return _has_chronological_milestones(record)
    if family == "statutory_map":
        return bool(statutes)
    if family == "argument_outcome":
        return bool((arguments or issues) and record.holding_or_operative_order)
    if family == "decision_tree":
        return bool(issues)
    if family == "process_flow":
        return bool(issues or record.procedural_history or len(record.material_facts) >= 2)
    return section_count >= 2


# Families the renderer can carry for any grounded set of sections. The model normally
# picks from the whole list; this rotation is only the deterministic escape hatch when it
# keeps returning a composition that was used moments ago.
_FAMILY_ROTATION = (
    "briefing_sheet",
    "argument_outcome",
    "statutory_map",
    "decision_tree",
    "process_flow",
    "split_comparison",
    "landmark_cover",
)


def _open_families(record: LegalRecord, banned: Sequence[str], section_count: int = 3) -> List[str]:
    return [
        family
        for family in _FAMILY_ROTATION
        if family not in banned and _family_is_viable(family, record, section_count)
    ]


def _suggest_family(record: LegalRecord, banned: Sequence[str], section_count: int = 3) -> Optional[str]:
    """Default to the flagship briefing_sheet format."""
    return "briefing_sheet"


def _reshape_family(brief: DesignBrief, record: LegalRecord, banned: Sequence[str]) -> DesignBrief:
    """Last-resort family change that keeps every validated pointer untouched."""
    target = _suggest_family(record, banned, len(brief.sections))
    if not target or target == brief.layout_family.value:
        return brief
    return brief.model_copy(
        update={
            "layout_family": LayoutFamily(target),
            "secondary_family": None,
            "chart": None,
            "flow_direction": "stepped" if target == "process_flow" else "vertical",
            # A cover-sized display line would crowd a denser family's content.
            "headline_scale": "standard" if brief.headline_scale == "dramatic" else brief.headline_scale,
        }
    )


def _brief_omits_the_decision(brief: DesignBrief, record: LegalRecord) -> bool:
    """A judgment poster without the court's decision is not publishable."""
    if not record.is_court_judgment:
        return False
    if not (record.holding_or_operative_order or "").strip():
        return False
    return not any(
        section.kind.value in {"holding", "outcome"} for section in brief.sections
    )


def _with_holding_section(brief: DesignBrief, record: LegalRecord) -> DesignBrief:
    """Add the decision as a grounded section when the model omitted it twice."""
    if not _brief_omits_the_decision(brief, record):
        return brief
    sections = list(brief.sections)
    if len(sections) >= 5:
        sections = sections[:4]
    sections.append(
        DesignSection(
            heading="WHAT THE BENCH HELD",
            kind=DesignSectionKind.HOLDING,
            items=[BriefItem(source=BriefSourceField.HOLDING, index=0)],
            emphasis="primary",
        )
    )
    return brief.model_copy(update={"sections": sections})


def build_design_brief_prompt(
    record: LegalRecord,
    validation: ValidationSummary,
    avoid_layouts: Optional[Sequence[str]] = None,
    preferred_family: Optional[str] = None,
) -> str:
    pointers = json.dumps(available_sources(record), indent=2)
    avoid = [key for key in (avoid_layouts or []) if key]
    recent_families = [] if preferred_family else _recent_families(avoid)
    avoid_rule = ""
    if avoid:
        open_families = _open_families(record, recent_families)
        family_list = ", ".join(recent_families) if recent_families else "none parsed"
        avoid_rule = (
            "10. CLOSED COMPOSITIONS: the most recent Legal Snaps posters used these layout "
            f"families - {family_list}. Do not return any of them for this article. Their "
            "exact structures were: "
            + "; ".join(avoid[:6])
            + ". Choose a different family that the record genuinely supports"
            + (f" (open options here: {', '.join(open_families[:4])})" if open_families else "")
            + ", and change the number and shape of sections so this poster visibly differs. "
            "Reuse a closed family only if every open family would misrepresent the record, "
            "and say so in the rationale.\n"
        )
    preferred_rule = ""
    if preferred_family:
        preferred_rule = (
            f"11. The editor has pinned this poster to the '{preferred_family}' composition. "
            "Use that layout family and shape its sections the way that family requires; "
            "the pin overrides the recent-layout list above. Stay inside the record.\n"
        )
    return f"""You are the art director for Legal Snaps, an editorial series of legal infographics.

Choose ONE structural composition for the VALIDATED RECORD below. The record is the only
permitted source of legal content: you select layout and point at record fields, you never
write, paraphrase, condense or invent the legal sentences themselves.

Layout families:
- landmark_cover: one decisive ruling with no comparison, chronology or dataset. Huge
  headline, a dominant pull-quote of the holding, then supporting points as a row of cards.
- split_comparison: the document contrasts two regimes, provisions or positions.
- timeline: the material sequence is procedural history, dates or stages.
- decision_tree: the document applies a test with conditions/branches leading to outcomes.
- statutory_map: several statutes or constitutional provisions are mapped to their effect.
- chart_led: ONLY when the record contains at least two different numeric figures that are
  the real story. Give a chart object whose value_text is copied verbatim from the record.
- process_flow: ONLY when the document sets out ordered steps, directions, compliance
  actions or a sequence the reader must follow. A judgment's facts and reasoning are not
  steps, so never stretch a case explanation into a numbered flow.
- argument_outcome: contested party arguments resolved into an operative order.
- briefing_sheet: an explanatory judgment that combines a mechanism or set of facts, several
  distinct legal questions, an operative order and consequences. This is the densest
  composition: a big left headline, a row of numbered step cards, numbered issue cards, a
  gold holding band and a closing impact strip. Use it when the document genuinely has that
  many distinct blocks to explain.
- hybrid: two families genuinely dominate; then secondary_family is required.

{LEGAL_SNAPS_STYLE_GUIDE}
- The headline names the story but never swallows the content: choose the scale that leaves the
  legal substance most of the poster.
- Judicial holdings and party arguments are different things; never blend them into one section.
- For a court judgment whose record carries a holding, the brief must include a section of
  kind holding or outcome that cites holding_or_operative_order. A poster that omits what
  the court decided is not publishable, whatever family you choose.
- Never invent dates, figures, citations, quotations or parties, and never chart anything that is
  not a real figure in the record.
- Do not force a timeline when the record has no meaningful chronological sequence.
- The one-sentence hook and the gist are plan-level copy, not a section you can cite; never
  create a section just to restate them under a generic label.

Selection rules:
1. For court judgments and legal explainers, briefing_sheet is the signature Legal Snaps format
   (matching the benchmark house explainer poster with step rows, issue cards with article pills,
   gold holding band with scales medallion, and closing impact strip). Default to briefing_sheet
   so that every poster delivers this rich, authoritative editorial standard.
2. Return 4-5 sections (each with 2-4 items) so the poster comprehensively fills the 1350px
   editorial canvas without empty voids. Include: (1) Background Facts or Scheme Mechanism (as sequence
   steps or facts), (2) Constitutional Questions or Legal Issues, (3) What the Court Held (the operative
   holding band), (4) Legal Reasoning & Key Principles, (5) Practical Implications & Impact. Order them
   chronologically and logically as the legal story unfolds. Each item is only {{"source": ..., "index": ...}}.
3. "source" must be one of the field names in AVAILABLE POINTERS below; "index" must be
   within the count shown for that field. An unavailable field causes the job to fail.
4. Headings are short design labels (max 52 characters). Never use "OVERVIEW", "SUMMARY" or
   "KEY TAKEAWAYS"; name the legal idea, for example "WHAT THE BENCH ANSWERED".
5. Make sections differ from one another and from the headline. Prefer the fields with the
   most substance: reasoning, facts, statutes, implications, quotations, procedural history.
   A section's kind must match its pointers: questions_or_issues only under an issues
   section, arguments_parties only under an argument section, holding_or_operative_order
   only under holding or outcome, and practical_implications only under implications. Never
   present the court's questions as a party's arguments.
6. Set is-judgment context honestly: commentary and news articles may not present themselves
   as a court's operative order. If a field is absent from AVAILABLE POINTERS, do not cite it.
7. For chart_led, chart must use {CHART_SCHEMA_HINT}; every value_text must appear verbatim
   in the record. For every other family set chart to null.
8. Set headline_source to article_title when the article title is the sharper poster line,
   otherwise case_name. Choose headline_scale/alignment/flow/whitespace to reinforce the
   family, not decoratively.
9. Fill the editorial metadata from the record only: article_title, content_type,
   central_issue, main_takeaway, diagram_type, illustration_concept, visual_emphasis,
   source_attribution and uncertainties. These are art-direction notes, never poster copy.
   The illustration_concept must be a concrete metaphor for THIS article; do not default to
   a gavel, courthouse or scales when the facts suggest something more specific.
{avoid_rule}{preferred_rule}
Return ONLY one JSON object with exactly these keys, no markdown fences:
{DESIGN_BRIEF_SCHEMA_HINT}

VALIDATION STATUS: {validation.verified_claims}/{validation.total_claims} claims verified;
critical unverified = {str(validation.has_critical_unverified).lower()}.
Unverified fields: {json.dumps(record.unverified_fields[:6])}

AVAILABLE POINTERS (field name -> number of usable items):
{pointers}

VALIDATED RECORD:
{json.dumps(record_value_map(record), indent=2, default=str)}
"""


def _design_brief_messages(prompt: str, feedback: Optional[str]) -> List[Dict[str, str]]:
    user_content = prompt
    if feedback:
        user_content = (
            f"{prompt}\n\n"
            "YOUR PREVIOUS BRIEF WAS REJECTED:\n"
            f"{feedback}\n"
            "Return a complete corrected JSON object. Keep every cited index inside the "
            "counts shown in AVAILABLE POINTERS."
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a legal-editorial art director. You answer with one valid JSON "
                "object only, never prose or markdown."
            ),
        },
        {"role": "user", "content": user_content},
    ]


async def generate_design_brief_with_hf(
    record: LegalRecord,
    validation: ValidationSummary,
    avoid_layouts: Optional[Sequence[str]] = None,
    preferred_family: Optional[str] = None,
) -> DesignBrief:
    """Choose and validate article-specific art direction before anything is rendered.

    avoid_layouts carries the structure keys of recent posters. The model is told which
    layout families those posters used and a brief that reuses one is retried at the family
    level, not just the exact key, so a run of articles cannot keep wearing the same
    composition under a different section count. If it still refuses to move, the grounded
    brief is reshaped onto a different viable family without touching a single pointer.
    preferred_family is an explicit editorial pin and takes precedence over that list.

    Raises HFProviderError when the provider fails or the brief cannot be grounded in the
    validated record. There is deliberately no default layout and no sample infographic.
    """
    avoid = [key for key in (avoid_layouts or []) if key]
    recent_families = [] if preferred_family else _recent_families(avoid)
    prompt = build_design_brief_prompt(record, validation, avoid, preferred_family)
    feedback: Optional[str] = None
    brief: Optional[DesignBrief] = None
    stale: Optional[DesignBrief] = None
    attempts = DESIGN_BRIEF_ATTEMPTS + (2 if recent_families else (1 if avoid else 0))

    for attempt in range(attempts):
        body = await _hf_chat_completion({
            "model": settings.hf_text_model,
            "messages": _design_brief_messages(prompt, feedback),
            "temperature": 0.2,
            "max_tokens": DESIGN_BRIEF_MAX_TOKENS,
        })

        try:
            data = _parse_json_object(_extract_completion_text(body))
            candidate = DesignBrief.model_validate(data)
            candidate.generated_by = f"huggingface:{settings.hf_text_model}"
            resolve_design_brief(candidate, record)
            if (
                preferred_family
                and candidate.layout_family.value != preferred_family
                and attempt + 1 < attempts
            ):
                feedback = (
                    f"The editor pinned this poster to the '{preferred_family}' composition, "
                    f"but the brief used '{candidate.layout_family.value}'. Return the same "
                    f"grounded brief with layout_family set to '{preferred_family}' and its "
                    "sections shaped the way that family requires."
                )
                logger.warning(
                    "Design brief attempt %s ignored the pinned layout (%s); retrying.",
                    attempt + 1,
                    candidate.layout_family.value,
                )
                continue
            if _brief_omits_the_decision(candidate, record):
                if attempt + 1 < attempts:
                    feedback = (
                        "This is a court judgment, but the brief has no holding or outcome "
                        "section. Add one citing holding_or_operative_order and keep the "
                        "other record pointers. A Legal Snaps poster must state what the "
                        "court decided, so choose a family that can display it."
                    )
                    logger.warning(
                        "Design brief attempt %s omitted the court's decision; retrying.",
                        attempt + 1,
                    )
                    continue
                candidate = _with_holding_section(candidate, record)
                resolve_design_brief(candidate, record)
                logger.warning(
                    "The art direction model omitted the court's decision; added the "
                    "record's holding as a grounded section so the poster states it."
                )
            repeats_recent = bool(avoid) and not preferred_family and (
                candidate.layout_family.value in recent_families
                or candidate.layout_key in avoid
            )
            if repeats_recent:
                stale = candidate
                if attempt + 1 < attempts:
                    banned = recent_families or _recent_families(avoid)
                    alternative = _suggest_family(record, banned, len(candidate.sections))
                    feedback = (
                        f"The brief reused '{candidate.layout_family.value}' "
                        f"(structure {candidate.layout_key}), but the most recent posters "
                        f"already used {', '.join(banned) or candidate.layout_family.value}. "
                        "That family is closed for this article. Keep the same record "
                        "pointers and rewrite the brief for a different family"
                        + (f", for example '{alternative}'" if alternative else "")
                        + ", with the number and shape of sections that family requires."
                    )
                    logger.warning(
                        "Design brief attempt %s reused a recent family (%s); retrying.",
                        attempt + 1,
                        candidate.layout_family.value,
                    )
                    continue
                break
            brief = candidate
            break
        except (HFProviderError, ValidationError, DesignBriefError) as e:
            feedback = str(e)
            if attempt + 1 < attempts:
                logger.warning(
                    "Design brief attempt %s rejected; retrying: %s",
                    attempt + 1,
                    feedback,
                )
                continue

    if brief is None and stale is not None:
        banned = recent_families or _recent_families(avoid)
        reshaped = _reshape_family(stale, record, banned)
        if reshaped.layout_family.value != stale.layout_family.value:
            try:
                resolve_design_brief(reshaped, record)
            except DesignBriefError as e:
                logger.warning(
                    "Deterministic family reshape could not be validated (%s); keeping the "
                    "model's grounded brief.",
                    e,
                )
                brief = stale
            else:
                brief = reshaped
                logger.warning(
                    "The art direction model kept returning recent compositions for this "
                    "record; reshaped the same grounded brief from %s to %s so the poster "
                    "does not repeat the previous structure.",
                    stale.layout_family.value,
                    reshaped.layout_family.value,
                )
        else:
            brief = stale

    if brief is None:
        raise HFProviderError(
            "Hugging Face did not return a usable design brief after "
            f"{attempts} attempts: {feedback}"
        )

    if avoid and brief.layout_family.value in recent_families:
        logger.warning(
            "Design brief still matches a recent layout family (%s); no other viable "
            "composition was available for this record.",
            brief.layout_family.value,
        )

    logger.info(
        "Design brief for '%s': %s (%s)",
        brief.headline_source,
        brief.layout_family.value,
        brief.rationale,
    )
    return brief


# ---------------------------------------------------------------------------
# Article-specific artwork (Krea-2-Turbo via Hugging Face Inference Providers)

def build_artwork_prompt(plan: InfographicContentPlan) -> str:
    """
    Build a per-article illustration prompt from this job's validated brief.

    The subject comes from the brief's illustration_concept, not from a fixed cast of legal
    props, so two different articles do not receive the same advocate-with-scales image.
    Precise legal text is never requested from the image model; the SVG renderer draws it.
    """
    brief = plan.design_brief
    concept = (
        (brief.illustration_concept if brief else None)
        or plan.artwork_subject
        or plan.headline
    )
    issue = (brief.central_issue if brief else None) or plan.subtitle or plan.headline
    family = brief.layout_family.value if brief else "editorial layout"
    placement = {
        "landmark_cover": "a compact square spot illustration that will sit to the right of the headline",
        "split_comparison": "a compact spot illustration that will sit beside the headline above two comparison panels",
        "timeline": "a compact spot illustration that will sit beside the headline above a chronological spine",
        "decision_tree": "a compact spot illustration that will sit beside the headline above a legal-test tree",
        "process_flow": "a compact spot illustration that will sit beside the headline above a process flow",
        "argument_outcome": "a compact spot illustration that will sit beside the headline above argument and outcome panels",
    }.get(family, "a compact spot illustration that will sit beside the poster headline")
    return (
        "Premium flat-vector editorial spot illustration for an Indian legal publication, "
        "on a pure white background. "
        f"Article-specific subject: {concept}. "
        f"The legal idea it must communicate: {issue}. "
        f"Format: {placement}, one clear focal subject with generous white space around it. "
        "Use a visual metaphor specific to this article; do not fall back on a generic gavel, "
        "courthouse, scales of justice or anonymous advocate unless the subject explicitly "
        "calls for one. Do not invent legal documents, seals, figures, dates or statistics, "
        "and do not depict a misleading scene. "
        "Never depict weapons, violence, injury, harassment, distress, confrontation or "
        "threatening gestures; for sensitive subject matter prefer a dignified still-life or "
        "abstract symbolic composition over human conflict scenes. "
        "Absolutely no text, letters, words, numbers, logos, watermarks, signatures, banners, "
        "flags, emblems, frames or borders anywhere in the image. "
        "Sophisticated modern editorial vector style: clean geometric silhouettes, crisp edges, "
        "restrained flat two-tone shading, anatomically correct forms, no sketch lines, no "
        "gradients, no 3D, no photorealism, no collage. "
        "Strict palette: warm gold #CFA444, dark slate #2A2E3D, muted charcoal #4A4C5A, white, "
        "plus one restrained warm neutral where a human tone is needed. "
        "The background stays pure white to every edge so the image sits directly on the "
        "poster; no panel, halo, floor, cast shadow, or background architecture. "
        "Balanced square composition with the complete subject visible and uncropped."
    )


async def generate_legal_artwork(
    output_path: str,
    plan: InfographicContentPlan,
) -> Tuple[bool, Optional[str]]:
    """Generate article-specific artwork through HF's native text-to-image task.

    The official client selects the provider's supported native route instead of
    relying on the inconsistently supported OpenAI-compatible images route. The returned
    image is re-encoded as PNG so the SVG always receives the correct data MIME type.
    """
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    token = settings.get_effective_hf_token()
    if not token:
        return False, "No Hugging Face token configured for artwork generation."

    side = getattr(settings, "artwork_max_side", 1024)
    models_to_try = [settings.hf_image_model]
    if "FLUX" in settings.hf_image_model:
        alt = "black-forest-labs/FLUX.1-dev" if "schnell" in settings.hf_image_model else "black-forest-labs/FLUX.1-schnell"
        if alt not in models_to_try:
            models_to_try.append(alt)

    image_bytes = None
    last_error = None
    prompt = build_artwork_prompt(plan)
    neg_prompt = (
        "text, letters, words, numbers, brand names, logo, watermark, signature, "
        "banner, flag, emblem, border, frame, halo, background shape, floor, "
        "cast shadow, collage, split image, duplicate subject, cropped subject, "
        "weapon, gun, knife, violence, blood, injury, harassment, distress, "
        "confrontation, threatening pose, photorealism, 3d, gradients"
    )

    for cur_model in models_to_try:
        for provider in [settings.hf_image_provider, "together", None]:
            try:
                client = AsyncInferenceClient(
                    provider=provider,
                    api_key=token,
                    timeout=ARTWORK_TIMEOUT_SECONDS,
                )
                image = await client.text_to_image(
                    prompt,
                    negative_prompt=neg_prompt,
                    model=cur_model,
                    width=side,
                    height=side,
                )
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                image_bytes = buffer.getvalue()
                if image_bytes and image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 2048:
                    logger.info("Successfully generated artwork with %s via provider %s", cur_model, provider)
                    break
            except Exception as e:
                last_error = e
                logger.warning("Artwork generation with %s via %s failed: %s", cur_model, provider, e)
        if image_bytes and len(image_bytes) >= 2048:
            break

    if not image_bytes or not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, f"All Hugging Face image providers failed for FLUX: {last_error}"

    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, "Generated artwork could not be encoded as a PNG."
    if len(image_bytes) < 2048:
        return False, f"Generated artwork is implausibly small ({len(image_bytes)} bytes), likely blank."

    target.write_bytes(image_bytes)
    logger.info(
        "Artwork for this job written to %s (%d bytes) using %s via %s",
        output_path,
        len(image_bytes),
        settings.hf_image_model,
        settings.hf_image_provider,
    )
    return True, None


# ---------------------------------------------------------------------------
# Per-card pictures: Qwen names the picture, Krea-2-Turbo draws it

def _card_key(text: str) -> str:
    """Normalise card copy so the renderer finds the picture for the same sentence."""
    return " ".join((text or "").split()).lower()


def build_card_subject_prompt(plan: InfographicContentPlan, items: Sequence[str]) -> str:
    """Ask Qwen what each card should depict; the module never maps keywords to icons."""
    brief = plan.design_brief
    concept = (brief.illustration_concept if brief else None) or plan.artwork_subject or plan.headline
    central = (brief.central_issue if brief else None) or plan.subtitle or plan.headline
    listing = "\n".join(f"{index + 1}. {text}" for index, text in enumerate(items))
    return f"""You are the picture editor for Legal Snaps, an Indian legal explainer poster.

Poster headline: {plan.headline}
The article's visual concept: {concept}
The legal idea being explained: {central}

Below are the numbered card sentences that appear on the poster. For EACH sentence,
decide what one picture should sit above it.

{listing}

Rules for every picture subject:
- Name ONE concrete object, place or institution, or one simple dignified human action,
  in five to eleven words.
- Prefer an object, place or institution over a human figure. At most TWO of the pictures
  may feature a person, and only where that sentence is about a person's right or action.
- Every picture must have a different main object from the others. Do not repeat a ballot
  box, a book, a magnifying glass or a sealed envelope; once used, choose another object.
- Never choose a gavel, scales of justice, a courthouse, a judge's bench, or an anonymous
  advocate portrait.
- It must be visually specific to this sentence. Indian civic and legal setting where the
  sentence calls for it (voting, government offices, banks, courts, public records, family,
  work, money).
- No text, letters, numbers, signs with writing, documents with legible lines, logos,
  maps with labels, or flags with emblems. The picture must read without any wording.
- No weapons, violence, injury, distress, confrontation, or threatening gestures. Never
  illustrate a party or a victim as a caricature.
- A simple composition: one subject with generous white space, no background scene.

Return JSON only, exactly this shape, with exactly {len(items)} strings in the same order:
{{"subjects": ["...", "..."]}}"""


def build_card_illustration_prompt(subject: str, plan: InfographicContentPlan) -> str:
    """Render one card picture as a flat pictogram that carries no legal lettering.

    Kept short on purpose: a long style essay dilutes the subject and Krea-2-Turbo starts
    substituting its own stock legal props (gavels, portraits) for the requested object.
    """
    return (
        f"A single flat-vector pictogram on a pure white background: {subject}. "
        "The subject is the only object in the frame, centred and complete, with wide white "
        "margins on every side. Modern editorial vector style for an Indian legal explainer, "
        "clean geometric shapes, flat two-tone shading. "
        "Strict palette: warm gold #CFA444, dark slate #2A2E3D, muted charcoal #4A4C5A, "
        "white, warm ivory #F6EBD2. "
        "No text, letters, words, numbers, logos, watermarks, frames, borders, background "
        "scene, floor, cast shadow, gradients, 3D or photorealism. "
        "Not a gavel, not scales of justice, not a courthouse, not a judge, and not a "
        "standing portrait, unless the subject explicitly names one."
    )


CARD_ART_NEGATIVE_PROMPT = (
    "text, letters, words, numbers, typography, gibberish writing, logo, watermark, "
    "signature, banner, flag, emblem, border, frame, background scene, floor, cast shadow, "
    "collage, split image, duplicate subject, cropped subject, photorealism, 3d, gradients, "
    "gavel, scales of justice, courthouse, weapon, gun, knife, violence, blood, injury, "
    "harassment, distress, confrontation, threatening pose"
)


async def generate_card_subjects_with_hf(
    plan: InfographicContentPlan,
    items: Sequence[str],
) -> List[str]:
    """Use Qwen to choose a concrete picture subject for every card sentence."""
    prompt = build_card_subject_prompt(plan, items)
    last_error: Optional[str] = None
    for attempt in range(CARD_SUBJECT_ATTEMPTS):
        try:
            body = await _hf_chat_completion({
                "model": settings.hf_text_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a precise picture editor. Answer with JSON only and "
                            "never write the poster's legal copy inside the picture."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": CARD_SUBJECT_MAX_TOKENS,
            })
            data = _parse_json_object(_extract_completion_text(body))
        except HFProviderError as e:
            last_error = str(e)
            continue

        raw = data.get("subjects")
        if not isinstance(raw, list):
            last_error = "response had no 'subjects' list"
            continue
        subjects = [" ".join(str(subject).split()) for subject in raw]
        if len(subjects) != len(items) or any(not subject for subject in subjects):
            last_error = f"expected {len(items)} subjects, received {len(subjects)} usable strings"
            continue
        return subjects

    raise HFProviderError(
        f"Qwen did not return a usable picture subject for every card: {last_error or 'no response'}"
    )


async def generate_explainer_illustrations(
    output_dir: str,
    job_id: str,
    plan: InfographicContentPlan,
    record: LegalRecord,
) -> Tuple[Dict[str, str], List[str]]:
    """Generate one Krea picture per explainer card, keyed by the card's exact sentence.

    The renderer only embeds pictures for the sentences that came back; a failed picture is
    reported as a warning and that card renders without artwork. No hand-drawn substitute is
    inserted in its place, and nothing here invents legal content.
    """
    warnings: List[str] = []
    brief = plan.design_brief
    if brief is None:
        return {}, warnings

    resolved = resolve_design_brief(brief, record)
    items: List[str] = []
    seen: set = set()
    for section in resolved.sections:
        if section.kind in {"holding", "outcome"}:
            continue
        for item in section.items:
            key = _card_key(item.text)
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(item.text)
            if len(items) >= CARD_ART_MAX_ITEMS:
                break
        if len(items) >= CARD_ART_MAX_ITEMS:
            break
    if not items:
        return {}, warnings

    token = settings.get_effective_hf_token()
    if not token:
        warnings.append(
            "Card pictures were not generated: no Hugging Face token is configured. "
            "Cards render without artwork."
        )
        return {}, warnings

    try:
        subjects = await generate_card_subjects_with_hf(plan, items)
    except HFProviderError as e:
        warnings.append(
            f"Card pictures were not generated because Qwen could not choose their subjects: "
            f"{e}. Cards render without artwork."
        )
        return {}, warnings

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(CARD_ART_CONCURRENCY)

    try:
        client = AsyncInferenceClient(
            provider=settings.hf_image_provider,
            api_key=token,
            timeout=ARTWORK_TIMEOUT_SECONDS,
        )
    except Exception as e:
        warnings.append(
            f"Card pictures were not generated: could not create the Hugging Face image "
            f"client ({e}). Cards render without artwork."
        )
        return {}, warnings

    async def render_one(index: int, item_text: str, subject: str):
        async with semaphore:
            try:
                image = await client.text_to_image(
                    build_card_illustration_prompt(subject, plan),
                    negative_prompt=CARD_ART_NEGATIVE_PROMPT,
                    model=settings.hf_image_model,
                    width=CARD_ART_SIDE,
                    height=CARD_ART_SIDE,
                )
                image = image.convert("RGB")
                image.thumbnail((CARD_ART_STORED_SIDE, CARD_ART_STORED_SIDE))
                buffer = BytesIO()
                image.save(buffer, format="PNG", optimize=True)
                data = buffer.getvalue()
            except Exception as e:
                return item_text, None, f"card {index + 1} ({subject}): {e}"
            if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 1024:
                return item_text, None, f"card {index + 1} ({subject}): blank or invalid PNG"
            path = target_dir / f"{job_id}_card_{index + 1}.png"
            path.write_bytes(data)
            return (
                item_text,
                "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
                None,
            )

    results = await asyncio.gather(
        *(render_one(index, text, subject) for index, (text, subject) in enumerate(zip(items, subjects)))
    )

    illustrations: Dict[str, str] = {}
    failures: List[str] = []
    for item_text, data_uri, failure in results:
        if data_uri:
            illustrations[_card_key(item_text)] = data_uri
        elif failure:
            failures.append(failure)

    if failures:
        warnings.append(
            f"{len(failures)} of {len(items)} card pictures failed with "
            f"{settings.hf_image_model}: " + "; ".join(failures[:4])
        )
    if not illustrations:
        warnings.append(
            "No card pictures were produced; the poster's cards render without artwork."
        )
    else:
        logger.info(
            "Generated %d/%d card pictures with %s via %s for job %s",
            len(illustrations),
            len(items),
            settings.hf_image_model,
            settings.hf_image_provider,
            job_id,
        )
    return illustrations, warnings
