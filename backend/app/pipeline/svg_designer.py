import re
import xml.sax.saxutils as saxutils
import logging
from dataclasses import dataclass
from typing import List, Optional

from app.schemas import InfographicContentPlan

logger = logging.getLogger(__name__)

# Everything below is laid out in a 1080-unit-wide design space and scaled to the
# requested canvas through the SVG viewBox. That keeps the type hierarchy identical
# on every output size instead of re-flowing at the wrong scale.
DESIGN_WIDTH = 1080
PAD = 56
FOOTER_H = 88
ICON_W = 150

PRIMARY_GOLD = "#CFA444"
GOLD_SOFT = "#F6EBD2"
DARK_GRAY = "#4A4C5A"
HEADLINE_DARK = "#2A2E3D"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#E9E2D4"
MUTED_TEXT = "#8B8E99"

FONT_STACK = "'Poppins', 'DejaVu Sans', 'Helvetica Neue', sans-serif"


def escape_xml(text: Optional[str]) -> str:
    if not text:
        return ""
    return saxutils.escape(str(text), {'"': "&quot;", "'": "&apos;"})


def wrap_text_into_lines(text: str, max_chars_per_line: int) -> List[str]:
    """Break text into lines respecting word boundaries."""
    if not text:
        return []
    words = text.split()
    lines = []
    current_line = []
    current_len = 0

    for word in words:
        word_len = len(word)
        extra = 1 if current_line else 0
        if current_len + word_len + extra <= max_chars_per_line:
            current_line.append(word)
            current_len += word_len + extra
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_len = word_len

    if current_line:
        lines.append(" ".join(current_line))
    return lines


def _balance_lines(text: str, per_line: int, line_count: int) -> Optional[List[str]]:
    """Rewrite a greedy wrap into evenly filled lines with the same line count.

    Keeps the same number of lines (so the measured header height stays valid) but
    minimises raggedness, which stops a headline from orphaning its last word.
    """
    words = text.split()
    if line_count <= 1 or len(words) <= 1:
        return None

    count = len(words)
    lengths = [0] * (count + 1)
    for i, word in enumerate(words):
        lengths[i + 1] = lengths[i] + len(word)

    inf = float("inf")
    cost = [[inf] * (count + 1) for _ in range(line_count + 1)]
    cut = [[-1] * (count + 1) for _ in range(line_count + 1)]
    cost[0][count] = 0

    for k in range(1, line_count + 1):
        for i in range(count - 1, -1, -1):
            for j in range(i + 1, count + 1):
                width = lengths[j] - lengths[i] + (j - i - 1)
                if width > per_line:
                    break
                if cost[k - 1][j] == inf:
                    continue
                slack = per_line - width
                candidate = slack * slack + cost[k - 1][j]
                if candidate < cost[k][i]:
                    cost[k][i] = candidate
                    cut[k][i] = j

    if cut[line_count][0] == -1:
        return None

    lines: List[str] = []
    i = 0
    for k in range(line_count, 0, -1):
        j = cut[k][i]
        lines.append(" ".join(words[i:j]))
        i = j
    return lines


def _wrap(
    text: Optional[str],
    max_width: int,
    font_size: int,
    max_lines: int,
    weight: str = "normal",
    uppercase: bool = False,
    balance: bool = False,
) -> List[str]:
    """Wrap to a pixel width and ellipsise overflow instead of cutting mid-word.

    The ratios are measured from Poppins renders; they are deliberately a little
    wide so measured card heights never come out shorter than the painted text.
    """
    if not text:
        return []
    factor = 0.50
    if weight in ("700", "800"):
        factor = 0.60
    elif weight == "600":
        factor = 0.52
    elif weight == "500":
        factor = 0.49
    if uppercase:
        factor += 0.03
    per_line = max(8, int(max_width / (font_size * factor)))

    lines = wrap_text_into_lines(text, per_line)
    if balance and 1 < len(lines) <= max_lines:
        balanced = _balance_lines(text, per_line, len(lines))
        if balanced:
            lines = balanced
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        if len(last) >= per_line - 1:
            cut = last[: max(4, per_line - 2)]
            if " " in cut:
                cut = cut.rsplit(" ", 1)[0]
            last = cut.rstrip(" ,.;:-")
        lines[-1] = last.rstrip(" ,.;:-") + "…"
    return lines


def render_tspan_text(
    lines: List[str],
    x: int,
    start_y: int,
    line_height: int,
    fill: str = DARK_GRAY,
    font_size: int = 18,
    font_weight: str = "normal",
    font_family: str = FONT_STACK,
    letter_spacing: Optional[float] = None,
) -> str:
    if not lines:
        return ""
    spacing = f' letter-spacing="{letter_spacing}"' if letter_spacing is not None else ""
    tspans = []
    for i, line in enumerate(lines):
        y = start_y + (i * line_height)
        tspans.append(f'<tspan x="{x}" y="{y}">{escape_xml(line)}</tspan>')

    return (
        f'<text x="{x}" y="{start_y}" fill="{fill}" font-size="{font_size}" '
        f'font-weight="{font_weight}" font-family="{font_family}"{spacing}>\n'
        f'  {"".join(tspans)}\n'
        f'</text>'
    )


def render_header_icon(icon_type: str, gold: str, gray: str) -> str:
    """Gold/gray legal header icon drawn in a 90x90 local box."""
    if icon_type == "scales":
        return f'''
        <g>
          <line x1="45" y1="14" x2="45" y2="80" stroke="{gold}" stroke-width="5" stroke-linecap="round"/>
          <line x1="26" y1="80" x2="64" y2="80" stroke="{gold}" stroke-width="5.5" stroke-linecap="round"/>
          <circle cx="45" cy="14" r="5.5" fill="{gold}"/>
          <line x1="10" y1="22" x2="80" y2="37" stroke="{gray}" stroke-width="4.5" stroke-linecap="round"/>
          <line x1="10" y1="22" x2="4" y2="48" stroke="{gray}" stroke-width="2"/>
          <line x1="10" y1="22" x2="24" y2="48" stroke="{gray}" stroke-width="2"/>
          <path d="M 1 48 Q 14 57 27 48 Z" fill="{gold}" stroke="{gray}" stroke-width="1.6"/>
          <line x1="80" y1="37" x2="66" y2="64" stroke="{gray}" stroke-width="2"/>
          <line x1="80" y1="37" x2="90" y2="64" stroke="{gray}" stroke-width="2"/>
          <path d="M 64 64 Q 78 75 92 64 Z" fill="{gold}" stroke="{gray}" stroke-width="1.6"/>
        </g>
        '''
    return f'''
    <g>
      <rect x="4" y="72" width="60" height="9" rx="3" fill="{gold}"/>
      <g transform="rotate(-35 36 40)">
        <rect x="20" y="14" width="30" height="44" rx="4" fill="{gold}" stroke="{gray}" stroke-width="1.6"/>
        <rect x="16" y="9" width="38" height="7" rx="2" fill="{gold}"/>
        <rect x="16" y="56" width="38" height="7" rx="2" fill="{gold}"/>
        <line x1="35" y1="63" x2="35" y2="98" stroke="{gold}" stroke-width="7" stroke-linecap="round"/>
      </g>
    </g>
    '''


def render_takeaway_icon(icon_type: str, gold: str) -> str:
    """Icon drawn in a 24x24 local box."""
    if icon_type in ("parliament", "court"):
        return f'''
        <g>
          <polygon points="12,2 2,9 22,9" fill="{gold}"/>
          <line x1="4" y1="9" x2="4" y2="18" stroke="{gold}" stroke-width="2"/>
          <line x1="9" y1="9" x2="9" y2="18" stroke="{gold}" stroke-width="2"/>
          <line x1="15" y1="9" x2="15" y2="18" stroke="{gold}" stroke-width="2"/>
          <line x1="20" y1="9" x2="20" y2="18" stroke="{gold}" stroke-width="2"/>
          <rect x="1" y="18" width="22" height="3" fill="{gold}"/>
        </g>
        '''
    if icon_type in ("book", "checklist"):
        return f'''
        <g>
          <rect x="2" y="1" width="16" height="20" rx="2" fill="#FFFFFF" stroke="{gold}" stroke-width="1.8"/>
          <line x1="6" y1="6" x2="14" y2="6" stroke="{gold}" stroke-width="1.5"/>
          <line x1="6" y1="10" x2="14" y2="10" stroke="{gold}" stroke-width="1.5"/>
          <line x1="6" y1="14" x2="11" y2="14" stroke="{gold}" stroke-width="1.5"/>
          <circle cx="16" cy="17" r="5" fill="{gold}"/>
          <path d="M14 17 L15.5 18.5 L18 15.5" stroke="#FFFFFF" stroke-width="1.3" fill="none"/>
        </g>
        '''
    if icon_type in ("prohibited", "warning"):
        return f'''
        <g>
          <circle cx="12" cy="11" r="9" fill="none" stroke="{gold}" stroke-width="2.2"/>
          <line x1="5.5" y1="4.5" x2="18.5" y2="17.5" stroke="{gold}" stroke-width="2.2"/>
        </g>
        '''
    return f'''
    <g>
      <rect x="0" y="17" width="18" height="3" rx="1" fill="{gold}"/>
      <g transform="rotate(-30 10 10)">
        <rect x="7" y="2" width="7" height="12" rx="1" fill="{gold}"/>
        <line x1="10.5" y1="14" x2="10.5" y2="24" stroke="{gold}" stroke-width="2.2" stroke-linecap="round"/>
      </g>
    </g>
    '''


def render_editorial_illustration(gold: str, gray: str, year: Optional[str] = None) -> str:
    """Vector fallback illustration drawn in a 140x150 local box."""
    year_label = (
        f'<text x="28" y="60" fill="{gray}" font-size="10" font-weight="700" text-anchor="middle" '
        f'font-family="{FONT_STACK}">{escape_xml(year)}</text>'
        if year else ""
    )
    return f'''
    <g>
      <g opacity="0.16">
        <polygon points="65,40 10,72 120,72" fill="{gray}"/>
        <rect x="18" y="72" width="12" height="60" fill="{gray}"/>
        <rect x="42" y="72" width="12" height="60" fill="{gray}"/>
        <rect x="66" y="72" width="12" height="60" fill="{gray}"/>
        <rect x="90" y="72" width="12" height="60" fill="{gray}"/>
        <rect x="6" y="132" width="118" height="10" rx="2" fill="{gray}"/>
      </g>
      <g transform="translate(18, 12)">
        <circle cx="28" cy="28" r="24" fill="#FFFFFF" stroke="{gold}" stroke-width="5"/>
        <line x1="28" y1="28" x2="28" y2="14" stroke="{gray}" stroke-width="3" stroke-linecap="round"/>
        <line x1="28" y1="28" x2="38" y2="28" stroke="{gray}" stroke-width="3" stroke-linecap="round"/>
        {year_label}
      </g>
      <g transform="translate(48, 8)">
        <circle cx="62" cy="38" r="14" fill="#F8C798"/>
        <path d="M48 36 Q62 18 76 36 Q72 24 58 24 Z" fill="{HEADLINE_DARK}"/>
        <circle cx="58" cy="36" r="1.5" fill="{HEADLINE_DARK}"/>
        <circle cx="68" cy="36" r="1.5" fill="{HEADLINE_DARK}"/>
        <path d="M60 43 Q63 46 66 43" stroke="{HEADLINE_DARK}" stroke-width="1.2" fill="none"/>
        <polygon points="56,54 62,64 68,54" fill="#FFFFFF"/>
        <path d="M42 54 L55 54 L62 76 L69 54 L82 54 L88 140 L36 140 Z" fill="{HEADLINE_DARK}"/>
        <rect x="36" y="80" width="34" height="46" rx="3" fill="{gold}"/>
        <rect x="40" y="84" width="26" height="3" fill="#FFFFFF" opacity="0.6"/>
        <circle cx="64" cy="116" r="5" fill="#F8C798"/>
        <circle cx="68" cy="118" r="4.5" fill="#F8C798"/>
      </g>
    </g>
    '''


@dataclass(frozen=True)
class _Spec:
    title_size: int
    title_lh: int
    subtitle_size: int
    subtitle_lh: int
    body_size: int
    body_lh: int
    overview_lines: int
    take_size: int
    take_lh: int
    takeaway_count: int
    takeaway_lines: int
    comp_size: int
    comp_lh: int
    comp_count: int
    comp_lines: int
    art: int
    gap: int


# Ordered from most generous to most compact. The first spec whose measured height
# fits the canvas is used, so a square or landscape canvas degrades gracefully
# instead of spilling text over the footer.
_SPECS: List[_Spec] = [
    _Spec(52, 58, 24, 32, 21, 31, 5, 22, 31, 4, 2, 20, 29, 3, 3, 340, 32),
    _Spec(48, 54, 23, 31, 20, 30, 4, 21, 30, 4, 2, 19, 28, 3, 3, 320, 28),
    _Spec(46, 52, 22, 29, 19, 28, 4, 20, 29, 4, 2, 18, 27, 3, 3, 300, 26),
    _Spec(42, 48, 20, 27, 18, 26, 3, 19, 27, 4, 2, 17, 25, 3, 3, 270, 22),
    # A square editorial canvas still gets the complete composition. The previous
    # compact spec silently removed the illustration and comparison, leaving most
    # of the poster blank even though the job had supplied both.
    _Spec(38, 44, 18, 24, 17, 24, 3, 18, 25, 4, 2, 16, 23, 2, 2, 240, 16),
    _Spec(30, 34, 14, 18, 14, 19, 2, 15, 20, 2, 1, 0, 0, 0, 0, 0, 14),
]


class _Layout:
    def __init__(self, plan: InfographicContentPlan, spec: _Spec, inner_w: int):
        self.plan = plan
        self.spec = spec
        self.inner_w = inner_w
        s = spec

        self.meta_size = max(13, round(s.title_size * 0.29))
        # The scales mark shrinks with the type scale so an ultra-compact landscape
        # header stays in proportion instead of forcing 150 units of empty height.
        self.icon = min(ICON_W, round(s.title_size * 2.9))
        text_w = inner_w - self.icon - 34
        self.title_lines = _wrap(
            plan.headline.upper(), text_w, s.title_size, 3, "800",
            uppercase=True, balance=True,
        )
        # Let the measured layout grow for a complete three-line subtitle instead
        # of cutting off the legal holding with an ellipsis on portrait posters.
        self.subtitle_lines = _wrap(
            plan.subtitle or "", text_w, s.subtitle_size, 3, "400"
        )
        self.meta_text = (plan.meta_line or "").strip().upper()

        self.title_h = (
            s.title_size + (len(self.title_lines) - 1) * s.title_lh
            if self.title_lines else 0
        )
        self.subtitle_h = (
            14 + s.subtitle_size + (len(self.subtitle_lines) - 1) * s.subtitle_lh
            if self.subtitle_lines else 0
        )
        self.meta_h = 12 + self.meta_size if self.meta_text else 0
        self.header_h = max(self.icon * 0.94, self.title_h + self.subtitle_h + self.meta_h)

        self.overview_lines = _wrap(
            plan.overview_text, inner_w - 68, s.body_size, s.overview_lines, "400"
        )
        self.overview_h = 84 + max(0, len(self.overview_lines) - 1) * s.body_lh + 32

        self.takeaways = plan.takeaways[: s.takeaway_count]
        self.art = s.art
        self.take_text_w = inner_w - (self.art + 52 if self.art else 0) - 46
        self.take_lines = [
            _wrap(t.description, self.take_text_w, s.take_size, s.takeaway_lines, "500")
            for t in self.takeaways
        ]
        items_h = 0
        for lines in self.take_lines:
            items_h += max(42, len(lines) * s.take_lh) + 16
        items_h = 78 + max(0, items_h - 16) + 10 if self.take_lines else 0
        art_h = 54 + self.art + 10 if self.art else 0
        self.take_h = max(items_h, art_h, 96)

        self.comp_old = plan.comparison_old_items[: s.comp_count]
        self.comp_new = plan.comparison_new_items[: s.comp_count]
        self.has_comparison = bool(s.comp_count and (self.comp_old or self.comp_new))
        self.col_w = (inner_w - 20) // 2
        comp_text_w = self.col_w - 60
        self.comp_old_lines = [
            _wrap(item, comp_text_w, s.comp_size, s.comp_lines, "500")
            for item in self.comp_old
        ]
        self.comp_new_lines = [
            _wrap(item, comp_text_w, s.comp_size, s.comp_lines, "600")
            for item in self.comp_new
        ]
        comp_items = max(len(self.comp_old_lines), len(self.comp_new_lines))
        comp_lines = max(
            sum(len(lines) for lines in self.comp_old_lines),
            sum(len(lines) for lines in self.comp_new_lines),
        )
        self.comp_card_h = (
            88 + (comp_lines - 1) * s.comp_lh + (comp_items - 1) * 14 + 32
            if comp_items else 0
        )
        self.comp_block_h = (
            46 + self.comp_card_h + (36 if plan.comparison_footnote else 0)
            if self.has_comparison else 0
        )

        self.note_lines = _wrap(
            plan.verification_note or "", inner_w - 44, 13, 2, "700"
        )
        self.banner_h = 46 if self.note_lines else 0

        self.total_h = self._total_height()

    def _total_height(self) -> int:
        gaps = 3 if self.has_comparison else 2
        total = (
            PAD
            + self.header_h
            + self.overview_h
            + self.take_h
            + self.comp_block_h
            + gaps * self.spec.gap
        )
        if self.banner_h:
            total += self.spec.gap + self.banner_h
        return total

    def fits(self, canvas_h: float, footer_h: float, has_source: bool) -> bool:
        limit = canvas_h - footer_h - (36 if has_source else 14)
        return self.total_h <= limit

    def slack(self, canvas_h: float, footer_h: float, has_source: bool) -> int:
        limit = canvas_h - footer_h - (36 if has_source else 14)
        return max(0, int(limit - self.total_h))


def _choose_layout(
    plan: InfographicContentPlan,
    canvas_h: float,
    footer_h: float,
    has_source: bool,
    inner_w: int,
) -> _Layout:
    last: Optional[_Layout] = None
    for spec in _SPECS:
        layout = _Layout(plan, spec, inner_w)
        last = layout
        if layout.fits(canvas_h, footer_h, has_source):
            return layout
    logger.warning(
        "Content does not fit %.0f-unit canvas even at the compact spec; using smallest layout.",
        canvas_h,
    )
    assert last is not None
    return last


def _source_and_footer(
    plan: InfographicContentPlan, width: int, dh: float, footer_h: float
) -> str:
    parts: List[str] = []
    if plan.source_url:
        source_y = dh - footer_h - 16
        display_source = (
            plan.source_url if len(plan.source_url) <= 74 else plan.source_url[:71] + "..."
        )
        provenance = (
            f"Source: {plan.publisher + ' - ' if plan.publisher else ''}{display_source}"
        )
        parts.append(
            f'<text x="{PAD}" y="{source_y:.1f}" fill="#8B8E99" font-size="11" font-weight="400" '
            f'font-family="{FONT_STACK}">{escape_xml(provenance)}</text>\n'
        )
        if plan.analysis_source:
            parts.append(
                f'<text x="{DESIGN_WIDTH - PAD}" y="{source_y:.1f}" fill="#A9ABB4" font-size="11" '
                f'font-weight="400" text-anchor="end" font-family="{FONT_STACK}">'
                f'{escape_xml("Analysis: " + plan.analysis_source)}</text>\n'
            )

    footer_y = dh - footer_h
    ratio = footer_h / FOOTER_H
    brand_size = max(15, round(30 * ratio))
    date_size = max(10, round(18 * ratio))
    parts.append(
        f'<g transform="translate(0, {footer_y:.1f})">\n'
        f'  <rect width="{DESIGN_WIDTH}" height="{footer_h:.1f}" fill="{PRIMARY_GOLD}"/>\n'
        f'  <text x="{PAD}" y="{footer_h * 0.64:.1f}" fill="{HEADLINE_DARK}" font-size="{brand_size}" '
        f'font-weight="800" letter-spacing="0.2" font-family="{FONT_STACK}">'
        f'{escape_xml(plan.footer_brand)}</text>\n'
        f'  <text x="{DESIGN_WIDTH - PAD}" y="{footer_h * 0.62:.1f}" fill="#FFF8E8" '
        f'font-size="{date_size}" font-weight="500" text-anchor="end" font-family="{FONT_STACK}">'
        f'{escape_xml(plan.footer_date or "")}</text>\n'
        f'</g>\n'
    )
    return "".join(parts)


def generate_legal_snaps_svg(
    plan: InfographicContentPlan,
    width: int = 800,
    height: int = 1240,
    artwork_base64_data_uri: Optional[str] = None,
) -> str:
    inner_w = DESIGN_WIDTH - (PAD * 2)
    # Uniform design scale: the design space is 1080 wide; canvas height is converted
    # into the same coordinate system so nothing is squashed.
    dh = DESIGN_WIDTH * (height / width)
    footer_h = max(46.0, FOOTER_H * min(1.0, dh / 1350)) if dh < 900 else FOOTER_H
    has_source = bool(plan.source_url)
    layout = _choose_layout(plan, dh, footer_h, has_source, inner_w)
    spec = layout.spec
    slack = layout.slack(dh, footer_h, has_source)
    top_offset = min(56, int(slack * 0.25)) if slack > 40 else 0
    remaining = max(0, slack - top_offset)
    gap_slots = 4 if layout.has_comparison else 3
    extra_gap = spec.gap + min(34, remaining // gap_slots)

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {DESIGN_WIDTH} {dh:.2f}">\n'
        f'<defs>\n'
        f'  <filter id="softShadow" x="-4%" y="-4%" width="108%" height="112%">\n'
        f'    <feDropShadow dx="0" dy="4" stdDeviation="7" flood-color="#2A2E3D" flood-opacity="0.06"/>\n'
        f'  </filter>\n'
        f'</defs>\n'
        f'<rect width="{DESIGN_WIDTH}" height="{dh:.2f}" fill="#FFFFFF"/>\n'
    )

    # ---------------------------------------------------------------- header
    top = PAD + top_offset
    icon_scale = layout.icon / 90
    parts.append(
        f'<g transform="translate({PAD}, {top - 2}) scale({icon_scale:.3f})">'
        f'{render_header_icon(plan.header_icon, PRIMARY_GOLD, DARK_GRAY)}</g>\n'
    )
    text_x = PAD + layout.icon + 34
    title_start_y = top + spec.title_size
    parts.append(
        render_tspan_text(
            layout.title_lines,
            x=text_x,
            start_y=title_start_y,
            line_height=spec.title_lh,
            fill=HEADLINE_DARK,
            font_size=spec.title_size,
            font_weight="800",
            letter_spacing=0.2,
        )
    )
    cursor_y = title_start_y + max(0, len(layout.title_lines) - 1) * spec.title_lh

    if layout.subtitle_lines:
        sub_start = cursor_y + 14 + spec.subtitle_size
        parts.append(
            render_tspan_text(
                layout.subtitle_lines,
                x=text_x,
                start_y=sub_start,
                line_height=spec.subtitle_lh,
                fill=DARK_GRAY,
                font_size=spec.subtitle_size,
                font_weight="400",
            )
        )
        cursor_y = sub_start + (len(layout.subtitle_lines) - 1) * spec.subtitle_lh

    if layout.meta_text:
        meta_start = cursor_y + 12 + layout.meta_size
        parts.append(
            render_tspan_text(
                [layout.meta_text],
                x=text_x,
                start_y=meta_start,
                line_height=layout.meta_size,
                fill=MUTED_TEXT,
                font_size=layout.meta_size,
                font_weight="500",
                letter_spacing=0.8,
            )
        )

    cursor = top + layout.header_h + extra_gap

    # -------------------------------------------------------------- overview
    overview_h = layout.overview_h
    parts.append(
        f'<g transform="translate({PAD}, {cursor:.1f})">\n'
        f'  <rect width="{inner_w}" height="{overview_h}" rx="10" fill="{CARD_BG}" '
        f'stroke="#E7D6AC" stroke-width="1.4" filter="url(#softShadow)"/>\n'
        f'  <rect x="0" y="-20" width="236" height="52" rx="10" fill="{PRIMARY_GOLD}"/>\n'
        f'  <text x="118" y="14" fill="#FFFFFF" font-size="17" font-weight="800" '
        f'letter-spacing="1.8" text-anchor="middle" font-family="{FONT_STACK}">OVERVIEW</text>\n'
    )
    parts.append(
        render_tspan_text(
            layout.overview_lines,
            x=32,
            start_y=84,
            line_height=spec.body_lh,
            fill=DARK_GRAY,
            font_size=spec.body_size,
            font_weight="400",
        )
    )
    parts.append('</g>\n')
    cursor += overview_h + extra_gap

    # ------------------------------------------------------------- takeaways
    take_h = layout.take_h
    parts.append(
        f'<g transform="translate({PAD}, {cursor:.1f})">\n'
        f'  <text x="0" y="26" fill="{HEADLINE_DARK}" font-size="24" font-weight="800" '
        f'letter-spacing="0.9" font-family="{FONT_STACK}">KEY TAKEAWAYS</text>\n'
    )
    item_y = 78
    count = len(layout.takeaways)
    heights = [max(1, len(lines)) * spec.take_lh for lines in layout.take_lines]
    natural_bottom = item_y + sum(heights) + 16 * max(0, count - 1)
    art_bottom = 54 + layout.art if layout.art else take_h - 12
    # Spread the short takeaway lines down the height of the illustration instead of
    # leaving all the slack above the comparison, matching the sample's airy rhythm.
    extra_step = 0
    if count > 1 and art_bottom > natural_bottom:
        extra_step = min(44, (art_bottom - natural_bottom) // (count - 1))
    for takeaway, lines, height in zip(layout.takeaways, layout.take_lines, heights):
        parts.append(
            f'<g transform="translate(2, {item_y - 22}) scale(1.25)">'
            f'{render_takeaway_icon(takeaway.icon_type, PRIMARY_GOLD)}</g>\n'
        )
        parts.append(
            render_tspan_text(
                lines,
                x=46,
                start_y=item_y,
                line_height=spec.take_lh,
                fill=DARK_GRAY,
                font_size=spec.take_size,
                font_weight="500",
            )
        )
        item_y += height + 16 + extra_step

    if layout.art:
        art_x = inner_w - layout.art
        art_y = 54
        if artwork_base64_data_uri:
            parts.append(
                f'<image x="{art_x}" y="{art_y}" width="{layout.art}" '
                f'height="{layout.art}" href="{artwork_base64_data_uri}" '
                f'xlink:href="{artwork_base64_data_uri}" '
                f'preserveAspectRatio="xMidYMid meet"/>\n'
            )
        else:
            year_match = re.search(r"\b(?:19|20)\d{2}\b", plan.footer_date or "")
            illustration_scale = layout.art / 140.0
            parts.append(
                f'<g transform="translate({art_x - 4}, {art_y - 4}) scale({illustration_scale:.3f})">'
                f'{render_editorial_illustration(PRIMARY_GOLD, DARK_GRAY, year_match.group(0) if year_match else None)}'
                f'</g>\n'
            )
    parts.append('</g>\n')
    cursor += take_h + extra_gap

    # ------------------------------------------------------------ comparison
    if layout.has_comparison:
        parts.append(
            f'<text x="{PAD}" y="{cursor + 30:.1f}" fill="{HEADLINE_DARK}" font-size="25" '
            f'font-weight="800" letter-spacing="0.4" font-family="{FONT_STACK}">'
            f'{escape_xml(plan.comparison_title or "Before and After")}</text>\n'
        )
        cursor += 46
        col_w = layout.col_w
        col2_x = PAD + col_w + 20
        card_h = layout.comp_card_h
        header_y = 50

        # Left column
        parts.append(
            f'<g transform="translate({PAD}, {cursor:.1f})">\n'
            f'  <rect width="{col_w}" height="{card_h}" rx="10" fill="{CARD_BG}" '
            f'stroke="{CARD_BORDER}" stroke-width="1.2" filter="url(#softShadow)"/>\n'
            f'  <text x="{col_w / 2:.1f}" y="{header_y}" fill="{DARK_GRAY}" font-size="18" '
            f'font-weight="800" letter-spacing="1.4" text-anchor="middle" '
            f'font-family="{FONT_STACK}">{escape_xml(plan.comparison_old_title)}</text>\n'
        )
        item_y = 88
        for lines in layout.comp_old_lines:
            parts.append(
                f'<circle cx="30" cy="{item_y - 6}" r="3.4" fill="{PRIMARY_GOLD}"/>\n'
            )
            parts.append(
                render_tspan_text(
                    lines,
                    x=46,
                    start_y=item_y,
                    line_height=spec.comp_lh,
                    fill=DARK_GRAY,
                    font_size=spec.comp_size,
                    font_weight="500",
                )
            )
            item_y += len(lines) * spec.comp_lh + 14
        parts.append('</g>\n')

        # Right column
        parts.append(
            f'<g transform="translate({col2_x}, {cursor:.1f})">\n'
            f'  <rect width="{col_w}" height="{card_h}" rx="10" fill="{PRIMARY_GOLD}"/>\n'
            f'  <text x="{col_w / 2:.1f}" y="{header_y}" fill="{HEADLINE_DARK}" font-size="18" '
            f'font-weight="800" letter-spacing="1.4" text-anchor="middle" '
            f'font-family="{FONT_STACK}">{escape_xml(plan.comparison_new_title)}</text>\n'
        )
        item_y = 88
        for lines in layout.comp_new_lines:
            parts.append(
                f'<circle cx="30" cy="{item_y - 6}" r="3.4" fill="{HEADLINE_DARK}"/>\n'
            )
            parts.append(
                render_tspan_text(
                    lines,
                    x=46,
                    start_y=item_y,
                    line_height=spec.comp_lh,
                    fill="#252A39",
                    font_size=spec.comp_size,
                    font_weight="600",
                )
            )
            item_y += len(lines) * spec.comp_lh + 14
        parts.append('</g>\n')

        cursor += card_h

        if plan.comparison_footnote:
            parts.append(
                f'<text x="{DESIGN_WIDTH / 2:.1f}" y="{cursor + 26:.1f}" fill="#9A9CA6" '
                f'font-size="13" font-weight="400" text-anchor="middle" '
                f'font-family="{FONT_STACK}">{escape_xml(plan.comparison_footnote)}</text>\n'
            )
            cursor += 36
        cursor += extra_gap

    # --------------------------------------------------- verification banner
    if layout.note_lines:
        parts.append(
            f'<g transform="translate({PAD}, {cursor:.1f})">\n'
            f'  <rect width="{inner_w}" height="{layout.banner_h}" rx="10" fill="{GOLD_SOFT}" '
            f'stroke="{PRIMARY_GOLD}" stroke-width="1.4"/>\n'
        )
        parts.append(
            render_tspan_text(
                [f"! {layout.note_lines[0]}"] + layout.note_lines[1:],
                x=20,
                start_y=21,
                line_height=18,
                fill="#8A5A00",
                font_size=13,
                font_weight="700",
            )
        )
        parts.append('</g>\n')

    parts.append(_source_and_footer(plan, width, dh, footer_h))
    parts.append('</svg>')
    return "".join(parts)
