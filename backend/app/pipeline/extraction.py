import re
import logging
from typing import List, Tuple
from app.config import settings
from app.schemas import ExtractionResult

logger = logging.getLogger(__name__)

# Site chrome, promotional blocks and navigational text that legal sources wrap around
# the real document. Left in place, this boilerplate dominates the head of the text and
# pushes the actual judgment out of the analysis window.
BOILERPLATE_PATTERNS = [
    r"unlock advanced research",
    r"integrated with over",
    r"designed for legal practitioners",
    r"download (as|the) pdf",
    r"cite this (judgment|order|document)",
    r"share this (judgment|order|document|page)",
    r"report (a|an) (error|mistake|issue)",
    r"sign (in|up) to",
    r"subscribe to (our|the)",
    r"advertisement",
    r"cookie",
    r"all rights reserved",
    r"terms of (use|service)",
    r"privacy policy",
    r"follow us on",
    r"join our (whatsapp|telegram)",
    r"notice:?\s*—?",
    r"^---\s*\[?page \d+\]?\s*---$",
    r"^\s*[.\u2024\u00b7\s]{8,}\s*\d+\s*$",
    r"^\s*[\d\s.·|_-]{6,}\s*$",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in BOILERPLATE_PATTERNS]

HEADING_MARKERS = ("###",)

# Paragraphs carrying the operative legal content, used to keep the analysis window
# focused on substance rather than the cover page of a long judgment.
SUBSTANCE_KEYWORDS = [
    "held", "holds", "holding", "we are of the opinion", "ratio", "operative order",
    "conclusion", "order", "directions", "bench", "article ", "section ", "constitution",
    "fundamental right", "right to privacy", "petition", "appeal", "writ", "judgment",
    "issue", "whether", "respectful", "precedent", "statute",
]


def is_boilerplate(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if any(rx.search(stripped) for rx in _COMPILED):
        return True
    # Link/menu fragments: almost no alphabetic content relative to length.
    letters = sum(c.isalpha() for c in stripped)
    return bool(stripped) and letters < max(4, len(stripped) // 4) and len(stripped) < 60


def structure_legal_text(raw_text: str) -> ExtractionResult:
    """
    Sanitize retrieved source text: drop site boilerplate, collapse whitespace, and
    collect section headings. The returned text is what downstream analysis and claim
    validation operate on, so unverifiable site chrome never reaches the model.
    """
    warnings: List[str] = []
    kept: List[str] = []
    headings: List[str] = []
    removed = 0

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        heading = line.startswith(HEADING_MARKERS)
        content = line.lstrip("#").strip() if heading else line
        if is_boilerplate(content):
            removed += 1
            continue
        kept.append(line)
        if heading:
            headings.append(content[:120])

    # Collapse runs of blank lines.
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()

    if len(text) < 400:
        warnings.append(
            f"Only {len(text)} characters of substantive text survived sanitisation; "
            "the source page may be mostly navigation or behind an access restriction."
        )

    return ExtractionResult(
        text=text,
        section_headings=headings[:40],
        line_count=len([l for l in text.splitlines() if l.strip()]),
        char_count=len(text),
        boilerplate_lines_removed=removed,
        warnings=warnings,
    )


def _paragraph_score(paragraph: str) -> float:
    lowered = paragraph.lower()
    hits = sum(1 for kw in SUBSTANCE_KEYWORDS if kw in lowered)
    length_bonus = min(len(paragraph) / 900.0, 2.0)
    return hits + length_bonus


def split_paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def build_analysis_corpus(extraction: ExtractionResult, max_chars: int = None) -> str:
    """
    Assemble the text handed to the analysis model.

    Long judgments place the operative reasoning far from the opening pages, so taking a
    blind prefix silently discards the holding. This keeps the opening block for identity
    and citation, then fills the remaining budget with the highest-substance paragraphs in
    their original document order.
    """
    budget = max_chars or settings.analysis_max_chars
    paragraphs = split_paragraphs(extraction.text)
    if not paragraphs:
        return extraction.text[:budget]

    if sum(len(p) for p in paragraphs) <= budget:
        return "\n\n".join(paragraphs)

    opening_count = max(1, min(4, len(paragraphs)))
    opening = paragraphs[:opening_count]
    rest = paragraphs[opening_count:]

    tail = paragraphs[-1] if len(paragraphs) > opening_count else ""

    scored = sorted(
        ((idx, _paragraph_score(p)) for idx, p in enumerate(rest)),
        key=lambda t: t[1],
        reverse=True,
    )

    used = sum(len(p) for p in opening) + len(tail)
    selected_idx = set(range(opening_count))
    if tail:
        selected_idx.add(len(paragraphs) - 1)

    for idx, _score in scored:
        para = rest[idx]
        if used + len(para) > budget:
            continue
        selected_idx.add(idx + opening_count)
        used += len(para)

    ordered = [paragraphs[i] for i in sorted(selected_idx) if i < len(paragraphs)]
    corpus = "\n\n".join(ordered)

    logger.info(
        "Analysis corpus built: %d/%d paragraphs, %d chars (budget %d)",
        len(ordered), len(paragraphs), len(corpus), budget
    )
    return corpus[:budget]


def count_words(text: str) -> int:
    return len(text.split())
