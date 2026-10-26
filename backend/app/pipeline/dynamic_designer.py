"""Article-specific Legal Snaps art direction.

The validated LegalRecord supplies the legal text; the design brief supplies the
composition. Each layout family below draws different geometry and hierarchy rather than
reusing one poster template with new words.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from app.schemas import InfographicContentPlan, LegalRecord
from app.pipeline.design_brief import (
    ResolvedBrief,
    ResolvedSection,
    resolve_design_brief,
)
from app.pipeline.svg_designer import (
    CARD_BORDER,
    DARK_GRAY,
    DESIGN_WIDTH,
    FOOTER_H,
    FONT_STACK,
    GOLD_SOFT,
    HEADLINE_DARK,
    MUTED_TEXT,
    PAD,
    PRIMARY_GOLD,
    _wrap,
    escape_xml,
    render_header_icon,
    render_takeaway_icon,
)

logger = logging.getLogger(__name__)

WHITE = "#FFFFFF"
INK = HEADLINE_DARK
GRAY = DARK_GRAY
GOLD = PRIMARY_GOLD
SOFT = GOLD_SOFT
BORDER = CARD_BORDER
MUTED = MUTED_TEXT
PANEL_INK = "#232836"
PANEL_TEXT = "#EAEAEE"
INNER_W = DESIGN_WIDTH - PAD * 2

SCALES = (
    2.00, 1.90, 1.82, 1.74, 1.66, 1.58, 1.50, 1.42, 1.35, 1.28,
    1.22, 1.16, 1.10, 1.05, 1.00, 0.95, 0.90, 0.85, 0.80, 0.75,
    0.70, 0.65, 0.60,
)

# Below this the type hits its pixel floors and the poster reads as fine print, so the
# fitter prefers to drop a section and keep the composition legible.
READABLE_SCALE_FLOOR = 0.85

# Body copy is measured, never clipped: every text block gets enough line allowance to hold
# the whole sentence, and the scale ladder shrinks or sheds a section instead of ellipsising
# legal wording.
BODY_LINE_BUDGET = 12

FAMILY_LABELS = {
    "landmark_cover": "LANDMARK RULING",
    "split_comparison": "SIDE BY SIDE",
    "timeline": "MATTER TIMELINE",
    "decision_tree": "LEGAL TEST",
    "statutory_map": "STATUTORY MAP",
    "chart_led": "BY THE NUMBERS",
    "process_flow": "PROCESS FLOW",
    "argument_outcome": "ARGUMENT v OUTCOME",
    "briefing_sheet": "EXPLAINER BRIEFING",
    "hybrid": "EDITORIAL BRIEF",
}


@dataclass(frozen=True)
class _Ctx:
    plan: InfographicContentPlan
    record: LegalRecord
    brief: ResolvedBrief
    sections: List[ResolvedSection]
    canvas_h: float
    footer_h: float
    avail: float
    scale: float
    artwork: Optional[str]
    # Model-generated card pictures, keyed by normalised card sentence. Empty when the
    # image model produced none, in which case cards carry no picture at all.
    illustrations: Dict[str, str] = field(default_factory=dict)

    def u(self, value: float, floor: int = 4) -> int:
        return max(floor, round(value * self.scale))

    def font(self, value: float, floor: int = 13) -> int:
        return max(floor, round(value * self.scale))


def _s(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _rect(
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str = "none",
    stroke: Optional[str] = None,
    radius: int = 8,
    stroke_width: float = 1.2,
    opacity: Optional[float] = None,
) -> str:
    common = f'x="{_s(x)}" y="{_s(y)}" width="{_s(width)}" height="{_s(height)}" rx="{radius}" '
    if fill != "none":
        common += f'fill="{fill}" '
    else:
        common += 'fill="none" '
    if opacity is not None:
        common += f'opacity="{opacity}" '
    if stroke:
        common += f'stroke="{stroke}" stroke-width="{stroke_width}"'
    else:
        common += 'stroke="none"'
    return f"<rect {common}/>\n"


def _line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    stroke: str = GOLD,
    width: float = 1.5,
    dash: Optional[str] = None,
    opacity: Optional[float] = None,
) -> str:
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    extra += f' opacity="{opacity}"' if opacity is not None else ""
    return (
        f'<line x1="{_s(x1)}" y1="{_s(y1)}" x2="{_s(x2)}" y2="{_s(y2)}" '
        f'stroke="{stroke}" stroke-width="{width}" stroke-linecap="round"{extra}/>\n'
    )


def _circle(
    cx: float,
    cy: float,
    radius: float,
    fill: str = WHITE,
    stroke: Optional[str] = GOLD,
    stroke_width: float = 2,
) -> str:
    return (
        f'<circle cx="{_s(cx)}" cy="{_s(cy)}" r="{_s(radius)}" fill="{fill}" '
        f'stroke="{stroke or "none"}" stroke-width="{stroke_width}"/>\n'
    )


def _polygon(points: Sequence[Tuple[float, float]], fill: str, stroke: Optional[str] = None, width: float = 1) -> str:
    rendered = " ".join(f"{_s(x)},{_s(y)}" for x, y in points)
    tail = f' stroke="{stroke}" stroke-width="{width}"' if stroke else ""
    return f'<polygon points="{rendered}" fill="{fill}"{tail}/>\n'


def _illustration_key(text: str) -> str:
    return " ".join((text or "").split()).lower()


def _illustration_for(ctx: _Ctx, text: str) -> Optional[str]:
    """The model-generated picture that belongs to this exact card sentence, if one exists."""
    if not ctx.illustrations:
        return None
    return ctx.illustrations.get(_illustration_key(text))


def _card_art_tile(
    parts: List[str],
    uri: Optional[str],
    x: float,
    y: float,
    side: float,
    radius: int,
) -> bool:
    """Draw a model-generated picture in a rounded white tile. No drawn substitute exists."""
    if not uri:
        return False
    clip_id = f"cardArt{int(round(x))}x{int(round(y))}"
    parts.append(
        f'<defs><clipPath id="{clip_id}"><rect x="{_s(x)}" y="{_s(y)}" '
        f'width="{_s(side)}" height="{_s(side)}" rx="{radius}"/></clipPath></defs>\n'
    )
    parts.append(_rect(x, y, side, side, WHITE, "#E9E0CF", radius, 1.0))
    parts.append(
        f'<image class="card-art" href="{uri}" xlink:href="{uri}" '
        f'x="{_s(x)}" y="{_s(y)}" width="{_s(side)}" height="{_s(side)}" '
        f'preserveAspectRatio="xMidYMid meet" clip-path="url(#{clip_id})"/>\n'
    )
    return True


def _path(d: str, stroke: str = GOLD, width: float = 2, fill: str = "none", opacity: Optional[float] = None) -> str:
    extra = f' opacity="{opacity}"' if opacity is not None else ""
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"{extra}/>\n'


def _text(
    lines: List[str],
    x: float,
    y: float,
    line_height: int,
    size: int,
    weight: str = "400",
    fill: str = GRAY,
    anchor: Optional[str] = None,
    letter_spacing: Optional[float] = None,
) -> Tuple[str, float]:
    if not lines:
        return "", y
    anchor_attr = f' text-anchor="{anchor}"' if anchor else ""
    spacing = f' letter-spacing="{letter_spacing}"' if letter_spacing is not None else ""
    tspans = "".join(
        f'<tspan x="{_s(x)}" y="{_s(y + index * line_height)}">{escape_xml(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    markup = (
        f'<text{anchor_attr} fill="{fill}" font-size="{size}" font-weight="{weight}" '
        f'font-family="{FONT_STACK}"{spacing}>{tspans}</text>\n'
    )
    return markup, y + (len(lines) - 1) * line_height


def _block(
    text: str,
    x: float,
    y: float,
    width: float,
    size: int,
    weight: str,
    fill: str,
    line_height: Optional[int] = None,
    max_lines: int = 3,
    anchor: Optional[str] = None,
    letter_spacing: Optional[float] = None,
) -> Tuple[str, float]:
    lines = _wrap(text, max(80, round(width)), size, max_lines, weight, uppercase=weight == "800" and size <= 18)
    lh = line_height or round(size * 1.38)
    markup, bottom = _text(lines, x, y, lh, size, weight, fill, anchor, letter_spacing)
    return markup, bottom + round(size * 0.32)


def _heading(text: str) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned.upper() if cleaned else "LEGAL BRIEF"


def _truncated(lines: Sequence[str]) -> bool:
    """True when _wrap had to ellipsise; legal copy is never allowed to be cut off."""
    return bool(lines) and lines[-1].endswith("…")


def _has_cut_copy(parts: Sequence[str]) -> bool:
    """Detect an ellipsis anywhere in a finished composition.

    _wrap only ever emits "…" when a sentence did not fit the box it was given, so a
    candidate containing one would ship truncated legal text. The scale ladder treats that
    as a failed fit and keeps looking for a size where every sentence stays whole.
    """
    return any("…" in part for part in parts)


def _copy_tokens(text: str) -> set:
    return {token for token in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(token) > 2}


def _copy_overlaps(a: str, b: str) -> bool:
    left, right = _copy_tokens(a), _copy_tokens(b)
    if not left or not right:
        return False
    return len(left & right) / min(len(left), len(right)) > 0.72


def _brand_header(ctx: _Ctx, family_text: str) -> Tuple[List[str], float]:
    parts: List[str] = []
    y = PAD
    mark_scale = 0.26
    parts.append(
        f'<g transform="translate({PAD}, {y - 3}) scale({mark_scale:.3f})">'
        f'{render_header_icon("scales", GOLD, GRAY)}</g>\n'
    )
    word_size = ctx.font(14)
    word_y = y + ctx.u(16)
    markup, word_bottom = _text(
        ["LEGAL SNAPS"],
        x=PAD + 38,
        y=word_y,
        line_height=word_size,
        size=word_size,
        weight="800",
        fill=INK,
        letter_spacing=2.8,
    )
    parts.append(markup)

    court = (ctx.record.court_or_tribunal or "SUPREME COURT OF INDIA").upper()
    topic = (ctx.record.legislation_or_article_type or "CONSTITUTIONAL LAW").upper()
    kicker_text = f"{court} • {topic}" if court and topic != court else (court or "CONSTITUTIONAL LAW")
    kicker_markup, _ = _text(
        [kicker_text[:48]],
        x=PAD,
        y=y + ctx.u(32),
        line_height=ctx.font(10, 8),
        size=ctx.font(10, 8),
        weight="700",
        fill=GOLD,
        letter_spacing=1.8,
    )
    parts.append(kicker_markup)

    rule_y = y + ctx.u(38)
    parts.append(_line(PAD, rule_y, DESIGN_WIDTH - PAD, rule_y, "#E5DFD2", 1.1))
    return parts, rule_y + ctx.u(12)


def _doc_label(record: LegalRecord) -> str:
    doc_type = (record.legislation_or_article_type or "").strip().replace("-", " ")
    if not doc_type:
        doc_type = "court judgment" if record.is_court_judgment else "legal document"
    court = " ".join((record.court_or_tribunal or "").split())
    if court and court.lower() not in doc_type.lower():
        return f"{doc_type} · {court}"
    return doc_type


def _headline(
    ctx: _Ctx,
    y: float,
    width: Optional[int] = None,
    x: float = PAD,
    max_lines: int = 4,
    base_sizes: Optional[Dict[str, int]] = None,
    budget_ratio: float = 0.22,
) -> Tuple[List[str], float]:
    parts: List[str] = []
    box_w = width or INNER_W
    kicker_size = ctx.font(13, 11)
    kicker, _ = _text(
        [_doc_label(ctx.record).upper()],
        x=x,
        y=y + kicker_size,
        line_height=kicker_size,
        size=kicker_size,
        weight="700",
        fill=GOLD,
        letter_spacing=1.8,
    )
    parts.append(kicker)
    scale = ctx.brief.headline_scale
    hl_len = len(ctx.brief.headline)
    if hl_len > 60:
        base_sizes = base_sizes or {"compact": 28, "standard": 34, "dramatic": 40}
    elif hl_len > 35:
        base_sizes = base_sizes or {"compact": 32, "standard": 38, "dramatic": 44}
    else:
        base_sizes = base_sizes or {"compact": 36, "standard": 42, "dramatic": 48}
    base_size = base_sizes.get(scale, 38)
    size = ctx.font(base_size, 22)
    budget = ctx.avail * budget_ratio
    floor = ctx.font(20, 16)
    hl_len = len(ctx.brief.headline)
    lines_limit = max_lines if hl_len <= 55 else max(max_lines, 5)
    headline_lines: List[str] = []
    while True:
        lh = round(size * 1.18)
        headline_lines = _wrap(
            ctx.brief.headline.upper(),
            box_w,
            size,
            lines_limit,
            "800",
            uppercase=True,
            balance=True,
        )
        block_h = kicker_size + ctx.u(22) + max(1, len(headline_lines)) * lh + ctx.u(16)
        if (block_h <= budget or size <= floor) and not _truncated(headline_lines):
            break
        if size <= 16:
            break
        size = max(16, round(size * 0.92))
    title_x = x + box_w / 2
    title, title_bottom = _text(
        headline_lines,
        x=title_x if ctx.brief.headline_alignment == "center" else x,
        y=y + kicker_size + ctx.u(22) + size,
        line_height=lh,
        size=size,
        weight="800",
        fill=INK,
        anchor="middle" if ctx.brief.headline_alignment == "center" else None,
        letter_spacing=0.2,
    )
    parts.append(title)
    return parts, title_bottom + ctx.u(16)


def _deck_and_meta(ctx: _Ctx, y: float, width: int = INNER_W, x: float = PAD) -> Tuple[List[str], float]:
    parts: List[str] = []
    cursor = y
    subtitle = " ".join((ctx.plan.subtitle or "").split())
    section_texts = [item.text for section in ctx.sections for item in section.items]
    already_said = (
        _copy_overlaps(subtitle, ctx.brief.headline)
        or any(_copy_overlaps(subtitle, text) for text in section_texts)
    )
    if subtitle and not already_said:
        size = ctx.font(19, 12)
        markup, cursor = _block(
            subtitle, x, cursor + size, width, size, "400", GRAY, max_lines=2
        )
        parts.append(markup)
        cursor += ctx.u(10)
    meta = " ".join((ctx.plan.meta_line or "").split()).upper()
    if meta:
        size = ctx.font(12, 9)
        markup, cursor = _block(
            meta, x, cursor + size, width, size, "600", MUTED, max_lines=2, letter_spacing=1.1
        )
        parts.append(markup)
    return parts, cursor + ctx.u(24)


def _spot_artwork(ctx: _Ctx, x: float, y: float, side: int) -> Tuple[str, float]:
    if not ctx.artwork:
        return "", y
    clip_id = f"spotClip_{int(x)}_{int(y)}"
    markup = (
        f'<defs>\n'
        f'  <clipPath id="{clip_id}">\n'
        f'    <rect x="{_s(x)}" y="{_s(y)}" width="{side}" height="{side}" rx="{ctx.u(10)}" ry="{ctx.u(10)}"/>\n'
        f'  </clipPath>\n'
        f'</defs>\n'
        f'<image x="{_s(x)}" y="{_s(y)}" width="{side}" height="{side}" '
        f'href="{ctx.artwork}" xlink:href="{ctx.artwork}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip_id})"/>\n'
        f'<rect x="{_s(x)}" y="{_s(y)}" width="{side}" height="{side}" rx="{ctx.u(10)}" fill="none" stroke="#E9E0CF" stroke-width="1.2"/>\n'
    )
    return markup, y + side


def _headline_with_spot(
    ctx: _Ctx,
    y: float,
    base_width: int,
    spot_side: int = 150,
    base_sizes: Optional[Dict[str, int]] = None,
    budget_ratio: float = 0.34,
) -> Tuple[List[str], float]:
    """Headline plus the article's FLUX spot illustration when one was generated.

    The spot sits in the right margin beside the title; the headline narrows so text and
    artwork never collide, and the layout fitter still sees the true block height.
    """
    spot = ctx.u(spot_side) if ctx.artwork else 0
    head_w = base_width
    if spot:
        head_w = max(int(INNER_W * 0.58), base_width - spot - ctx.u(20))
    hl_len = len(ctx.brief.headline)
    lines_budget = 5 if hl_len > 55 else 4
    parts, bottom = _headline(
        ctx,
        y,
        head_w,
        max_lines=lines_budget,
        base_sizes=base_sizes,
        budget_ratio=budget_ratio,
    )
    if spot:
        art_y = y + ctx.u(10)
        art, _ = _spot_artwork(ctx, DESIGN_WIDTH - PAD - spot, art_y, spot)
        parts.append(art)
        bottom = max(bottom, art_y + spot)
    return parts, bottom


def _sections_by_priority(ctx: _Ctx) -> List[ResolvedSection]:
    ordered: List[ResolvedSection] = []
    for emphasis in ("primary", "secondary", "quiet"):
        ordered.extend(section for section in ctx.sections if section.emphasis == emphasis)
    seen = set()
    return [s for s in ordered if not (id(s) in seen or seen.add(id(s)))]


def _deduped_items(ctx: _Ctx, sections: Optional[Sequence[ResolvedSection]] = None, limit: int = 6) -> List[ResolvedSection]:
    """Flatten and remove a repeated record pointer without dropping unique legal content."""
    chosen: List[ResolvedSection] = []
    used = set()
    remaining = limit
    for section in sections or ctx.sections:
        items = []
        for item in section.items:
            if remaining <= 0:
                break
            key = item.text.lower()
            if key in used:
                continue
            used.add(key)
            items.append(item)
            remaining -= 1
        if items:
            chosen.append(
                ResolvedSection(
                    heading=section.heading,
                    kind=section.kind,
                    emphasis=section.emphasis,
                    items=items,
                )
            )
        if remaining <= 0:
            break
    return chosen


def _section_by_kinds(ctx: _Ctx, *kinds: str) -> Optional[ResolvedSection]:
    for section in _sections_by_priority(ctx):
        if section.kind in kinds:
            return section
    return None


def _outcome_section(ctx: _Ctx) -> Optional[ResolvedSection]:
    return _section_by_kinds(ctx, "outcome", "holding")


def _measure_item_lines(
    ctx: _Ctx,
    items: Sequence[str],
    width: int,
    size: int,
    per_item: int = 2,
    weight: str = "400",
) -> List[List[str]]:
    return [
        _wrap(text, max(60, width), size, per_item, weight, uppercase=False)
        for text in items
    ]


def _item_block_height(ctx: _Ctx, line_groups: List[List[str]], size: int, gap: int) -> int:
    lh = round(size * 1.4)
    return sum(max(1, len(lines)) * lh for lines in line_groups) + gap * max(0, len(line_groups) - 1)


def _items_down(
    parts: List[str],
    x: float,
    y: float,
    groups: List[List[str]],
    size: int,
    fill: str = GRAY,
    weight: str = "400",
    gap: int = 18,
    anchor: Optional[str] = None,
) -> float:
    lh = round(size * 1.4)
    cursor = y + size
    for lines in groups:
        markup, bottom = _text(lines, x, cursor, lh, size, weight, fill, anchor=anchor)
        parts.append(markup)
        # Advance by the whole line box plus the gap. Adding only the gap after the last
        # baseline put consecutive one-line paragraphs 13 units apart on a 22-unit line,
        # which printed the second sentence on top of the first.
        cursor = bottom + lh + gap
    return cursor


def _section_card(
    ctx: _Ctx,
    section: ResolvedSection,
    x: float,
    y: float,
    width: int,
    *,
    heading_size: Optional[int] = None,
    body_size: Optional[int] = None,
    per_item_lines: int = BODY_LINE_BUDGET,
    fill: str = WHITE,
    stroke: Optional[str] = BORDER,
    heading_fill: str = GOLD,
    body_fill: str = GRAY,
    body_weight: str = "400",
) -> Tuple[List[str], float]:
    parts: List[str] = []
    h_size = heading_size or ctx.font(12, 9)
    b_size = body_size or ctx.font(17, 11)
    padding = ctx.u(26)
    text_w = width - padding * 2
    groups = _measure_item_lines(ctx, [item.text for item in section.items], text_w, b_size, per_item_lines, body_weight)
    body_h = _item_block_height(ctx, groups, b_size, ctx.u(16))
    card_h = ctx.u(54) + body_h + ctx.u(22)
    parts.append(_rect(x, y, width, card_h, fill=fill, stroke=stroke, radius=ctx.u(8), stroke_width=1.2))
    hx = x + padding
    markup, _ = _text(
        [_heading(section.heading)],
        hx,
        y + ctx.u(32),
        h_size,
        h_size,
        "800",
        heading_fill,
        letter_spacing=1.2,
    )
    parts.append(markup)
    bottom = _items_down(parts, hx, y + ctx.u(54), groups, b_size, body_fill, body_weight, ctx.u(16))
    parts.append(_line(hx, y + card_h - ctx.u(18), hx + ctx.u(44), y + card_h - ctx.u(18), GOLD, 2.4))
    return parts, y + card_h


# ---------------------------------------------------------------------------
# Layout family A - landmark editorial cover
# ---------------------------------------------------------------------------

def _landmark_cover(ctx: _Ctx) -> Tuple[List[str], float]:
    parts, cursor = _brand_header(ctx, FAMILY_LABELS["landmark_cover"])
    cursor += ctx.u(18)

    spot_w = ctx.u(230) if ctx.artwork else 0
    head_w = INNER_W - (spot_w + ctx.u(34) if spot_w else ctx.u(230))
    hl_parts, cursor = _headline(ctx, cursor, max(260, head_w))
    parts.extend(hl_parts)
    if ctx.artwork:
        art, _ = _spot_artwork(ctx, DESIGN_WIDTH - PAD - spot_w, cursor - ctx.u(170), spot_w)
        parts.append(art)
    else:
        glyph_scale = (ctx.u(205) / 90.0)
        parts.append(
            f'<g transform="translate({DESIGN_WIDTH - PAD - ctx.u(205)}, {cursor - ctx.u(185)}) '
            f'scale({glyph_scale:.3f})" opacity="0.14">'
            f'{render_header_icon("scales", GOLD, GRAY)}</g>\n'
        )

    parts.append(_rect(PAD, cursor - ctx.u(8), ctx.u(150), ctx.u(7), GOLD, None, 3))
    cursor += ctx.u(28)
    deck_parts, cursor = _deck_and_meta(ctx, cursor - ctx.u(28), max(260, head_w))
    parts.extend(deck_parts)
    cursor += ctx.u(26)

    holding = _outcome_section(ctx) or (_sections_by_priority(ctx)[0] if ctx.sections else None)
    if holding:
        quote_size = ctx.font(22, 15)
        quote_width = INNER_W - ctx.u(96)
        lines = _wrap(holding.items[0].text, quote_width, quote_size, 5, "400")
        lh = round(quote_size * 1.34)
        card_h = ctx.u(78) + len(lines) * lh + ctx.u(32)
        parts.append(_rect(PAD, cursor, INNER_W, card_h, "#FFFCF4", "#E9DDBE", ctx.u(8), 1.2))
        parts.append(_rect(PAD, cursor, ctx.u(12), card_h, GOLD, None, 0))
        markup, _ = _text(
            [_heading(holding.heading)],
            PAD + ctx.u(42),
            cursor + ctx.u(34),
            ctx.font(13, 10),
            ctx.font(13, 10),
            "800",
            GOLD,
            letter_spacing=1.5,
        )
        parts.append(markup)
        quote_markup, _ = _text(lines, PAD + ctx.u(42), cursor + ctx.u(76), lh, quote_size, "400", INK)
        parts.append(quote_markup)
        cursor += card_h + ctx.u(24)

    support_pool = [s for s in _sections_by_priority(ctx) if holding is None or s is not holding]
    if holding is not None and len(holding.items) > 1:
        support_pool = [replace(holding, items=holding.items[1:])] + support_pool

    support = support_pool
    if support:
        support_size = ctx.font(15, 12)
        gap = ctx.u(18)
        count = len(support)
        
        if count <= 3:
            card_w = (INNER_W - gap * (count - 1)) // count
            groups_by_section = [
                _measure_item_lines(
                    ctx, [item.text for item in section.items], card_w - ctx.u(48), support_size, 6
                )
                for section in support
            ]
            rem_h = ctx.avail - cursor
            min_card_h = max(
                ctx.u(82) + _item_block_height(ctx, groups, support_size, ctx.u(15))
                for groups in groups_by_section
            )
            card_h = max(min_card_h, min(int(rem_h * 0.90), min_card_h + ctx.u(60)))
            for index, section in enumerate(support):
                x = PAD + index * (card_w + gap)
                parts.append(_rect(x, cursor, card_w, card_h, WHITE, BORDER, ctx.u(8), 1.2))
                heading_markup, _ = _text(
                    [_heading(section.heading)],
                    x + ctx.u(24),
                    cursor + ctx.u(32),
                    ctx.font(12, 10),
                    ctx.font(12, 10),
                    "800",
                    GOLD,
                    letter_spacing=1.1,
                )
                parts.append(heading_markup)
                _items_down(
                    parts, x + ctx.u(24), cursor + ctx.u(58), groups_by_section[index], support_size, GRAY, "400", ctx.u(15)
                )
            cursor += card_h
        else:
            # 4 or more sections: render in 2-column grid
            columns = 2
            card_w = (INNER_W - gap) // 2
            row_cursor = cursor
            for i in range(0, count, 2):
                pair = support[i:i+2]
                row_groups = [
                    _measure_item_lines(
                        ctx, [item.text for item in sec.items], card_w - ctx.u(44), support_size, 5
                    )
                    for sec in pair
                ]
                row_h = max(
                    ctx.u(80) + _item_block_height(ctx, grps, support_size, ctx.u(14))
                    for grps in row_groups
                )
                for j, sec in enumerate(pair):
                    x = PAD + j * (card_w + gap)
                    parts.append(_rect(x, row_cursor, card_w, row_h, WHITE, BORDER, ctx.u(8), 1.2))
                    heading_markup, _ = _text(
                        [_heading(sec.heading)],
                        x + ctx.u(22),
                        row_cursor + ctx.u(30),
                        ctx.font(12, 10),
                        ctx.font(12, 10),
                        "800",
                        GOLD,
                        letter_spacing=1.1,
                    )
                    parts.append(heading_markup)
                    _items_down(
                        parts, x + ctx.u(22), row_cursor + ctx.u(54), row_groups[j], support_size, GRAY, "400", ctx.u(14)
                    )
                row_cursor += row_h + ctx.u(16)
            cursor = row_cursor

    return parts, cursor


# ---------------------------------------------------------------------------
# Layout family B - split-panel comparison
# ---------------------------------------------------------------------------

def _split_comparison(ctx: _Ctx) -> Tuple[List[str], float]:
    parts, cursor = _brand_header(ctx, FAMILY_LABELS["split_comparison"])
    cursor += ctx.u(8)
    hl_parts, cursor = _headline_with_spot(ctx, cursor, max(460, int(INNER_W * 0.8)))
    parts.extend(hl_parts)
    parts.append(_rect(PAD, cursor - ctx.u(10), ctx.u(132), ctx.u(7), GOLD, None, 3))
    cursor += ctx.u(24)

    sections = _sections_by_priority(ctx)
    if len(sections) < 2:
        items = [item for section in sections for item in section.items]
        half = max(1, (len(items) + 1) // 2)
        sections = [
            ResolvedSection("CHALLENGED POSITION", "comparison", "primary", items[:half]),
            ResolvedSection("JUDICIAL RULING", "comparison", "primary", items[half:half + 3]),
        ]

    left_section, right_section = sections[0], sections[1]
    extra_sections = sections[2:]
    col_gap = ctx.u(24)
    split = (INNER_W - col_gap) // 2
    left_x = PAD
    right_x = PAD + split + col_gap
    left_w = split
    right_w = split
    left_pad = ctx.u(28)
    text_size = ctx.font(17, 13)
    line_gap = ctx.u(16)

    left_groups = _measure_item_lines(ctx, [i.text for i in left_section.items], left_w - left_pad * 2, text_size, BODY_LINE_BUDGET)
    right_groups = _measure_item_lines(ctx, [i.text for i in right_section.items], right_w - left_pad * 2, text_size, BODY_LINE_BUDGET)
    left_body_h = _item_block_height(ctx, left_groups, text_size, line_gap)
    right_body_h = _item_block_height(ctx, right_groups, text_size, line_gap)
    min_panel_h = ctx.u(82) + max(left_body_h, right_body_h) + ctx.u(28)

    rem_avail = ctx.avail - cursor
    if extra_sections:
        # Balance height between comparison panels and extra section cards
        panel_h = max(min_panel_h, min(int(rem_avail * 0.50), min_panel_h + ctx.u(80)))
    else:
        panel_h = max(min_panel_h, int(rem_avail * 0.88))

    parts.append(_rect(left_x, cursor, left_w, panel_h, PANEL_INK, None, ctx.u(10)))
    parts.append(_rect(right_x, cursor, right_w, panel_h, "#FFFDF7", "#E6D9B7", ctx.u(10)))
    parts.append(_line(left_x + left_w + col_gap / 2, cursor + ctx.u(16), left_x + left_w + col_gap / 2, cursor + panel_h - ctx.u(16), GOLD, ctx.u(3, 2)))

    markup, _ = _text(
        [_heading(left_section.heading)],
        left_x + left_pad,
        cursor + ctx.u(42),
        ctx.font(13, 10),
        ctx.font(13, 10),
        "800",
        GOLD,
        letter_spacing=1.5,
    )
    parts.append(markup)
    _items_down(parts, left_x + left_pad, cursor + ctx.u(78), left_groups, text_size, PANEL_TEXT, "400", line_gap)

    markup, _ = _text(
        [_heading(right_section.heading)],
        right_x + left_pad,
        cursor + ctx.u(42),
        ctx.font(13, 10),
        ctx.font(13, 10),
        "800",
        INK,
        letter_spacing=1.5,
    )
    parts.append(markup)
    _items_down(parts, right_x + left_pad, cursor + ctx.u(78), right_groups, text_size, INK, "400", line_gap)

    cursor += panel_h + ctx.u(24)

    # Render ALL extra sections so no information is dropped and space is filled
    if extra_sections:
        if len(extra_sections) == 1:
            sec = extra_sections[0]
            block, cursor = _section_card(
                ctx,
                sec,
                PAD,
                cursor,
                INNER_W,
                per_item_lines=BODY_LINE_BUDGET,
                body_size=ctx.font(16, 12),
                fill=SOFT,
                stroke=GOLD,
                heading_fill=INK,
            )
            parts.extend(block)
            cursor += ctx.u(16)
        elif len(extra_sections) == 2:
            sub_gap = ctx.u(20)
            sub_w = (INNER_W - sub_gap) // 2
            card_max_h = 0
            sub_blocks = []
            for i, sec in enumerate(extra_sections):
                cx = PAD + i * (sub_w + sub_gap)
                bg = SOFT if i == 0 else WHITE
                stk = GOLD if i == 0 else BORDER
                blk, end_y = _section_card(
                    ctx,
                    sec,
                    cx,
                    cursor,
                    sub_w,
                    per_item_lines=BODY_LINE_BUDGET,
                    body_size=ctx.font(15, 11),
                    fill=bg,
                    stroke=stk,
                    heading_fill=INK,
                )
                sub_blocks.append(blk)
                card_max_h = max(card_max_h, end_y - cursor)
            for blk in sub_blocks:
                parts.extend(blk)
            cursor += card_max_h + ctx.u(16)
        else:
            sub_gap = ctx.u(18)
            sub_w = (INNER_W - sub_gap) // 2
            row_cursor = cursor
            for i in range(0, len(extra_sections), 2):
                pair = extra_sections[i:i+2]
                row_h = 0
                for j, sec in enumerate(pair):
                    cx = PAD + j * (sub_w + sub_gap)
                    blk, end_y = _section_card(
                        ctx,
                        sec,
                        cx,
                        row_cursor,
                        sub_w,
                        per_item_lines=7,
                        body_size=ctx.font(14, 11),
                        fill=SOFT if (i + j) % 2 == 0 else WHITE,
                        stroke=GOLD if (i + j) % 2 == 0 else BORDER,
                        heading_fill=INK,
                    )
                    parts.extend(blk)
                    row_h = max(row_h, end_y - row_cursor)
                row_cursor += row_h + ctx.u(16)
            cursor = row_cursor

    return parts, cursor


# ---------------------------------------------------------------------------
# Layout family C - timeline
# ---------------------------------------------------------------------------

def _timeline(ctx: _Ctx) -> Tuple[List[str], float]:
    parts, cursor = _brand_header(ctx, FAMILY_LABELS["timeline"])
    cursor += ctx.u(8)
    hl_parts, cursor = _headline_with_spot(ctx, cursor, max(420, int(INNER_W * 0.72)))
    parts.extend(hl_parts)
    deck_parts, cursor = _deck_and_meta(ctx, cursor, max(360, int(INNER_W * 0.72)))
    parts.extend(deck_parts)

    # No oversized year watermark: the date already sits in the meta line and the footer,
    # and a giant ghost numeral competes with the legal copy instead of supporting it.

    sections = _deduped_items(ctx, _sections_by_priority(ctx), 6)
    node_x = PAD + ctx.u(46)
    content_x = node_x + ctx.u(64)
    text_w = DESIGN_WIDTH - PAD - content_x - ctx.u(12)
    node_r = ctx.u(22, 12)
    heading_size = ctx.font(16, 12)
    body_size = ctx.font(16, 12)
    step_heights: List[int] = []
    step_lines: List[Tuple[str, List[List[str]], str]] = []
    
    date_pattern = re.compile(r"\b((?:19|20)\d{2})\b")
    for index, section in enumerate(sections, 1):
        item_texts = [item.text for item in section.items]
        # Look for real verified year in section heading or items
        found_year = None
        for txt in [section.heading] + item_texts:
            m = date_pattern.search(txt)
            if m:
                found_year = m.group(1)
                break
        badge_label = found_year if found_year else f"{index:02}"
        groups = _measure_item_lines(ctx, item_texts, text_w, body_size, BODY_LINE_BUDGET)
        height = ctx.u(48) + _item_block_height(ctx, groups, body_size, ctx.u(14)) + ctx.u(18)
        step_heights.append(height)
        step_lines.append((section.heading, groups, badge_label))

    rem_avail = ctx.avail - cursor - ctx.u(34)
    natural_h = sum(step_heights)
    step_gap = ctx.u(16)
    if len(step_lines) > 1 and natural_h < rem_avail * 0.82:
        step_gap = min(ctx.u(36), int((rem_avail * 0.85 - natural_h) / (len(step_lines) - 1)))

    spine_top = cursor + ctx.u(24)
    total_h = sum(step_heights) + step_gap * max(0, len(step_heights) - 1)
    parts.append(_line(node_x, spine_top, node_x, spine_top + max(0, total_h - ctx.u(20)), GOLD, ctx.u(3, 2)))

    y = cursor + ctx.u(30)
    for index, (heading, groups, badge_label) in enumerate(step_lines, 1):
        height = step_heights[index - 1]
        circle_y = y + ctx.u(18)
        parts.append(_circle(node_x, circle_y, node_r, WHITE, GOLD, ctx.u(3, 2)))
        badge_font = ctx.font(10, 8) if len(badge_label) > 2 else ctx.font(12, 10)
        markup, _ = _text(
            [badge_label],
            node_x,
            circle_y + node_r * 0.32,
            node_r,
            badge_font,
            "800",
            GOLD,
            anchor="middle",
        )
        parts.append(markup)
        heading_markup, _ = _text(
            [_heading(heading)],
            content_x,
            circle_y,
            round(heading_size * 1.32),
            heading_size,
            "800",
            INK,
            letter_spacing=1.0,
        )
        parts.append(heading_markup)
        _items_down(parts, content_x, circle_y + ctx.u(42), groups, body_size, GRAY, "400", ctx.u(14))
        parts.append(_line(content_x, y + height - ctx.u(14), content_x + ctx.u(90), y + height - ctx.u(14), "#E5DDCB", 1.4))
        y += height + step_gap

    return parts, y


# ---------------------------------------------------------------------------
# Layout family D - decision tree / legal test
# ---------------------------------------------------------------------------

def _decision_tree(ctx: _Ctx) -> Tuple[List[str], float]:
    parts, cursor = _brand_header(ctx, FAMILY_LABELS["decision_tree"])
    cursor += ctx.u(8)
    hl_parts, cursor = _headline_with_spot(ctx, cursor, max(420, int(INNER_W * 0.8)))
    parts.extend(hl_parts)

    sections = _sections_by_priority(ctx)
    outcome = _outcome_section(ctx)
    # A legal test opens on the question, not on the answer it is about to prove. Check
    # each kind in turn: passing them as one tuple would let an earlier primary section
    # of another kind win the root and push the issues off the poster.
    root = (
        _section_by_kinds(ctx, "issues")
        or _section_by_kinds(ctx, "context")
        or _section_by_kinds(ctx, "facts")
        or _section_by_kinds(ctx, "process")
        or next((section for section in sections if section is not outcome), None)
    )
    branch_sections = [s for s in sections if s is not root and s is not outcome]
    branch_items: List[str] = []
    if root is not None:
        for item in root.items[1:]:
            # The root card above already names this section, so its branches do not need
            # to repeat the heading; only the other sections are labelled inside the cards.
            branch_items.append(item.text)
    for section in branch_sections:
        for item in section.items:
            if len(branch_items) >= 4:
                break
            branch_items.append(f"{section.heading.upper()}: {item.text}")
        if len(branch_items) >= 4:
            break

    body_size = ctx.font(16, 11)
    root_w = round(INNER_W * 0.72)
    root_x = PAD + (INNER_W - root_w) // 2
    root_lines = _wrap((root.items[0].text if root else ctx.brief.headline), root_w - ctx.u(76), body_size, 4, "500")
    root_h = ctx.u(94) + len(root_lines) * round(body_size * 1.38)
    parts.append(_rect(root_x, cursor, root_w, root_h, SOFT, GOLD, ctx.u(8), 1.8))
    heading_size = ctx.font(12, 9)
    markup, _ = _text(
        [_heading(root.heading if root else "THE QUESTION")],
        root_x + ctx.u(26),
        cursor + ctx.u(32),
        heading_size,
        heading_size,
        "800",
        INK,
        letter_spacing=1.5,
    )
    parts.append(markup)
    _items_down(parts, root_x + ctx.u(26), cursor + ctx.u(64), [root_lines], body_size, INK, "500", 0)
    root_bottom = cursor + root_h
    parts.append(_line(DESIGN_WIDTH / 2, root_bottom, DESIGN_WIDTH / 2, root_bottom + ctx.u(28), GOLD, ctx.u(2.5)))

    if branch_items:
        branch_count = len(branch_items)
        branch_gap = ctx.u(16)
        columns = 1 if branch_count == 1 else 2
        branch_w = (INNER_W - branch_gap * (columns - 1)) // columns
        branch_y = root_bottom + ctx.u(52)
        branch_heights = []
        branch_groups = []
        for text in branch_items:
            lines = _wrap(text, branch_w - ctx.u(52), body_size, BODY_LINE_BUDGET, "400")
            branch_groups.append(lines)
            branch_heights.append(ctx.u(54) + len(lines) * round(body_size * 1.38) + ctx.u(18))

        rows = [branch_groups[index : index + columns] for index in range(0, branch_count, columns)]
        row_heights: List[int] = []
        offsets = []
        cursor_y = branch_y
        for row_index, row in enumerate(rows):
            heights = branch_heights[row_index * columns : row_index * columns + len(row)]
            row_h = max(heights)
            row_heights.append(row_h)
            offsets.append(cursor_y)
            cursor_y += row_h + branch_gap
        branch_bottom = cursor_y - branch_gap

        connector_y = root_bottom + ctx.u(28)
        last_column_center = PAD + (columns - 1) * (branch_w + branch_gap) + branch_w / 2
        parts.append(
            _line(
                PAD + branch_w / 2,
                connector_y,
                last_column_center,
                connector_y,
                GOLD,
                ctx.u(2.2),
            )
        )
        for row_index, row in enumerate(rows):
            row_y = offsets[row_index]
            for column, lines in enumerate(row):
                bx = PAD + column * (branch_w + branch_gap)
                cx = bx + branch_w / 2
                if row_index == 0:
                    parts.append(_line(cx, connector_y, cx, row_y, GOLD, ctx.u(2)))
                else:
                    parts.append(_line(cx, offsets[row_index - 1] + row_heights[row_index - 1], cx, row_y, GOLD, ctx.u(2)))
                parts.append(_rect(bx, row_y, branch_w, row_heights[row_index], WHITE, BORDER, ctx.u(8), 1.2))
                parts.append(_circle(cx, row_y + ctx.u(16), ctx.u(8, 5), GOLD, None))
                _items_down(parts, bx + ctx.u(26), row_y + ctx.u(48), [lines], body_size, GRAY, "400", 0)
    else:
        branch_bottom = root_bottom + ctx.u(48)

    if outcome:
        parts.append(_line(DESIGN_WIDTH / 2, branch_bottom, DESIGN_WIDTH / 2, branch_bottom + ctx.u(34), GOLD, ctx.u(2.5)))
        out_y = branch_bottom + ctx.u(50)
        out_size = ctx.font(20, 13)
        outcome_lines = _wrap(outcome.items[0].text, INNER_W - ctx.u(72), out_size, 5, "600")
        out_h = ctx.u(96) + len(outcome_lines) * round(out_size * 1.34)
        parts.append(_rect(PAD, out_y, INNER_W, out_h, PANEL_INK, None, ctx.u(8)))
        parts.append(_rect(PAD + INNER_W - ctx.u(12), out_y, ctx.u(12), out_h, GOLD, None, 0))
        markup, _ = _text(
            [_heading(outcome.heading)],
            PAD + ctx.u(34),
            out_y + ctx.u(36),
            heading_size,
            heading_size,
            "800",
            GOLD,
            letter_spacing=1.5,
        )
        parts.append(markup)
        _items_down(parts, PAD + ctx.u(34), out_y + ctx.u(74), [outcome_lines], out_size, PANEL_TEXT, "600", 0)
        return parts, out_y + out_h

    return parts, branch_bottom + ctx.u(32)


# ---------------------------------------------------------------------------
# Layout family E - statutory map
# ---------------------------------------------------------------------------

def _statutory_map(ctx: _Ctx) -> Tuple[List[str], float]:
    parts, cursor = _brand_header(ctx, FAMILY_LABELS["statutory_map"])
    cursor += ctx.u(8)
    hl_parts, cursor = _headline_with_spot(ctx, cursor, max(420, int(INNER_W * 0.78)))
    parts.extend(hl_parts)

    sections = _deduped_items(ctx, _sections_by_priority(ctx), 6)
    # Short canvases keep four mapped provisions at a readable size rather than six in
    # fine print; the hub still anchors the map to the operative provision.
    max_satellites = 4 if ctx.avail < 760 else 6
    flat = [(section, item) for section in sections for item in section.items][:max_satellites]
    if not flat:
        raise ValueError("statutory_map layout needs at least one resolved provision")

    map_top = cursor + ctx.u(28)
    row_gap = ctx.u(22)
    col_gap = ctx.u(16)
    hub_w = ctx.u(300, 150)
    hub_size = ctx.font(15, 10)
    hub_label_size = ctx.font(11, 8)
    hub_text = (ctx.record.relevant_statutes[0] if ctx.record.relevant_statutes else ctx.brief.headline)
    # A diamond narrows away from its centre, so the hub copy is set to the middle band
    # and vertically centred as one block instead of hanging off the top vertex.
    hub_text_w = hub_w - ctx.u(130)
    hub_lines = _wrap(hub_text, hub_text_w, hub_size, 5, "500")
    hub_block = hub_label_size + ctx.u(26) + len(hub_lines) * round(hub_size * 1.34)
    hub_h = max(ctx.u(210, 120), int(hub_block * 2.1))
    sat_w = int((INNER_W - hub_w - col_gap * 2) / 2)
    left_x = PAD
    right_x = DESIGN_WIDTH - PAD - sat_w
    hub_cx = DESIGN_WIDTH / 2
    body_size = ctx.font(14, 10)
    heading_size = ctx.font(11, 8)
    line_h = round(body_size * 1.38)

    # Satellite cards grow with the provision text instead of cutting it off.
    sat_groups = [_wrap(item.text, sat_w - ctx.u(44), body_size, BODY_LINE_BUDGET, "400") for _, item in flat]
    rows = [sat_groups[index : index + 2] for index in range(0, len(sat_groups), 2)]
    row_heights = [
        max(ctx.u(150, 84), ctx.u(64) + max(len(group) for group in row) * line_h + ctx.u(24))
        for row in rows
    ]
    row_offsets = []
    row_y = map_top
    for height in row_heights:
        row_offsets.append(row_y)
        row_y += height + row_gap
    map_bottom = row_y - row_gap
    hub_cy = map_top + (map_bottom - map_top) / 2
    hub_x = hub_cx - hub_w / 2
    hub_y = hub_cy - hub_h / 2
    positions = [
        (left_x if index % 2 == 0 else right_x, row_offsets[index // 2])
        for index in range(len(flat))
    ]

    for index, ((sx, sy), (section, item), lines) in enumerate(
        zip(positions, flat, sat_groups)
    ):
        connector_x = sx + sat_w / 2
        connector_y = sy + row_heights[index // 2] / 2
        parts.append(_line(hub_cx, hub_cy, connector_x, connector_y, GOLD, ctx.u(2), dash="5 7", opacity=0.58))
        parts.append(_rect(sx, sy, sat_w, row_heights[index // 2], WHITE, BORDER, ctx.u(8), 1.2))
        parts.append(_circle(sx + ctx.u(24), sy + ctx.u(28), ctx.u(7, 4), GOLD, None))
        markup, _ = _text(
            [_heading(section.heading)],
            sx + ctx.u(40),
            sy + ctx.u(32),
            heading_size,
            heading_size,
            "800",
            GOLD,
            letter_spacing=1.1,
        )
        parts.append(markup)
        _items_down(parts, sx + ctx.u(22), sy + ctx.u(64), [lines], body_size, GRAY, "400", 0)

    parts.append(
        _polygon(
            [
                (hub_cx, hub_y),
                (hub_x + hub_w, hub_cy),
                (hub_cx, hub_y + hub_h),
                (hub_x, hub_cy),
            ],
            PANEL_INK,
            GOLD,
            ctx.u(3),
        )
    )
    hub_title = "ANCHOR PROVISION" if ctx.record.relevant_statutes else _heading(
        sections[0].heading if sections else "LEGAL FRAMEWORK"
    )
    markup, _ = _text(
        [hub_title],
        hub_cx,
        hub_cy - hub_block / 2 + hub_label_size,
        hub_label_size,
        hub_label_size,
        "800",
        GOLD,
        anchor="middle",
        letter_spacing=1.3,
    )
    parts.append(markup)
    _items_down(
        parts,
        hub_cx,
        hub_cy - hub_block / 2 + hub_label_size + ctx.u(26),
        [hub_lines],
        hub_size,
        PANEL_TEXT,
        "500",
        0,
        anchor="middle",
    )

    bottom_y = max(map_bottom, hub_y + hub_h)
    outcome = _outcome_section(ctx)
    if outcome and (ctx.avail - bottom_y) > 110:
        block, bottom_y = _section_card(
            ctx,
            outcome,
            PAD,
            bottom_y + ctx.u(18),
            INNER_W,
            per_item_lines=5,
            body_size=ctx.font(15, 12),
            fill=SOFT,
            stroke=GOLD,
            heading_fill=INK,
        )
        parts.extend(block)

    return parts, bottom_y


# ---------------------------------------------------------------------------
# Layout family F - chart-led
# ---------------------------------------------------------------------------

def _chart_panel(
    ctx: _Ctx, y: float, x: float, width: int
) -> Tuple[List[str], float]:
    """Draw the record-verbatim bar chart inside a panel of the given width."""
    chart = ctx.brief.chart
    if chart is None:
        raise ValueError("chart_led layout requested without chart data")
    parts: List[str] = []
    rows = len(chart.data)
    panel_h = ctx.u(96) + rows * ctx.u(92) + ctx.u(46)
    parts.append(_rect(x, y, width, panel_h, WHITE, "#E8E0CF", ctx.u(10), 1.4))
    parts.append(_rect(x, y, width, ctx.u(60), PANEL_INK, None, ctx.u(10)))
    parts.append(_rect(x, y + ctx.u(48), width, ctx.u(12), PANEL_INK, None, 0))
    markup, _ = _text(
        [_wrap(chart.title.upper(), width - ctx.u(56), ctx.font(14, 10), 1, "800")[0]],
        x + ctx.u(28),
        y + ctx.u(38),
        ctx.font(14, 10),
        ctx.font(14, 10),
        "800",
        GOLD,
        letter_spacing=1.5,
    )
    parts.append(markup)

    label_w = ctx.u(215, 96) if width > INNER_W * 0.7 else ctx.u(120, 70)
    axis_x = x + ctx.u(34) + label_w
    bar_end = x + width - ctx.u(112)
    max_value = max(item[2] for item in chart.data)
    scale_w = max(60, bar_end - axis_x)
    axis_top = y + ctx.u(104)
    axis_bottom = y + panel_h - ctx.u(34)
    parts.append(_line(axis_x, axis_top - ctx.u(26), axis_x, axis_bottom, INK, ctx.u(2)))
    tick_size = ctx.font(10, 8)
    for tick in range(0, 4):
        tick_x = axis_x + (scale_w * tick / 3)
        parts.append(_line(tick_x, axis_top - ctx.u(18), tick_x, axis_bottom, "#DAD8DE", 1, dash="3 6", opacity=0.55))
        if tick not in (0, 3):
            continue
        tick_markup, _ = _text(
            [f"{round(max_value * tick / 3)}{(' ' + chart.unit) if chart.unit else ''}"],
            tick_x,
            axis_top - ctx.u(34),
            tick_size,
            tick_size,
            "500",
            MUTED,
            anchor="start" if tick == 0 else "end",
        )
        parts.append(tick_markup)

    bar_size = ctx.font(15, 10)
    row_pitch = max(ctx.u(56), int((axis_bottom - axis_top) / rows))
    bar_h = min(ctx.u(38), int(row_pitch * 0.52))
    for index, (label, value_text, value) in enumerate(chart.data):
        row_y = axis_top + index * row_pitch
        parts.append(_line(x + ctx.u(24), row_y + ctx.u(20), axis_x - ctx.u(14), row_y + ctx.u(20), "#E5E1D8", 1))
        label_lines = _wrap(label, label_w, ctx.font(13, 10), 2, "600")
        label_markup, _ = _text(
            label_lines, x + ctx.u(24), row_y + ctx.u(16), ctx.font(18, 12), ctx.font(13, 10), "600", INK
        )
        parts.append(label_markup)
        bar_w = max(ctx.u(20), round(scale_w * (value / max_value)))
        fill = GOLD if index % 2 == 0 else PANEL_INK
        parts.append(_rect(axis_x, row_y, bar_w, bar_h, fill, None, ctx.u(6)))
        value_markup, _ = _text(
            [value_text],
            axis_x + bar_w + ctx.u(14),
            row_y + round(bar_h * 0.72),
            bar_size,
            bar_size,
            "800",
            INK,
        )
        parts.append(value_markup)
    return parts, y + panel_h


def _chart_led(ctx: _Ctx) -> Tuple[List[str], float]:
    parts, cursor = _brand_header(ctx, FAMILY_LABELS["chart_led"])
    cursor += ctx.u(8)
    hl_parts, cursor = _headline_with_spot(ctx, cursor, max(420, int(INNER_W * 0.86)))
    parts.extend(hl_parts)

    sections = _sections_by_priority(ctx)[:2]
    body_size = ctx.font(15, 10)

    # Full-width chart with the supporting legal points underneath reads best on tall
    # canvases; short canvases (1200x675) place them beside the chart instead, so the
    # poster keeps its content without shrinking the type below the readable floor.
    stacked_parts, stacked_bottom = _chart_panel(ctx, cursor, PAD, INNER_W)
    positions: List[float] = []
    card_cursor = stacked_bottom + ctx.u(26)
    for section in sections:
        _, card_bottom = _section_card(
            ctx,
            section,
            PAD,
            card_cursor,
            INNER_W,
            per_item_lines=BODY_LINE_BUDGET,
            body_size=body_size,
            fill="#FFFDF6" if section.emphasis == "primary" else WHITE,
            stroke=GOLD if section.emphasis == "primary" else BORDER,
        )
        positions.append(card_cursor)
        card_cursor = card_bottom + ctx.u(16)
    if card_cursor <= ctx.avail:
        parts.extend(stacked_parts)
        for section, card_y in zip(sections, positions):
            block, _ = _section_card(
                ctx,
                section,
                PAD,
                card_y,
                INNER_W,
                per_item_lines=BODY_LINE_BUDGET,
                body_size=body_size,
                fill="#FFFDF6" if section.emphasis == "primary" else WHITE,
                stroke=GOLD if section.emphasis == "primary" else BORDER,
            )
            parts.extend(block)
        return parts, card_cursor

    panel_w = round(INNER_W * 0.6)
    side_gap = ctx.u(24)
    side_x = PAD + panel_w + side_gap
    side_w = INNER_W - panel_w - side_gap
    panel_parts, panel_bottom = _chart_panel(ctx, cursor, PAD, panel_w)
    parts.extend(panel_parts)

    y = cursor
    for section in sections:
        block, y = _section_card(
            ctx,
            section,
            side_x,
            y,
            side_w,
            per_item_lines=6,
            body_size=ctx.font(14, 10),
            heading_size=ctx.font(11, 9),
            fill="#FFFDF6" if section.emphasis == "primary" else WHITE,
            stroke=GOLD if section.emphasis == "primary" else BORDER,
        )
        parts.extend(block)
        y += ctx.u(18)
    return parts, max(panel_bottom, y)


# ---------------------------------------------------------------------------
# Layout family G - process flow
# ---------------------------------------------------------------------------

def _chevron(
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str,
    stroke: Optional[str],
    point: int,
) -> str:
    points = [
        (x, y),
        (x + width - point, y),
        (x + width, y + height / 2),
        (x + width - point, y + height),
        (x, y + height),
    ]
    return _polygon(points, fill, stroke, 1.2)


def _process_flow(ctx: _Ctx) -> Tuple[List[str], float]:
    parts, cursor = _brand_header(ctx, FAMILY_LABELS["process_flow"])
    cursor += ctx.u(8)
    hl_parts, cursor = _headline_with_spot(ctx, cursor, max(420, int(INNER_W * 0.84)))
    parts.extend(hl_parts)

    sections = _deduped_items(ctx, _sections_by_priority(ctx), 6)
    horizontal = ctx.brief.flow_direction == "horizontal"
    outcome = _outcome_section(ctx)
    step_items: List[Tuple[str, str]] = []
    for section in sections:
        for item in section.items:
            step_items.append((section.heading, item.text))
    if len(step_items) > 5:
        step_items = step_items[:5]
    if not step_items:
        raise ValueError("process_flow layout needs at least one resolved step")

    body_size = ctx.font(15, 10)
    heading_size = ctx.font(12, 9)
    per_item_lines = BODY_LINE_BUDGET
    gap = ctx.u(14)
    step_w = (INNER_W - gap * (len(step_items) - 1)) // len(step_items)
    row_groups = [_wrap(text, step_w - ctx.u(52), body_size, per_item_lines, "400") for _, text in step_items]
    # Card headings are legal section names, often too long for a third of the poster;
    # they get up to two lines instead of running past the chevron edge.
    head_groups = [
        _wrap(_heading(heading), step_w - ctx.u(52), heading_size, 2, "800", uppercase=True)
        for heading, _ in step_items
    ]
    head_extra = max(0, max((len(lines) for lines in head_groups), default=1) - 1) * round(heading_size * 1.3)
    # A row of chevrons is the signature of this family, but three columns at poster
    # scale leave ~15 characters per line, which would cut legal sentences short.
    # When that happens the same steps run as a full-width chevron stack instead.
    use_row = (
        horizontal
        and len(step_items) <= 3
        and not any(_truncated(lines) for lines in row_groups)
        and not any(_truncated(lines) for lines in head_groups)
    )
    if use_row:
        card_h = ctx.u(166) + head_extra + max(len(lines) for lines in row_groups) * round(body_size * 1.38)
        point = ctx.u(28)
        for index, (heading, _) in enumerate(step_items):
            x = PAD + index * (step_w + gap)
            fill = GOLD if index == len(step_items) - 1 else (WHITE if index % 2 == 0 else SOFT)
            stroke = None if fill == GOLD else BORDER
            parts.append(_chevron(x, cursor, step_w, card_h, fill, stroke, point))
            num_markup, _ = _text(
                [f"STEP {index + 1:02}"],
                x + ctx.u(22),
                cursor + ctx.u(34),
                heading_size,
                heading_size,
                "800",
                INK if fill == GOLD else GOLD,
                letter_spacing=1.3,
            )
            parts.append(num_markup)
            head_markup, _ = _text(
                head_groups[index],
                x + ctx.u(22),
                cursor + ctx.u(70),
                round(heading_size * 1.3),
                heading_size,
                "800",
                INK if fill == GOLD else INK,
                letter_spacing=0.8,
            )
            parts.append(head_markup)
            _items_down(
                parts,
                x + ctx.u(22),
                cursor + ctx.u(104) + head_extra,
                [row_groups[index]],
                body_size,
                INK if fill == GOLD else GRAY,
                "400",
                0,
            )
        cursor += card_h + ctx.u(24)
    else:
        for index, (heading, text) in enumerate(step_items):
            step_h = ctx.u(86)
            lines = _wrap(text, INNER_W - ctx.u(190), body_size, BODY_LINE_BUDGET, "400")
            actual_h = step_h + len(lines) * round(body_size * 1.38)
            fill = GOLD if index == len(step_items) - 1 else (PANEL_INK if index % 2 else WHITE)
            stroke = None if fill in {GOLD, PANEL_INK} else BORDER
            parts.append(_chevron(PAD, cursor, INNER_W, actual_h, fill, stroke, ctx.u(32)))
            circle_x = PAD + ctx.u(44)
            circle_y = cursor + actual_h / 2
            marker_fill = INK if fill == GOLD else GOLD
            parts.append(_circle(circle_x, circle_y, ctx.u(22, 10), WHITE, GOLD, ctx.u(2)))
            num_markup, _ = _text(
                [f"{index + 1:02}"],
                circle_x,
                circle_y + ctx.u(7, 4),
                ctx.u(20, 10),
                max(9, ctx.font(13)),
                "800",
                INK,
                anchor="middle",
            )
            parts.append(num_markup)
            text_x = PAD + ctx.u(92)
            color = INK if fill != PANEL_INK else PANEL_TEXT
            head_markup, _ = _text(
                [_heading(heading)],
                text_x,
                cursor + ctx.u(34),
                heading_size,
                heading_size,
                "800",
                GOLD if fill != GOLD else INK,
                letter_spacing=1.2,
            )
            parts.append(head_markup)
            _items_down(parts, text_x, cursor + ctx.u(64), [lines], body_size, color, "400", 0)
            cursor += actual_h + ctx.u(10)

    if outcome and not any(item.text == outcome.items[0].text for _, item in [(s, i) for s in sections for i in s.items]):
        block, cursor = _section_card(
            ctx,
            outcome,
            PAD,
            cursor + ctx.u(8),
            INNER_W,
            per_item_lines=BODY_LINE_BUDGET,
            fill=SOFT,
            stroke=GOLD,
            heading_fill=INK,
            body_size=body_size,
        )
        parts.extend(block)

    return parts, cursor


# ---------------------------------------------------------------------------
# Layout family H - argument vs outcome
# ---------------------------------------------------------------------------

def _argument_outcome(ctx: _Ctx) -> Tuple[List[str], float]:
    parts, cursor = _brand_header(ctx, FAMILY_LABELS["argument_outcome"])
    cursor += ctx.u(8)
    hl_parts, cursor = _headline_with_spot(ctx, cursor, max(420, int(INNER_W * 0.78)))
    parts.extend(hl_parts)

    sections = _sections_by_priority(ctx)
    argument = _section_by_kinds(ctx, "argument", "issues", "facts", "reasoning") or (sections[0] if sections else None)
    outcome = _outcome_section(ctx) or (sections[-1] if len(sections) > 1 and sections[-1] is not argument else argument)

    body_size = ctx.font(17, 11)
    arg_items = [item.text for item in (argument.items[:3] if argument else [])]
    arg_groups = _measure_item_lines(ctx, arg_items, int(INNER_W * 0.82), body_size, BODY_LINE_BUDGET)
    arg_h = ctx.u(106) + _item_block_height(ctx, arg_groups, body_size, ctx.u(18))
    parts.append(_rect(PAD, cursor, INNER_W, arg_h, PANEL_INK, None, ctx.u(10)))
    parts.append(_polygon(
        [(PAD, cursor + arg_h), (PAD + ctx.u(230), cursor + arg_h), (PAD, cursor + arg_h + ctx.u(44))],
        GOLD,
    ))
    markup, _ = _text(
        [_heading(argument.heading if argument else "THE ARGUMENT")],
        PAD + ctx.u(34),
        cursor + ctx.u(40),
        ctx.font(12, 9),
        ctx.font(12, 9),
        "800",
        GOLD,
        letter_spacing=1.6,
    )
    parts.append(markup)
    _items_down(parts, PAD + ctx.u(34), cursor + ctx.u(82), arg_groups, body_size, PANEL_TEXT, "400", ctx.u(18))
    cursor += arg_h + ctx.u(54)

    if outcome and outcome is not argument:
        out_size = ctx.font(25, 15)
        out_lines = _wrap(outcome.items[0].text, INNER_W - ctx.u(120), out_size, 5, "600")
        out_h = ctx.u(130) + len(out_lines) * round(out_size * 1.3)
        parts.append(_rect(PAD, cursor, INNER_W, out_h, "#FFFDF5", GOLD, ctx.u(10), 1.8))
        markup, _ = _text(
            [_heading(outcome.heading)],
            PAD + ctx.u(44),
            cursor + ctx.u(42),
            ctx.font(12, 9),
            ctx.font(12, 9),
            "800",
            GOLD,
            letter_spacing=1.6,
        )
        parts.append(markup)
        parts.append(_line(PAD + ctx.u(44), cursor + ctx.u(70), PAD + INNER_W - ctx.u(44), cursor + ctx.u(70), "#EADDBD", 1.2))
        _items_down(parts, PAD + ctx.u(44), cursor + ctx.u(108), [out_lines], out_size, INK, "600", 0)
        cursor += out_h + ctx.u(22)

    support = [s for s in sections if s not in (argument, outcome)]
    if support:
        gap = ctx.u(18)
        count = len(support)
        support_size = ctx.font(15, 11)
        if count <= 2:
            card_w = (INNER_W - gap * (count - 1)) // count
            groups_by_section = [
                _measure_item_lines(
                    ctx, [item.text for item in section.items], card_w - ctx.u(48), support_size, BODY_LINE_BUDGET
                )
                for section in support
            ]
            rem_h = ctx.avail - cursor
            min_card_h = max(
                ctx.u(82) + _item_block_height(ctx, groups, support_size, ctx.u(14))
                for groups in groups_by_section
            )
            card_h = max(min_card_h, min(int(rem_h * 0.90), min_card_h + ctx.u(50)))
            for index, (section, groups) in enumerate(zip(support, groups_by_section)):
                x = PAD + index * (card_w + gap)
                parts.append(_rect(x, cursor, card_w, card_h, WHITE, BORDER, ctx.u(8), 1.2))
                heading_markup, _ = _text(
                    [_heading(section.heading)],
                    x + ctx.u(24),
                    cursor + ctx.u(30),
                    ctx.font(12, 10),
                    ctx.font(12, 10),
                    "800",
                    GOLD,
                    letter_spacing=1.1,
                )
                parts.append(heading_markup)
                _items_down(parts, x + ctx.u(24), cursor + ctx.u(56), groups, support_size, GRAY, "400", ctx.u(14))
            cursor += card_h
        else:
            card_w = (INNER_W - gap) // 2
            row_cursor = cursor
            for i in range(0, count, 2):
                pair = support[i:i+2]
                row_groups = [
                    _measure_item_lines(ctx, [item.text for item in sec.items], card_w - ctx.u(44), support_size, 6)
                    for sec in pair
                ]
                row_h = max(
                    ctx.u(80) + _item_block_height(ctx, grps, support_size, ctx.u(14))
                    for grps in row_groups
                )
                for j, sec in enumerate(pair):
                    x = PAD + j * (card_w + gap)
                    parts.append(_rect(x, row_cursor, card_w, row_h, WHITE, BORDER, ctx.u(8), 1.2))
                    heading_markup, _ = _text(
                        [_heading(sec.heading)],
                        x + ctx.u(22),
                        row_cursor + ctx.u(30),
                        ctx.font(12, 10),
                        ctx.font(12, 10),
                        "800",
                        GOLD,
                        letter_spacing=1.1,
                    )
                    parts.append(heading_markup)
                    _items_down(parts, x + ctx.u(22), row_cursor + ctx.u(54), row_groups[j], support_size, GRAY, "400", ctx.u(14))
            cursor = row_cursor

    return parts, cursor


# ---------------------------------------------------------------------------
# Hybrid - editorial split brief
# ---------------------------------------------------------------------------

def _hybrid(ctx: _Ctx) -> Tuple[List[str], float]:
    parts, cursor = _brand_header(ctx, FAMILY_LABELS["hybrid"])
    cursor += ctx.u(8)
    hl_parts, cursor = _headline_with_spot(ctx, cursor, max(420, int(INNER_W * 0.82)))
    parts.extend(hl_parts)

    secondary = ctx.brief.secondary_family.value if ctx.brief.secondary_family else "editorial"
    parts.append(_rect(PAD, cursor - ctx.u(12), ctx.u(144), ctx.u(6), GOLD, None, 3))
    markup, _ = _text(
        [f"HYBRID / {secondary.upper().replace('_', ' ')}"],
        DESIGN_WIDTH - PAD,
        cursor - ctx.u(4),
        ctx.font(11, 8),
        ctx.font(11, 8),
        "700",
        GOLD,
        anchor="end",
        letter_spacing=1.3,
    )
    parts.append(markup)
    cursor += ctx.u(26)

    sections = _sections_by_priority(ctx)
    holding = _outcome_section(ctx)
    remaining = [section for section in sections if section is not holding]
    main_sections = remaining[:2]
    side_sections = remaining[2:]
    if not side_sections and len(main_sections) == 2:
        main_sections, side_sections = remaining[:1], remaining[1:2]

    main_w = round(INNER_W * 0.62)
    side_x = PAD + main_w + ctx.u(32)
    side_w = INNER_W - main_w - ctx.u(32)
    body_size = ctx.font(17, 11)

    y_main = cursor
    for section in main_sections:
        groups = _measure_item_lines(ctx, [i.text for i in section.items], main_w - ctx.u(48), body_size, BODY_LINE_BUDGET)
        heading_markup, _ = _text(
            [_heading(section.heading)],
            PAD,
            y_main + body_size,
            body_size,
            ctx.font(13, 10),
            "800",
            INK,
            letter_spacing=1.4,
        )
        parts.append(heading_markup)
        parts.append(_line(PAD, y_main + ctx.u(30), PAD + ctx.u(92), y_main + ctx.u(30), GOLD, ctx.u(3)))
        y_main = _items_down(parts, PAD, y_main + ctx.u(52), groups, body_size, GRAY, "400", ctx.u(30))
        y_main += ctx.u(32)

    side_body = ctx.font(14, 10)
    side_blocks: List[Tuple[str, List[List[str]], int]] = []
    for section in side_sections[:3]:
        groups = _measure_item_lines(
            ctx, [i.text for i in section.items], side_w - ctx.u(56), side_body, BODY_LINE_BUDGET
        )
        side_blocks.append(
            (
                section.heading,
                groups,
                ctx.u(30) + _item_block_height(ctx, groups, side_body, ctx.u(12)),
            )
        )

    natural_side_h = ctx.u(118) + sum(block[2] for block in side_blocks) + ctx.u(24) * max(
        0, len(side_blocks) - 1
    )
    # The panel is sized to its content: stretching it to the canvas left a dark void
    # under a single sidebar block.
    side_h = natural_side_h
    side_bottom = cursor
    if side_blocks:
        parts.append(_rect(side_x, cursor, side_w, side_h, PANEL_INK, None, ctx.u(10)))
        parts.append(_rect(side_x, cursor, side_w, ctx.u(8), GOLD, None, 0))
        side_markup, _ = _text(
            ["AT A GLANCE"],
            side_x + ctx.u(26),
            cursor + ctx.u(42),
            ctx.font(12, 9),
            ctx.font(12, 9),
            "800",
            GOLD,
            letter_spacing=1.5,
        )
        parts.append(side_markup)
        slack = 0.0
        side_y = cursor + ctx.u(82)
        for heading, groups, block_h in side_blocks:
            label_markup, _ = _text(
                [_heading(heading)],
                side_x + ctx.u(26),
                side_y,
                ctx.font(11, 8),
                ctx.font(11, 8),
                "800",
                GOLD,
                letter_spacing=1.2,
            )
            parts.append(label_markup)
            side_y = _items_down(
                parts, side_x + ctx.u(26), side_y + ctx.u(26), groups, side_body, PANEL_TEXT, "400", ctx.u(12)
            )
            side_y += ctx.u(24) + slack
        side_bottom = cursor + side_h

    cursor = max(y_main, side_bottom) + ctx.u(14)

    if holding:
        quote_size = ctx.font(18, 12)
        lines = _wrap(holding.primary_text, INNER_W - ctx.u(90), quote_size, 4, "500")
        card_h = ctx.u(84) + len(lines) * round(quote_size * 1.34)
        parts.append(_rect(PAD, cursor, INNER_W, card_h, GOLD, None, ctx.u(8)))
        markup, _ = _text(
            [_heading(holding.heading)],
            PAD + ctx.u(30),
            cursor + ctx.u(34),
            ctx.font(12, 9),
            ctx.font(12, 9),
            "800",
            PANEL_INK,
            letter_spacing=1.3,
        )
        parts.append(markup)
        _items_down(parts, PAD + ctx.u(30), cursor + ctx.u(68), [lines], quote_size, PANEL_INK, "500", 0)
        cursor += card_h

    return parts, cursor


# ---------------------------------------------------------------------------
# Briefing sheet - dense multi-band explainer
# ---------------------------------------------------------------------------

BRIEFING_HEADLINE_SIZES = {"compact": 38, "standard": 48, "dramatic": 58}
CREAM = "#FBF5E9"
CREAM_PANEL = "#FCF8EF"

_EXPLAINER_MICRO = {
    "context": "BACKGROUND TO THE MATTER",
    "facts": "MATERIAL FACTS ON THE RECORD",
    "issues": "KEY LEGAL ISSUES EXAMINED BY THE COURT",
    "reasoning": "HOW THE COURT REASONED",
    "statutes": "PROVISIONS RELIED ON",
    "holding": "THE OPERATIVE ORDER",
    "implications": "IMPACT ON LAW AND PRACTICE",
    "timeline": "SEQUENCE OF EVENTS",
    "comparison": "CONTRASTING POSITIONS",
    "process": "THE MECHANISM IN THE RECORD",
    "argument": "WHAT THE PARTIES CONTENDED",
    "outcome": "WHAT THE COURT DECIDED",
}

_EXPLAINER_ICONS = ("court", "book", "checklist", "gavel", "bank", "people", "bond", "flag", "document", "calendar", "lock", "ballot", "scales")


def _icon_for_text(text: str, default: str = "court") -> str:
    """Choose a semantically appropriate vector icon based on legal keywords in text."""
    t = text.lower()
    if any(k in t for k in ("bank", "sbi", "fund", "money", "rupee", "financial", "treasury", "corporate", "contribution", "commercial")):
        return "bank"
    if any(k in t for k in ("donor", "purchaser", "person", "citizen", "voter", "individual", "people", "public", "human", "electorate", "society", "patient", "dignity")):
        return "people"
    if any(k in t for k in ("bond", "instrument", "promissory", "bearer", "cheque", "certificate", "share")):
        return "bond"
    if any(k in t for k in ("party", "political", "election", "campaign", "governance", "democracy", "government", "union of india", "state")):
        return "flag"
    if any(k in t for k in ("court", "bench", "supreme court", "high court", "tribunal", "judge", "constitution bench", "gavel")):
        return "court"
    if any(k in t for k in ("petition", "writ", "filing", "application", "document", "record", "disclosure", "information", "report", "published")):
        return "document"
    if any(k in t for k in ("holding", "held", "verdict", "justice", "right", "equality", "unconstitutional", "arbitrary", "order", "liberty")):
        return "scales"
    if any(k in t for k in ("act", "statute", "section", "article", "code", "ipc", "law", "rule", "provision", "constitution")):
        return "book"
    if any(k in t for k in ("time", "date", "deadline", "schedule", "period", "compliance", "delay", "year", "timeline")):
        return "calendar"
    if any(k in t for k in ("confidential", "secret", "anonymous", "privacy", "lock", "shield", "kyc", "security")):
        return "lock"
    if any(k in t for k in ("vote", "ballot", "franchise", "electoral")):
        return "ballot"
    return default


def _split_title_body(text: str, max_words: int = 4) -> Tuple[str, str]:
    """Extract a concise bold title and keep the descriptive body intact."""
    for delim in (":", " — ", " – ", " - "):
        if delim in text:
            parts = text.split(delim, 1)
            title = parts[0].strip()
            body = parts[1].strip()
            if 3 <= len(title) <= 45:
                return title.upper(), body

    t = text.lower()
    if "writ petition" in t or "petition filed" in t or ("petitioners" in t and "filed" in t):
        return "WRIT PETITIONS FILED", text
    if "section 309" in t:
        return "SECTION 309 CHALLENGE", text
    if "right to refuse" in t or "refuse medical" in t:
        return "REFUSAL OF TREATMENT", text
    if "right to die" in t or "die with dignity" in t:
        return "RIGHT TO LIFE & DIGNITY", text
    if "passive euthanasia" in t:
        return "PASSIVE EUTHANASIA", text
    if "constitution bench" in t or ("referred" in t and "bench" in t):
        return "REFERENCE TO BENCH", text
    if "precedent" in t or "gian kaur" in t or "aruna" in t or "rathinam" in t:
        return "JUDICIAL PRECEDENTS", text
    if "donor" in t or "purchaser" in t:
        return "DONOR / PURCHASER", text
    if "state bank" in t or "sbi" in t:
        return "STATE BANK OF INDIA (SBI)", text
    if "electoral bond" in t or "bearer instrument" in t:
        return "ELECTORAL BOND", text
    if "political party" in t or "redeem" in t:
        return "POLITICAL PARTY", text
    if "voters" in t or "right to know" in t or ("information" in t and "right" in t):
        return "VOTERS' RIGHT TO KNOW", text
    if "corporate" in t or "contribution" in t:
        return "CORPORATE CONTRIBUTIONS", text
    if "disclosure" in t or "encashment" in t:
        return "DISCLOSURE DIRECTIONS", text

    words = text.split()
    if len(words) > 7:
        title = " ".join(words[:max_words]).rstrip(" ,.;:-").upper()
        return title, text
    return "", text


def _statute_pill(text: str) -> Optional[str]:
    """Return a statutory or constitutional reference found anywhere in the text."""
    match = re.search(
        r"\b((?:Article|Section|Rule|Order|Clause|Regulation)\s+"
        r"[0-9]+[A-Za-z]?(?:\s*\([^)]{1,12}\)){0,3})\b",
        text,
        re.IGNORECASE,
    )
    return " ".join(match.group(1).split()).upper() if match else None


def _explainer_bar(ctx: _Ctx, y: float, heading: str, kind: str) -> Tuple[List[str], float]:
    parts: List[str] = []
    size = ctx.font(16, 11)
    micro_size = ctx.font(9, 8)
    label = _heading(heading)
    bar_w = min(int(INNER_W * 0.64), round(len(label) * size * 0.75) + ctx.u(40))
    bar_w = max(ctx.u(190), bar_w)
    height = ctx.u(31)
    gold_style = kind in {"process", "holding", "outcome", "facts", "context"}
    fill = GOLD if gold_style else PANEL_INK
    parts.append(_rect(PAD, y, bar_w, height, fill, None, ctx.u(3)))
    markup, _ = _text(
        [label],
        PAD + ctx.u(15),
        y + ctx.u(22),
        size,
        size,
        "800",
        WHITE,
        letter_spacing=0.8,
    )
    parts.append(markup)
    micro = _EXPLAINER_MICRO.get(kind, "LEGAL BRIEF")
    micro_markup, _ = _text(
        [micro],
        DESIGN_WIDTH - PAD,
        y + ctx.u(21),
        micro_size,
        micro_size,
        "700",
        PANEL_INK if not gold_style else MUTED,
        anchor="end",
        letter_spacing=1.3,
    )
    parts.append(micro_markup)
    return parts, y + height + ctx.u(10)


def _explainer_steps(ctx: _Ctx, y: float, section: ResolvedSection) -> Tuple[List[str], float]:
    """Numbered horizontal cards joined by arrows, each with an icon, bold title, and text."""
    parts: List[str] = []
    items = list(section.items)
    if len(items) < 3 and ctx.record and ctx.record.material_facts:
        existing_texts = {it.text.strip().lower() for it in items}
        for fact in ctx.record.material_facts:
            if fact.strip().lower() not in existing_texts and len(items) < 4:
                from app.pipeline.design_brief import ResolvedItem
                items.append(ResolvedItem(text=fact, source="material_facts", index=len(items)))
                existing_texts.add(fact.strip().lower())

    step_items = items[:4]
    callout_item = items[4] if len(items) > 4 else None

    count = len(step_items)
    gap = ctx.u(16)
    card_w = (INNER_W - gap * (count - 1)) // count
    body = ctx.font(13, 11)
    lh = round(body * 1.36)
    number_r = ctx.u(14, 11)
    icon_box = ctx.u(44, 34)

    prepared = []
    for item in step_items:
        title, clean_body = _split_title_body(item.text, max_words=3)
        art = _illustration_for(ctx, item.text)
        icon_type = _icon_for_text(item.text, default="document")
        title_lines = _wrap(title, card_w - ctx.u(18), ctx.font(12, 10), 2, "800") if title else []
        body_lines = _wrap(clean_body, card_w - ctx.u(18), body, 6, "400")
        prepared.append((title_lines, body_lines, art, icon_type))

    title_h = max(len(t_lines) * round(ctx.font(12, 10) * 1.25) for t_lines, _, _, _ in prepared) if any(p[0] for p in prepared) else 0
    body_h = max(len(b_lines) * lh for _, b_lines, _, _ in prepared)
    card_h = max(ctx.u(156), ctx.u(42) + icon_box + ctx.u(8) + title_h + ctx.u(6) + body_h + ctx.u(16))

    mid_y = y + card_h / 2

    for index, (title_lines, body_lines, art, icon_type) in enumerate(prepared):
        x = PAD + index * (card_w + gap)
        cx = x + card_w / 2

        parts.append(_rect(x, y, card_w, card_h, CREAM, "#E9E0CF", ctx.u(7), 1.1))

        # Top circle badge with number
        badge_cy = y + ctx.u(16)
        parts.append(_circle(cx, badge_cy, number_r, GOLD, None))
        num_markup, _ = _text(
            [str(index + 1)],
            cx,
            badge_cy + ctx.u(4),
            ctx.font(11, 8),
            ctx.font(11, 8),
            "800",
            WHITE,
            anchor="middle",
        )
        parts.append(num_markup)

        # Center icon or raster art
        icon_top = badge_cy + number_r + ctx.u(4)
        if art:
            _card_art_tile(parts, art, cx - icon_box / 2, icon_top, icon_box, ctx.u(4))
        else:
            scale_fac = icon_box / 24.0
            icon_markup = render_takeaway_icon(icon_type, GOLD)
            parts.append(
                f'<g transform="translate({_s(cx - icon_box / 2)}, {_s(icon_top)}) scale({scale_fac:.3f})">'
                f'{icon_markup}</g>\n'
            )

        content_y = icon_top + icon_box + ctx.u(6)
        if title_lines:
            t_markup, _ = _text(
                title_lines,
                cx,
                content_y + ctx.font(11, 9),
                round(ctx.font(11, 9) * 1.25),
                ctx.font(11, 9),
                "800",
                INK,
                anchor="middle",
                letter_spacing=0.4,
            )
            parts.append(t_markup)
            content_y += len(title_lines) * round(ctx.font(11, 9) * 1.25) + ctx.u(4)

        b_markup, _ = _text(
            body_lines,
            cx,
            content_y + body,
            lh,
            body,
            "400",
            GRAY,
            anchor="middle",
        )
        parts.append(b_markup)

        if index < count - 1:
            ax = x + card_w + gap / 2
            parts.append(_line(ax - ctx.u(5), mid_y, ax + ctx.u(3), mid_y, GOLD, ctx.u(2)))
            parts.append(
                _polygon(
                    [
                        (ax + ctx.u(9), mid_y),
                        (ax + ctx.u(2), mid_y - ctx.u(5)),
                        (ax + ctx.u(2), mid_y + ctx.u(5)),
                    ],
                    GOLD,
                )
            )

    cursor = y + card_h

    if callout_item:
        cursor += ctx.u(10)
        callout_lines = _wrap(callout_item.text, INNER_W - ctx.u(84), body, 3, "500")
        call_h = max(ctx.u(44), ctx.u(16) + len(callout_lines) * lh + ctx.u(12))
        parts.append(_rect(PAD, cursor, INNER_W, call_h, CREAM_PANEL, "#EADDBD", ctx.u(6), 1.0))
        call_icon = _icon_for_text(callout_item.text, default="lock")
        parts.append(
            f'<g transform="translate({_s(PAD + ctx.u(16))}, {_s(cursor + (call_h - 24) / 2)}) scale(1.0)">'
            f'{render_takeaway_icon(call_icon, GOLD)}</g>\n'
        )
        call_markup, _ = _text(
            callout_lines,
            PAD + ctx.u(48),
            cursor + ctx.u(14) + body,
            lh,
            body,
            "500",
            GRAY,
        )
        parts.append(call_markup)
        cursor += call_h

    return parts, cursor


def _explainer_cards(ctx: _Ctx, y: float, section: ResolvedSection) -> Tuple[List[str], float]:
    """Numbered issue cards with gold numeral badge, bold title, statute pill, and vector icon."""
    parts: List[str] = []
    items = section.items[:4]
    body = ctx.font(14, 11)
    lh = round(body * 1.38)
    title_size = ctx.font(14, 11)
    gap = ctx.u(14)
    count = len(items)
    columns = 2 if count >= 2 else 1
    rows = (count + columns - 1) // columns
    card_w = (INNER_W - gap * (columns - 1)) // columns
    pad_x = ctx.u(18)
    badge_r = ctx.u(13, 10)
    icon_box = ctx.u(40, 30)

    prepared = []
    for item in items:
        pill = _statute_pill(item.text)
        title, clean_text = _split_title_body(item.text, max_words=3)
        art = _illustration_for(ctx, item.text)
        icon_type = _icon_for_text(item.text, default="court")
        prepared.append((title, pill, clean_text, art, icon_type))

    cursor = y
    for row in range(rows):
        start = row * columns
        row_items = prepared[start:start + columns]
        is_full_width = (len(row_items) == 1 and count > 1)
        cur_card_w = INNER_W if is_full_width else card_w

        # Compute card height for this row
        row_lines = []
        for title, pill, clean_text, art, icon_type in row_items:
            wrap_w = cur_card_w - pad_x * 2 - (icon_box + ctx.u(16) if is_full_width else 0)
            wrapped = _wrap(clean_text, wrap_w, body, 7, "400")
            row_lines.append(wrapped)
        max_lines = max((len(l) for l in row_lines), default=2)
        has_pill = any(p[1] for p in row_items)
        base_pad = ctx.u(66) if has_pill else ctx.u(48)
        card_h = max(ctx.u(122), base_pad + max_lines * lh + ctx.u(16))

        for offset, ((title, pill, clean_text, art, icon_type), lines) in enumerate(zip(row_items, row_lines)):
            index = start + offset
            x = PAD if is_full_width else PAD + offset * (card_w + gap)

            parts.append(_rect(x, cursor, cur_card_w, card_h, CREAM_PANEL, "#E9E0CF", ctx.u(7), 1.1))

            # Gold circle badge with white number
            badge_cx = x + pad_x + badge_r
            badge_cy = cursor + ctx.u(20)
            parts.append(_circle(badge_cx, badge_cy, badge_r, GOLD, None))
            num_markup, _ = _text(
                [str(index + 1)],
                badge_cx,
                badge_cy + ctx.u(4.5),
                ctx.font(11, 9),
                ctx.font(11, 9),
                "800",
                WHITE,
                anchor="middle",
            )
            parts.append(num_markup)

            # Bold question title beside badge
            title_text = title if title else f"ISSUE {index + 1}"
            title_x = badge_cx + badge_r + ctx.u(10)
            avail_title_w = cur_card_w - (title_x - x) - icon_box - ctx.u(12)
            title_lines = _wrap(title_text, avail_title_w, title_size, 1, "800")
            title_markup, _ = _text(
                title_lines,
                title_x,
                badge_cy + ctx.u(4.5),
                title_size,
                title_size,
                "800",
                INK,
                letter_spacing=0.5,
            )
            parts.append(title_markup)

            # Icon in top right of card
            icon_x = x + cur_card_w - pad_x - icon_box
            if art:
                _card_art_tile(parts, art, icon_x, cursor + ctx.u(12), icon_box, ctx.u(4))
            else:
                scale_fac = icon_box / 24.0
                icon_markup = render_takeaway_icon(icon_type, GOLD)
                parts.append(
                    f'<g transform="translate({_s(icon_x)}, {_s(cursor + ctx.u(12))}) scale({scale_fac:.3f})">'
                    f'{icon_markup}</g>\n'
                )

            # Gold statute pill badge
            top_y = badge_cy + badge_r + ctx.u(6)
            if pill:
                pill_w = min(cur_card_w - pad_x * 2 - ctx.u(20), round(len(pill) * ctx.font(10, 8) * 0.68) + ctx.u(18))
                parts.append(_rect(x + pad_x, top_y, pill_w, ctx.u(20), GOLD, None, ctx.u(8)))
                p_markup, _ = _text(
                    [pill],
                    x + pad_x + pill_w / 2,
                    top_y + ctx.u(14),
                    ctx.font(9.5, 8),
                    ctx.font(9.5, 8),
                    "800",
                    WHITE,
                    anchor="middle",
                    letter_spacing=0.5,
                )
                parts.append(p_markup)
                body_y = top_y + ctx.u(26)
            else:
                body_y = top_y + ctx.u(4)

            # Body lines
            markup, _ = _text(lines, x + pad_x, body_y + body, lh, body, "400", GRAY)
            parts.append(markup)

        cursor += card_h + (gap if row < rows - 1 else 0)
    return parts, cursor


def _explainer_holding(ctx: _Ctx, y: float, section: ResolvedSection) -> Tuple[List[str], float]:
    """The operative order as a single gold band with a scales medallion and white inner panel."""
    parts: List[str] = []
    text_x = PAD + ctx.u(94)
    text_w = INNER_W - ctx.u(126)

    prepared = []
    for index, item in enumerate(section.items):
        size = ctx.font(16, 12) if index == 0 else ctx.font(14, 11)
        weight = "700" if index == 0 else "500"
        prepared.append((_wrap(item.text, text_w - ctx.u(24), size, 5, weight), size, weight))

    gap = ctx.u(6)
    text_h = sum(len(lines) * round(size * 1.36) for lines, size, _ in prepared)
    text_h += gap * max(0, len(prepared) - 1)
    inner_card_h = text_h + ctx.u(22)
    height = max(ctx.u(126), ctx.u(46) + inner_card_h + ctx.u(14))

    # Outer Gold Banner
    parts.append(_rect(PAD, y, INNER_W, height, GOLD, None, ctx.u(6)))

    # Circular Scales Medallion on left
    circle_r = ctx.u(36)
    circle_cx = PAD + ctx.u(50)
    circle_cy = y + height / 2
    parts.append(_circle(circle_cx, circle_cy, circle_r, "#FFFDF7", None))
    icon_size = circle_r * 1.55
    icon_scale = icon_size / 90.0
    icon = render_header_icon("scales", GOLD, GRAY)
    parts.append(
        f'<g transform="translate({_s(circle_cx - icon_size / 2)}, '
        f'{_s(circle_cy - icon_size / 2)}) scale({icon_scale:.3f})">{icon}</g>\n'
    )

    # Top Heading
    heading_markup, _ = _text(
        [_heading(section.heading)],
        text_x,
        y + ctx.u(24),
        ctx.font(16, 12),
        ctx.font(16, 12),
        "800",
        WHITE,
        letter_spacing=0.9,
    )
    parts.append(heading_markup)

    # Right micro label
    micro_size = ctx.font(9.5, 8)
    micro_label = _EXPLAINER_MICRO.get(section.kind, "THE OPERATIVE ORDER")
    micro_markup, _ = _text(
        [micro_label],
        DESIGN_WIDTH - PAD - ctx.u(18),
        y + ctx.u(23),
        micro_size,
        micro_size,
        "700",
        "#4A3810",
        anchor="end",
        letter_spacing=1.1,
    )
    parts.append(micro_markup)

    # Inner White Card for the holding text (gives high contrast like Image 2!)
    inner_card_y = y + ctx.u(38)
    parts.append(_rect(text_x - ctx.u(6), inner_card_y, text_w + ctx.u(12), inner_card_h, "#FFFDF7", None, ctx.u(6)))

    # Holding text inside inner white card
    cursor = inner_card_y + ctx.u(11)
    for index, (lines, size, weight) in enumerate(prepared):
        lh = round(size * 1.36)
        markup, cursor = _text(lines, text_x + ctx.u(6), cursor + size, lh, size, weight, INK)
        parts.append(markup)
        if index < len(prepared) - 1:
            cursor += gap

    return parts, y + height


def _explainer_impact(ctx: _Ctx, y: float, section: ResolvedSection) -> Tuple[List[str], float]:
    """Bar plus a cream strip with people icon that reads as the closing 'why it matters' block."""
    parts: List[str] = []
    bar_parts, cursor = _explainer_bar(ctx, y, section.heading, section.kind)
    parts.extend(bar_parts)
    body = ctx.font(14, 11)
    lh = round(body * 1.38)
    first_text = section.items[0].text if section.items else ""
    art = _illustration_for(ctx, first_text)
    art_side = ctx.u(54)
    text_x = PAD + ctx.u(16) + art_side + ctx.u(16)
    text_w = DESIGN_WIDTH - PAD - text_x - ctx.u(16)

    groups = [_wrap(item.text, text_w, body, 5, "400") for item in section.items]
    text_h = sum(len(lines) for lines in groups) * lh + ctx.u(8) * (len(groups) - 1)
    height = max(ctx.u(94), text_h + ctx.u(28), art_side + ctx.u(24))
    parts.append(_rect(PAD, cursor, INNER_W, height, CREAM_PANEL, "#E9E0CF", ctx.u(7), 1.1))

    if art:
        _card_art_tile(parts, art, PAD + ctx.u(16), cursor + (height - art_side) / 2, art_side, ctx.u(6))
    else:
        icon_cx = PAD + ctx.u(16) + art_side / 2
        icon_cy = cursor + height / 2
        parts.append(_circle(icon_cx, icon_cy, art_side / 2, "#F7EDD5", GOLD, 1.2))
        parts.append(
            f'<g transform="translate({_s(icon_cx - 15)}, {_s(icon_cy - 15)}) scale(1.25)">'
            f'{render_takeaway_icon("people", GOLD)}</g>\n'
        )

    _items_down(
        parts,
        text_x,
        cursor + ctx.u(16),
        groups,
        body,
        GRAY,
        "400",
        ctx.u(8),
    )
    return parts, cursor + height


def _briefing_sheet(ctx: _Ctx) -> Tuple[List[str], float]:
    """Dense explainer: header, banded sections, step rows, issue cards and a closing impact strip."""
    parts, cursor = _brand_header(ctx, FAMILY_LABELS["briefing_sheet"])
    cursor += ctx.u(6)

    base_width = INNER_W
    spot_side = 160
    spot = ctx.u(spot_side) if ctx.artwork else 0
    head_w = (
        max(int(INNER_W * 0.58), base_width - spot - ctx.u(20))
        if spot
        else base_width
    )
    hl_parts, cursor = _headline_with_spot(
        ctx,
        cursor,
        base_width,
        spot_side=spot_side,
        base_sizes=BRIEFING_HEADLINE_SIZES,
        budget_ratio=0.26,
    )
    parts.extend(hl_parts)

    raw_subtitle = " ".join((ctx.plan.subtitle or "").split())
    subtitle = re.split(r"(?<=[.!?])\s+", raw_subtitle)[0] if raw_subtitle else ""
    if subtitle and not _copy_overlaps(subtitle, ctx.brief.headline):
        size = ctx.font(17, 11)
        lines = _wrap(subtitle, head_w, size, 2, "600")
        if not _truncated(lines):
            markup, bottom = _text(lines, PAD, cursor + size, round(size * 1.34), size, "600", GOLD)
            parts.append(markup)
            cursor = bottom + ctx.u(8)
    meta = " ".join((ctx.plan.meta_line or "").split()).upper()
    if meta:
        size = ctx.font(11, 9)
        lines = _wrap(meta, head_w, size, 2, "600")
        if not _truncated(lines):
            markup, bottom = _text(lines, PAD, cursor + size, round(size * 1.3), size, "600", MUTED, letter_spacing=0.9)
            parts.append(markup)
            cursor = bottom + ctx.u(8)
    cursor += ctx.u(12)

    sections: List[ResolvedSection] = []
    seen_text = set()
    for section in ctx.sections:
        items = []
        for item in section.items:
            key = item.text.strip().lower()
            if key in seen_text:
                continue
            seen_text.add(key)
            items.append(item)
        if items:
            sections.append(
                ResolvedSection(
                    heading=section.heading,
                    kind=section.kind,
                    emphasis=section.emphasis,
                    items=items,
                )
            )

    # Sort sections in natural legal editorial flow: Facts -> Issues -> Holding -> Reasoning -> Implications
    def _section_sort_key(s: ResolvedSection) -> int:
        k = s.kind
        if k in {"facts", "process", "context", "timeline"}:
            return 1
        if k in {"issues", "questions"}:
            return 2
        if k in {"holding", "outcome"}:
            return 3
        if k in {"reasoning", "statutes", "directions", "comparison", "argument"}:
            return 4
        if k in {"implications", "impact"}:
            return 5
        return 6

    sections.sort(key=_section_sort_key)

    for section in sections:
        kind = section.kind
        if kind in {"holding", "outcome"}:
            block, cursor = _explainer_holding(ctx, cursor, section)
            parts.extend(block)
        elif kind == "implications":
            block, cursor = _explainer_impact(ctx, cursor, section)
            parts.extend(block)
        elif kind in {"process", "timeline", "facts", "context", "directions"}:
            bar, cursor = _explainer_bar(ctx, cursor, section.heading, kind)
            parts.extend(bar)
            block, cursor = _explainer_steps(ctx, cursor, section)
            parts.extend(block)
        else:
            bar, cursor = _explainer_bar(ctx, cursor, section.heading, kind)
            parts.extend(bar)
            block, cursor = _explainer_cards(ctx, cursor, section)
            parts.extend(block)
        cursor += ctx.u(12)

    return parts, cursor - ctx.u(12)


_BUILDERS: Dict[str, Callable[[_Ctx], Tuple[List[str], float]]] = {
    "landmark_cover": _landmark_cover,
    "split_comparison": _split_comparison,
    "timeline": _timeline,
    "decision_tree": _decision_tree,
    "statutory_map": _statutory_map,
    "chart_led": _chart_led,
    "process_flow": _process_flow,
    "argument_outcome": _argument_outcome,
    "briefing_sheet": _briefing_sheet,
    "hybrid": _hybrid,
}


def _source_and_footer(plan: InfographicContentPlan, canvas_h: float, footer_h: float) -> str:
    parts: List[str] = []
    source_y = canvas_h - footer_h - 42
    disclaimer = plan.verification_note or (
        "Editorial summary of the cited source. Verify against the original order before relying on it."
    )
    lines = _wrap(disclaimer, INNER_W, 12, 2, "700")
    markup, _ = _text(lines, PAD, source_y, 17, 12, "700", "#8A5A00", letter_spacing=0.2)
    parts.append(markup)

    if plan.source_url:
        # Both provenance lines sit on the same baseline, so the source gets a measured share
        # of the page. A long URL is cut by character budget rather than by _wrap: a URL is
        # one unbreakable token, and wrapping it to a single line appends an ellipsis after
        # the publisher, which would hide the domain the quality check needs.
        publisher = f"{plan.publisher[:28]} - " if plan.publisher else ""
        provenance = f"Source: {publisher}{plan.source_url}"
        char_budget = int((INNER_W * 0.60) / (11 * 0.5))
        if len(provenance) > char_budget:
            provenance = provenance[: char_budget - 1].rstrip(" ,.;:-/") + "…"
        analysis = (
            f"Brief: {plan.design_brief.layout_family.value if plan.design_brief else 'dynamic'}"
            f" | {str(plan.analysis_source).split(':')[-1]}"
        )
        source_size = 11
        analysis_lines = _wrap(analysis, int(INNER_W * 0.36), source_size, 1, "400")
        source_line, _ = _text(
            [provenance],
            PAD,
            canvas_h - footer_h - 15,
            14,
            source_size,
            "400",
            MUTED,
        )
        parts.append(source_line)
        if plan.analysis_source:
            analysis_line, _ = _text(
                analysis_lines,
                DESIGN_WIDTH - PAD,
                canvas_h - footer_h - 15,
                14,
                source_size,
                "400",
                "#A9ABB4",
                anchor="end",
            )
            parts.append(analysis_line)

    footer_y = canvas_h - footer_h
    ratio = footer_h / FOOTER_H
    brand_size = max(15, round(30 * ratio))
    date_size = max(10, round(18 * ratio))
    parts.append(
        f'<g transform="translate(0, {_s(footer_y)})">\n'
        f'  <rect width="{DESIGN_WIDTH}" height="{_s(footer_h)}" fill="{GOLD}"/>\n'
        f'  <text x="{PAD}" y="{_s(footer_h * .64)}" fill="{INK}" font-size="{brand_size}" '
        f'font-weight="800" letter-spacing="0.2" font-family="{FONT_STACK}">{escape_xml(plan.footer_brand)}</text>\n'
        f'  <text x="{DESIGN_WIDTH - PAD}" y="{_s(footer_h * .62)}" fill="#FFF8E8" '
        f'font-size="{date_size}" font-weight="500" text-anchor="end" font-family="{FONT_STACK}">'
        f'{escape_xml(plan.footer_date or "")}</text>\n'
        f'</g>\n'
    )
    return "".join(parts)



def _render_slack_enrichment(ctx: _Ctx, cursor: float, slack: float) -> Tuple[List[str], float]:
    """If the layout has leftover vertical space, draw an authoritative statutory/bench strip.

    This ensures posters never have empty voids at the bottom, incorporating verified
    constitutional articles, statutes, bench details, and precedents from the record.
    """
    parts: List[str] = []
    record = ctx.record
    statutes = [str(s).strip() for s in (record.relevant_statutes or []) if str(s).strip()]
    precedents = [str(p).strip() for p in (record.precedents_cited or []) if str(p).strip()]
    bench = record.bench_composition or []
    bench_str = ", ".join(str(b) for b in bench) if isinstance(bench, list) else str(bench or "")

    # Check what text has already been rendered in sections
    rendered_text = " ".join(item.text.lower() for s in ctx.sections for item in s.items)
    unrendered_statutes = [s for s in statutes if s.lower() not in rendered_text][:3]
    unrendered_precedents = [p for p in precedents if p.lower() not in rendered_text][:2]

    if not unrendered_statutes and not unrendered_precedents and not bench_str:
        implications = [
            str(imp).strip()
            for imp in (record.practical_implications or [])
            if str(imp).strip() and str(imp).lower() not in rendered_text
        ]
        if implications:
            unrendered_statutes = implications[:2]

    if not unrendered_statutes and not unrendered_precedents and not bench_str:
        return parts, cursor

    cursor += ctx.u(8)
    avail_h = slack - ctx.u(16)

    heading = (
        "RELEVANT STATUTORY & CONSTITUTIONAL PROVISIONS"
        if unrendered_statutes
        else "JUDICIAL BENCH & PRECEDENTS"
    )
    bar_parts, cursor = _explainer_bar(ctx, cursor, heading, "statutes")
    parts.extend(bar_parts)

    if unrendered_statutes:
        gap = ctx.u(14)
        count = len(unrendered_statutes)
        col_w = (INNER_W - gap * (count - 1)) // count
        font_size = ctx.font(14, 11)
        lh = round(font_size * 1.36)

        prepared = []
        for text in unrendered_statutes:
            pill = _statute_pill(text)
            clean_text = text
            if pill and text.upper().startswith(pill):
                clean_text = text[len(pill):].lstrip(" :-—–") or text
            lines = _wrap(clean_text, col_w - ctx.u(32), font_size, 4, "400")
            prepared.append((pill, lines))

        card_h = max(ctx.u(88), min(avail_h - ctx.u(32), ctx.u(180)))
        for i, (pill, lines) in enumerate(prepared):
            x = PAD + i * (col_w + gap)
            parts.append(_rect(x, cursor, col_w, card_h, CREAM_PANEL, "#E9E0CF", ctx.u(8), 1.1))
            if pill:
                pill_w = min(col_w - ctx.u(32), round(len(pill) * ctx.font(9.5, 8) * 0.65) + ctx.u(18))
                parts.append(_rect(x + ctx.u(16), cursor + ctx.u(12), pill_w, ctx.u(20), GOLD, None, ctx.u(8)))
                p_markup, _ = _text(
                    [pill],
                    x + ctx.u(16) + pill_w / 2,
                    cursor + ctx.u(25),
                    ctx.font(9.5, 8),
                    ctx.font(9.5, 8),
                    "800",
                    WHITE,
                    anchor="middle",
                    letter_spacing=0.5,
                )
                parts.append(p_markup)
                text_top = cursor + ctx.u(42)
            else:
                text_top = cursor + ctx.u(16)
            markup, _ = _text(lines, x + ctx.u(16), text_top + font_size, lh, font_size, "400", GRAY)
            parts.append(markup)
        cursor += card_h

    elif unrendered_precedents or bench_str:
        card_h = max(ctx.u(72), min(avail_h - ctx.u(32), ctx.u(140)))
        parts.append(_rect(PAD, cursor, INNER_W, card_h, CREAM_PANEL, "#E9E0CF", ctx.u(8), 1.1))
        info_lines = []
        if bench_str:
            info_lines.append(f"Bench: {bench_str}")
        if unrendered_precedents:
            info_lines.append("Precedents Considered: " + " • ".join(unrendered_precedents))
        font_size = ctx.font(14, 11)
        lh = round(font_size * 1.4)
        wrapped = []
        for line in info_lines:
            wrapped.extend(_wrap(line, INNER_W - ctx.u(44), font_size, 2, "500"))
        markup, _ = _text(wrapped, PAD + ctx.u(22), cursor + ctx.u(18) + font_size, lh, font_size, "500", GRAY)
        parts.append(markup)
        cursor += card_h

    return parts, cursor


def render_dynamic_svg(
    plan: InfographicContentPlan,
    record: LegalRecord,
    brief: object,
    width: int = 800,
    height: int = 1240,
    artwork_base64_data_uri: Optional[str] = None,
    illustrations: Optional[Dict[str, str]] = None,
) -> str:
    """Render one of the Legal Snaps layout families selected by the validated brief."""
    from app.schemas import DesignBrief

    if not isinstance(brief, DesignBrief):
        brief = DesignBrief.model_validate(brief)
    resolved = resolve_design_brief(brief, record)
    canvas_h = DESIGN_WIDTH * (height / width)
    footer_h = max(46.0, FOOTER_H * min(1.0, canvas_h / 1350)) if canvas_h < 900 else FOOTER_H
    avail = canvas_h - footer_h - (68 if plan.source_url else 42)
    builder = _BUILDERS[resolved.family.value]

    Fit = Tuple[List[str], float, float, List[ResolvedSection]]
    whole_readable: Optional[Fit] = None
    whole_cramped: Optional[Fit] = None
    cut_copy: Optional[Fit] = None
    last: Optional[Fit] = None

    def keep_more(candidate: Fit, current: Optional[Fit]) -> bool:
        """More legal content kept wins, then the scale that best fills the canvas comfortably."""
        if current is None:
            return True
        if len(candidate[3]) != len(current[3]):
            return len(candidate[3]) > len(current[3])
        cand_bottom, cand_scale = candidate[1], candidate[2]
        curr_bottom, curr_scale = current[1], current[2]
        # Prefer filling 80% to 95% of avail comfortably
        cand_fill = cand_bottom / avail if avail else 0
        curr_fill = curr_bottom / avail if avail else 0
        cand_good_fill = 0.75 <= cand_fill <= 0.98
        curr_good_fill = 0.75 <= curr_fill <= 0.98
        if cand_good_fill and not curr_good_fill:
            return True
        if curr_good_fill and not cand_good_fill:
            return False
        return cand_scale > curr_scale

    for section_limit in (len(resolved.sections), 5, 4, 3, 2, 1):
        if section_limit > len(resolved.sections):
            continue
        sections = resolved.sections[:section_limit]
        for scale in SCALES:
            ctx = _Ctx(
                plan=plan,
                record=record,
                brief=resolved,
                sections=sections,
                canvas_h=canvas_h,
                footer_h=footer_h,
                avail=avail,
                scale=scale,
                artwork=artwork_base64_data_uri,
                illustrations=illustrations or {},
            )
            parts, bottom = builder(ctx)
            candidate = (parts, bottom, scale, sections)
            last = candidate
            if bottom > avail:
                continue
            if _has_cut_copy(parts):
                if keep_more(candidate, cut_copy):
                    cut_copy = candidate
                continue
            if scale >= READABLE_SCALE_FLOOR:
                if keep_more(candidate, whole_readable):
                    whole_readable = candidate
                    # If this scale fills >= 80% of canvas with all sections, it's ideal
                    if bottom >= avail * 0.80 and len(sections) == len(resolved.sections):
                        break
            elif keep_more(candidate, whole_cramped):
                whole_cramped = candidate

        if whole_readable and len(whole_readable[3]) == len(resolved.sections):
            break

    chosen = whole_readable or whole_cramped or cut_copy or last
    if whole_readable is None and whole_cramped is not None:
        logger.info(
            "Dynamic layout %s had to drop below the readable scale floor to fit; using scale %.2f.",
            resolved.family.value,
            chosen[2],
        )
    if chosen is cut_copy:
        logger.warning(
            "Dynamic layout %s could not fit every sentence whole at any scale; clipping at %.2f.",
            resolved.family.value,
            chosen[2],
        )
    parts, bottom, scale, sections = chosen or (["<!-- empty -->"], PAD, 0.65, resolved.sections[:2])

    ctx = _Ctx(
        plan=plan,
        record=record,
        brief=resolved,
        sections=sections,
        canvas_h=canvas_h,
        footer_h=footer_h,
        avail=avail,
        scale=scale,
        artwork=artwork_base64_data_uri,
        illustrations=illustrations or {},
    )

    # Slack fill: if content finishes early leaving dead white space,
    # enrich with verified statutory, constitutional, or precedent provisions from the record
    slack = avail - bottom
    if slack >= 70:
        enrichment_parts, new_bottom = _render_slack_enrichment(ctx, bottom, slack)
        if enrichment_parts and new_bottom <= avail:
            parts.extend(enrichment_parts)
            bottom = new_bottom
            slack = avail - bottom

    if slack > 12 and (bottom + min(55.0, round(slack * 0.45))) <= avail:
        shift_y = min(55.0, round(slack * 0.45))
        parts = [f'<g transform="translate(0, {_s(shift_y)})">\n'] + parts + ['</g>\n']
        bottom = bottom + shift_y

    if bottom > avail:
        logger.warning(
            "Dynamic layout %s still overflows by %.1f design units at scale %.2f.",
            resolved.family.value,
            bottom - avail,
            scale,
        )

    signature = resolved.signature

    header_parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {DESIGN_WIDTH} {_s(canvas_h)}" '
        f'data-layout-family="{resolved.family.value}" data-layout-signature="{escape_xml(signature)}" '
        f'data-layout-scale="{scale}" data-content-bottom="{_s(bottom)}" '
        f'data-sections-rendered="{len(sections)}" data-sections-planned="{len(resolved.sections)}" '
        f'data-canvas-bottom="{_s(avail)}">\n'
        f'<defs>\n'
        f'  <filter id="dynamicShadow" x="-4%" y="-4%" width="108%" height="112%">\n'
        f'    <feDropShadow dx="0" dy="4" stdDeviation="7" flood-color="{INK}" flood-opacity="0.055"/>\n'
        f'  </filter>\n'
        f'</defs>\n'
        f'<rect width="{DESIGN_WIDTH}" height="{_s(canvas_h)}" fill="{WHITE}"/>\n'
    ]
    header_parts.extend(parts)
    header_parts.append(_source_and_footer(plan, canvas_h, footer_h))
    header_parts.append("</svg>")
    return "".join(header_parts)
