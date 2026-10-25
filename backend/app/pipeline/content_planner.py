import logging
import re
from datetime import datetime
from typing import List, Optional, Set

from app.schemas import (
    InfographicContentPlan,
    LegalRecord,
    SourceMetadata,
    TakeawayItem,
    ValidationSummary,
)

logger = logging.getLogger(__name__)

# Poster text limits for the Legal Snaps editorial layout: short scannable phrases,
# not paragraphs. Each limit matches a measured line budget in the SVG designer.
OVERVIEW_LIMIT = 330
# Two measured takeaway lines can carry a complete legal clause. The previous
# 58-character budget produced fragments such as "prohibits caste".
TAKEAWAY_LIMIT = 84
COMPARISON_LIMIT = 52
# A portrait poster has room for three subtitle lines. Keep the operative holding
# intact instead of ending a legal sentence on an incomplete phrase.
SUBTITLE_LIMIT = 210

_SUBJECT_PREFIX = re.compile(
    r"^(?:the\s+)?(?:supreme court|high court|court|tribunal|bench|state|union|"
    r"government|petitioner|respondent|appellant|complainant)\s+",
    re.IGNORECASE,
)

# Preferred places to end a bullet. Cutting here keeps the phrase grammatical
# instead of trailing off, which is why bullets never end with an ellipsis.
_PHRASE_BOUNDARIES = (
    ", ",
    "; ",
    " — ",
    " - ",
    " and ",
    " but ",
    " to ",
    " for ",
    " in ",
    " by ",
    " with ",
    " on ",
    " under ",
    " that ",
    " which ",
)

_TRAILING_FILLER = re.compile(
    r"\s+(?:and|or|of|to|for|in|on|by|with|the|a|an|that|which|its|their|from|at|as)$",
    re.IGNORECASE,
)

# A bullet that ends on one of these is cut mid-thought ("...must align their").
_WEAK_ENDINGS = re.compile(
    r"\b(?:the|a|an|and|or|but|of|to|for|in|on|by|with|from|as|at|their|its|his|her|"
    r"our|your|this|that|these|those|must|will|shall|should|would|can|could|may|might|"
    r"is|are|was|were|be|been)\s*$",
    re.IGNORECASE,
)

# These nouns need their qualifier ("right to dignity", "principle of equality").
# Ending a poster bullet on them leaves a grammatically complete-looking fragment.
_INCOMPLETE_ENDINGS = re.compile(r"\b(?:the\s+)?(?:right|principle)\s*$", re.IGNORECASE)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "that", "this",
    "is", "are", "was", "were", "be", "been", "by", "with", "as", "at", "from",
    "it", "its", "their", "has", "have", "had", "not", "but", "which", "while",
}


def _clean_whitespace(text: Optional[str]) -> str:
    return " ".join((text or "").split())


def _shorten(text: Optional[str], limit: int) -> str:
    """Fit text to a budget at a sentence or word boundary, never mid-word."""
    cleaned = _clean_whitespace(text)
    if len(cleaned) <= limit:
        return cleaned

    window = cleaned[: limit + 1]
    for marker in (". ", "; "):
        boundary = window.rfind(marker)
        if boundary >= int(limit * 0.55):
            return cleaned[: boundary + 1].strip()

    comma = window.rfind(", ")
    if comma >= int(limit * 0.72):
        return cleaned[:comma].rstrip(" ,;:-") + "…"

    cut = cleaned[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-.") + "…"


def _content_tokens(text: Optional[str]) -> Set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _overlap(a: Optional[str], b: Optional[str]) -> float:
    left, right = _content_tokens(a), _content_tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _contained_in(candidate: Optional[str], reference: Optional[str]) -> float:
    """Share of the candidate's substance already stated in the reference."""
    left, right = _content_tokens(candidate), _content_tokens(reference)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left)


def _is_question(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    return (
        stripped.endswith("?")
        or lowered.startswith(("is ", "are ", "does ", "do ", "did ", "whether ", "should ", "can "))
    )


def _clean_publisher(publisher: Optional[str]) -> Optional[str]:
    """Drop SEO tails such as '| Best Supreme Court Lawyers in Delhi'."""
    if not publisher:
        return None
    parts = [p.strip() for p in re.split(r"\s*[|·•]\s*", publisher) if p.strip()]
    if not parts:
        return None
    promo = re.compile(
        r"\b(best|top|leading|award[- ]winning|no\.?\s*1|lawyers in|advocates in|"
        r"law firm in|solicitors in)\b",
        re.IGNORECASE,
    )
    for part in parts:
        if not promo.search(part):
            return part
    return parts[0]


def _build_artwork_subject(record: LegalRecord) -> str:
    """Article-specific imagery brief for the image model, built from this record only."""
    # Keep the brief free of courtroom scenery: image models otherwise add flags,
    # benches and emblems that overpower the restrained editorial palette.
    themes: List[str] = ["an isolated editorial legal still life"]
    themes.extend(_shorten(s, 64).lower() for s in record.relevant_statutes[:2])
    themes.extend(_shorten(p, 72).lower() for p in record.practical_implications[:1])
    if len(themes) == 1 and record.material_facts:
        themes.append(_shorten(record.material_facts[0], 72).lower())
    # Party names such as "Union of India" make image models add national flags.
    # The legal themes still make the artwork article-specific without national symbols.
    return "Visual themes: " + ", ".join(themes[:4])


def _build_hook(record: LegalRecord, publisher: Optional[str]) -> Optional[str]:
    """One readable line under the headline, like the sample posters.

    The article's own title is the best hook when it differs from the case name;
    otherwise the operative holding supplies it.
    """
    article_title = _clean_whitespace(record.article_title)
    case_name = _clean_whitespace(record.case_name)
    if (
        article_title
        and article_title.lower() != case_name.lower()
        and 20 <= len(article_title) <= SUBTITLE_LIMIT
    ):
        return article_title.rstrip(" .")

    holding = _shorten(record.holding_or_operative_order, SUBTITLE_LIMIT).rstrip(" .")
    if len(holding) >= 25:
        return holding

    court = _clean_whitespace(record.court_or_tribunal)
    if court:
        return court
    return publisher


def _build_meta(record: LegalRecord) -> Optional[str]:
    """Court, citation and decision date in one quiet line under the hook."""
    parts: List[str] = []
    for value in (record.court_or_tribunal, record.citation, record.judgment_date):
        text = _clean_whitespace(value)
        if text and text not in parts:
            parts.append(text)
    return "   ·   ".join(parts) if parts else None


def _build_overview(record: LegalRecord) -> str:
    holding = _clean_whitespace(record.holding_or_operative_order)
    overview = holding
    if len(overview) < 140 and record.material_facts:
        overview = f"{_clean_whitespace(record.material_facts[0])} {overview}".strip()
    if not overview:
        overview = _clean_whitespace(record.article_title)
    return _shorten(overview, OVERVIEW_LIMIT)


def _short_phrase(text: Optional[str], limit: int) -> str:
    """Compress a sentence into a scannable poster bullet.

    Drops the subject ("The Court ...") and ends at a real phrase boundary, so a
    bullet reads as a statement rather than a truncated sentence. No ellipsis is
    ever added: the poster style has no trailing dots.
    """
    cleaned = _clean_whitespace(text).rstrip(" .")
    question = cleaned.endswith("?")
    if question:
        cleaned = cleaned[:-1].rstrip()

    # "not merely X but Y" carries its real point in Y; keep that instead of the
    # negative half, which would otherwise become a dangling fragment.
    contrast = re.match(
        r"^.*?\bnot\s+(?:merely|only|just)\b.*?\bbut\s+(.+)$", cleaned, re.IGNORECASE
    )
    if contrast and len(contrast.group(1).strip(" .,;:")) >= 24:
        cleaned = contrast.group(1).strip()

    stripped = _SUBJECT_PREFIX.sub("", cleaned, count=1)
    # Never leave a conjunction or preposition dangling after dropping the subject.
    if re.match(r"^(?:and|or|of)\b", stripped, re.IGNORECASE):
        stripped = cleaned
    cleaned = re.sub(r"^(?:that|which)\s+", "", stripped, flags=re.IGNORECASE)

    # A phrase only a few characters over budget reads better whole than clipped.
    if len(cleaned) > limit + 12:
        in_budget = max(
            (cleaned.rfind(marker, 0, limit + 1) for marker in _PHRASE_BOUNDARIES),
            default=-1,
        )
        cut = -1
        if in_budget >= max(18, int(limit * 0.7)):
            # A solid short bullet already ends inside the budget.
            cut = in_budget
        else:
            # Otherwise finish the clause just past the budget rather than stopping
            # mid-phrase ("...different State"); a bullet must read as a statement.
            starts = [
                cleaned.find(marker, max(0, limit - 4))
                for marker in _PHRASE_BOUNDARIES
            ]
            starts = [p for p in starts if p != -1]
            overrun = min(starts) if starts else -1
            if 0 <= overrun <= limit + 30:
                cut = overrun
            elif in_budget >= int(limit * 0.45):
                cut = in_budget
        if cut >= 0:
            phrase = cleaned[:cut]
            if _WEAK_ENDINGS.search(phrase):
                # "...must align their" is not an ending; step to the next boundary.
                starts = [cleaned.find(m, cut + 1) for m in _PHRASE_BOUNDARIES]
                starts = [p for p in starts if p != -1]
                following = min(starts) if starts else -1
                if 0 <= following <= cut + 14:
                    cut = following
            phrase = cleaned[:cut]
            if _INCOMPLETE_ENDINGS.search(phrase):
                earlier = max(
                    (phrase.rfind(marker) for marker in _PHRASE_BOUNDARIES),
                    default=-1,
                )
                if earlier >= 18:
                    cut = earlier
            cleaned = cleaned[:cut]
        elif len(cleaned) > limit + 30:
            cleaned = cleaned[:limit]
            if " " in cleaned:
                cleaned = cleaned.rsplit(" ", 1)[0]
        # else: no boundary exists and the sentence is only slightly long - keep it
        # whole rather than cutting off its predicate ("...do not render the").
        cleaned = _TRAILING_FILLER.sub("", cleaned)

    cleaned = cleaned.strip(" ,;:-.")
    if not cleaned:
        return ""
    cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned + "?" if question else cleaned


def _takeaway_icon(text: str, index: int) -> str:
    if re.search(
        r"\b(prohibit\w*|banned?|barred?|must not|shall not|penalt\w*|restrict\w*)\b",
        text,
        re.IGNORECASE,
    ):
        return "prohibited"
    return ("gavel", "court", "book")[index % 3]


def _build_takeaways(record: LegalRecord) -> List[TakeawayItem]:
    """Four distinct scannable points; questions stay in the comparison column."""
    chosen: List[str] = []
    sources: List[str] = []

    def add(candidate: Optional[str]) -> None:
        text = _clean_whitespace(candidate)
        if len(text) < 25 or _is_question(text):
            return
        if any(_overlap(text, reference) > 0.72 for reference in sources):
            return
        # The overview already carries the holding; repeating it wastes a takeaway.
        if _contained_in(text, record.holding_or_operative_order) > 0.6:
            return
        phrase = _short_phrase(text, TAKEAWAY_LIMIT)
        if len(phrase) < 18:
            return
        if any(_overlap(phrase, existing) > 0.6 for existing in chosen):
            return
        sources.append(text)
        chosen.append(phrase)

    for item in record.legal_reasoning:
        add(item)
        if len(chosen) == 4:
            break
    if len(chosen) < 4:
        for item in record.practical_implications:
            add(item)
            if len(chosen) == 4:
                break
    if len(chosen) < 3:
        for fact in record.material_facts:
            add(fact)
            if len(chosen) == 4:
                break
    if len(chosen) < 3:
        for statute in record.relevant_statutes:
            add(f"Key statute: {_clean_whitespace(statute)}")
            if len(chosen) == 4:
                break

    if not chosen:
        fallback = _short_phrase(
            record.holding_or_operative_order or record.article_title, TAKEAWAY_LIMIT
        )
        return [TakeawayItem(icon_type="gavel", description=fallback or "Legal Snaps brief")]

    icons = [_takeaway_icon(text, i) for i, text in enumerate(sources[: len(chosen)])]
    return [
        TakeawayItem(icon_type=icons[i], description=text)
        for i, text in enumerate(chosen[:4])
    ]


def _comparison_item(text: Optional[str]) -> str:
    """One comparison bullet: questions stay whole, statements are compressed."""
    cleaned = _clean_whitespace(text)
    if not cleaned:
        return ""
    if _is_question(cleaned):
        # A truncated question reads as a different question; keep it intact.
        if len(cleaned) > 140:
            cut = cleaned[:140]
            cut = cut.rsplit(" ", 1)[0].rstrip(" ,;:-")
            return cut + "?"
        return cleaned
    return _short_phrase(cleaned, COMPARISON_LIMIT)


def _pick_items(
    candidates: List[str], taken: List[str], limit: int = 3
) -> List[str]:
    """Compress candidates, dropping anything the poster already says elsewhere."""
    valid: List[str] = []
    used = {phrase.lower() for phrase in taken}
    for candidate in candidates:
        item = _comparison_item(candidate)
        if not item or item.lower() in used:
            continue
        used.add(item.lower())
        valid.append(item)
    # Prefer bullets that end on a real phrase over ones cut mid-thought.
    strong = [i for i in valid if not _WEAK_ENDINGS.search(i)]
    weak = [i for i in valid if _WEAK_ENDINGS.search(i)]
    return (strong + weak)[:limit]


def _build_comparison(record: LegalRecord, taken: Optional[Set[str]] = None):
    """Return (title, old_title, old_items, new_title, new_items) or five Nones."""
    seen = sorted(taken or set())
    reasoning = [r for r in record.legal_reasoning if not _is_question(r)]
    implications = [p for p in record.practical_implications if not _is_question(p)]
    analysis = _pick_items(reasoning, seen)
    if len(analysis) < 3:
        # When the takeaways already used most reasoning points, add distinct
        # implications instead of repeating the same sentences in the card.
        for item in _pick_items(implications, seen):
            if item not in analysis:
                analysis.append(item)
            if len(analysis) == 3:
                break
    if len(analysis) < 2:
        analysis = _pick_items(reasoning + implications, [])

    statutes = [_clean_whitespace(s).rstrip(" .") for s in record.relevant_statutes[:3]]
    if len(statutes) >= 2 and len(analysis) >= 2:
        return (
            "The Law and the Ruling",
            "THE LAW",
            statutes,
            "THE COURT'S READING",
            analysis,
        )
    if len(record.questions_or_issues) >= 2 and (reasoning or implications):
        return (
            "Issues and Analysis",
            "THE ISSUES",
            [_comparison_item(q) for q in record.questions_or_issues[:2]],
            "THE ANALYSIS",
            analysis,
        )
    if record.material_facts and implications:
        return (
            "Context and Consequence",
            "THE FACTS",
            _pick_items(record.material_facts, []),
            "THE IMPACT",
            _pick_items(implications, seen),
        )
    return (None, None, [], None, [])


def plan_infographic_content(
    record: LegalRecord,
    validation: ValidationSummary,
    source_meta: Optional[SourceMetadata] = None,
) -> InfographicContentPlan:
    """
    Transforms ANY legal document into the Legal Snaps editorial format.
    All content is derived from the actual LegalRecord — no hardcoded templates.

    Layout: Header Icon + Title + Subtitle -> Overview Card -> Key Takeaways -> Dual Column Comparison -> Gold Footer
    """
    headline = _clean_whitespace(record.case_name or record.article_title) or "Legal Snaps Brief"
    publisher = _clean_publisher(source_meta.publisher if source_meta else None)
    subtitle = _build_hook(record, publisher)
    meta_line = _build_meta(record)
    overview = _build_overview(record)
    takeaways = _build_takeaways(record)

    takeaway_text = {t.description.lower() for t in takeaways}
    comparison_title, old_title, old_items, new_title, new_items = _build_comparison(
        record, takeaway_text
    )

    footer_date = _clean_whitespace(record.judgment_date) or datetime.now().strftime("%d %B %Y")

    footnote = None
    if validation.total_claims > 0:
        footnote = (
            f"Legal Snaps verified {validation.verified_claims}/{validation.total_claims} "
            "claims against the retrieved source text."
        )

    verification_note = None
    if validation.has_critical_unverified:
        verification_note = (
            f"{validation.unverified_claims} of {validation.total_claims} claims "
            "could not be verified against the source - manual legal verification required."
        )
    elif validation.unverified_claims:
        verification_note = (
            f"{validation.unverified_claims} supporting claim(s) unverified against the source."
        )

    header_icon = "scales" if record.is_court_judgment else "gavel"

    return InfographicContentPlan(
        headline=headline,
        subtitle=subtitle,
        meta_line=meta_line,
        header_icon=header_icon,
        overview_text=overview,
        takeaways=takeaways,
        comparison_title=comparison_title or "",
        comparison_old_title=old_title or "",
        comparison_old_items=old_items,
        comparison_new_title=new_title or "",
        comparison_new_items=new_items,
        comparison_footnote=footnote,
        footer_brand="Legal Snaps",
        footer_date=footer_date,
        source_url=source_meta.url if source_meta else None,
        publisher=publisher,
        verification_note=verification_note,
        artwork_subject=_build_artwork_subject(record),
        analysis_source=record.analysis_source,
    )
