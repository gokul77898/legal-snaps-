"""Resolve an AI design brief into verbatim, validated record text.

The model never writes poster copy. It selects a layout and points at fields of the
already-validated LegalRecord. This module turns those pointers into strings (or raises
DesignBriefError, which the pipeline surfaces as a failed job), so a malformed or
hallucinated brief can never be rendered as if it were legal content.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.schemas import (
    BriefItem,
    BriefSourceField,
    ChartSpec,
    DesignBrief,
    LegalRecord,
    LayoutFamily,
)


class DesignBriefError(ValueError):
    """The design brief is structurally valid but points outside the record."""


_SCALAR_FIELDS = {
    BriefSourceField.HOLDING,
    BriefSourceField.PROCEDURAL,
    BriefSourceField.ARTICLE_TITLE,
    BriefSourceField.CASE_NAME,
    BriefSourceField.CITATION,
    BriefSourceField.COURT,
    BriefSourceField.JUDGMENT_DATE,
}

_LIST_FIELDS = {
    BriefSourceField.FACTS,
    BriefSourceField.ISSUES,
    BriefSourceField.REASONING,
    BriefSourceField.STATUTES,
    BriefSourceField.IMPLICATIONS,
    BriefSourceField.PRECEDENTS,
    BriefSourceField.QUOTATIONS,
    BriefSourceField.ARGUMENTS,
    BriefSourceField.UNCERTAINTIES,
}


@dataclass(frozen=True)
class ResolvedItem:
    text: str
    source: BriefSourceField
    index: int


@dataclass(frozen=True)
class ResolvedSection:
    heading: str
    kind: str
    emphasis: str
    items: List[ResolvedItem]

    @property
    def primary_text(self) -> str:
        return self.items[0].text if self.items else ""


@dataclass(frozen=True)
class ResolvedChart:
    title: str
    unit: Optional[str]
    data: List[tuple]  # (label, value_text, numeric_value)


@dataclass(frozen=True)
class ResolvedBrief:
    family: LayoutFamily
    secondary_family: Optional[LayoutFamily]
    headline: str
    headline_scale: str
    headline_alignment: str
    hero_visual: str
    sections: List[ResolvedSection]
    flow_direction: str
    whitespace: str
    accent_strategy: str
    icon_motifs: List[str]
    chart: Optional[ResolvedChart]
    rationale: str
    design_notes: Optional[str]
    generated_by: Optional[str] = field(default=None)

    @property
    def signature(self) -> str:
        section_sig = "|".join(
            f"{section.kind}:{len(section.items)}" for section in self.sections
        )
        return (
            f"{self.family.value}/{self.flow_direction}/{self.headline_scale}/"
            f"{len(self.sections)}/{section_sig}"
        )


def _normalise(text: str) -> str:
    return " ".join((text or "").split())


def record_text(record: LegalRecord) -> str:
    """All validated record values, used only for verbatim checks (never displayed)."""
    parts: List[str] = []
    for value in record.model_dump().values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
    return _normalise(" \n ".join(parts))


def _resolve_item(item: BriefItem, record: LegalRecord) -> ResolvedItem:
    value = getattr(record, item.source.value, None)
    if item.source in _SCALAR_FIELDS:
        if not isinstance(value, str) or not value.strip():
            raise DesignBriefError(
                f"Brief cites '{item.source.value}', but this record has no value for it."
            )
        return ResolvedItem(_normalise(value), item.source, 0)

    if item.source in _LIST_FIELDS:
        values = value if isinstance(value, list) else []
        if item.index >= len(values):
            raise DesignBriefError(
                f"Brief cites '{item.source.value}' index {item.index}, but the record has "
                f"{len(values)} item(s) there."
            )
        text = _normalise(str(values[item.index]))
        if not text:
            raise DesignBriefError(
                f"Brief cites an empty '{item.source.value}' item at index {item.index}."
            )
        return ResolvedItem(text, item.source, item.index)

    raise DesignBriefError(f"Unsupported brief source '{item.source.value}'.")


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_ALLOWED_UNITS = {"", "%", "years", "year", "days", "day", "months", "month", "weeks", "week", "hours", "hour"}


def _resolve_chart(chart: ChartSpec, record: LegalRecord) -> ResolvedChart:
    source_text = record_text(record).lower()
    data = []
    for datum in chart.data:
        value_text = _normalise(datum.value_text)
        if value_text.lower() not in source_text:
            raise DesignBriefError(
                f"Chart value '{value_text}' is not present verbatim in the validated record."
            )
        match = _NUMBER.search(value_text)
        if not match:
            raise DesignBriefError(
                f"Chart value '{value_text}' has no numeric value the renderer can plot."
            )
        numeric = float(match.group(0).replace(",", ""))
        if numeric <= 0:
            raise DesignBriefError(f"Chart value '{value_text}' must be greater than zero.")
        data.append((_normalise(datum.label), value_text, numeric))

    if len({round(item[2], 4) for item in data}) < 2:
        raise DesignBriefError(
            "Chart data needs at least two different numeric values to be a meaningful chart."
        )
    units = {" ".join(_normalise(item[1]).split()[1:]).lower() for item in data}
    if len(units) > 1:
        raise DesignBriefError(
            "Chart values mix units ("
            + ", ".join(sorted(u or "no unit" for u in units))
            + "); bars are only comparable when every value uses the same unit."
        )
    if chart.unit and chart.unit.strip().lower() not in _ALLOWED_UNITS:
        raise DesignBriefError(
            f"Chart unit '{chart.unit}' is not a recognised unit; leave it null instead."
        )
    return ResolvedChart(
        title=_normalise(chart.title),
        unit=_normalise(chart.unit) if chart.unit else None,
        data=data,
    )


def resolve_design_brief(brief: DesignBrief, record: LegalRecord) -> ResolvedBrief:
    """Resolve every pointer and reject anything the record cannot support."""
    if brief.headline_source == "article_title":
        headline = record.article_title
    else:
        headline = record.case_name or record.article_title
    headline = _normalise(headline)
    if not headline:
        raise DesignBriefError("The record has no case name or article title to use as a headline.")

    sections: List[ResolvedSection] = []
    headings_seen: List[str] = []
    for section in brief.sections:
        items = [_resolve_item(item, record) for item in section.items]
        if not items:
            raise DesignBriefError(f"Section '{section.heading}' has no resolvable items.")
        headings = _normalise(section.heading)
        if headings.lower() in {"overview", "key takeaways", "summary"}:
            # These are the old fixed template labels; allowing them lets the model fall
            # back into one generic poster structure.
            raise DesignBriefError(
                f"Section heading '{headings}' is a generic template label; name the actual "
                "legal idea instead."
            )
        if headings.lower() in {seen.lower() for seen in headings_seen}:
            # Two panels titled "LEGAL REASONING" read as a copy-paste error on the poster.
            raise DesignBriefError(
                f"Section heading '{headings}' is used twice; give each section its own "
                "label for the legal idea it carries."
            )
        headings_seen.append(headings)
        sections.append(
            ResolvedSection(
                heading=headings,
                kind=section.kind.value,
                emphasis=section.emphasis,
                items=items,
            )
        )

    chart = _resolve_chart(brief.chart, record) if brief.chart else None
    if brief.layout_family == LayoutFamily.CHART_LED and chart is None:
        raise DesignBriefError("chart_led layouts require a chart built from record values.")

    return ResolvedBrief(
        family=brief.layout_family,
        secondary_family=brief.secondary_family,
        headline=headline,
        headline_scale=brief.headline_scale,
        headline_alignment=brief.headline_alignment,
        hero_visual=brief.hero_visual,
        sections=sections,
        flow_direction=brief.flow_direction,
        whitespace=brief.whitespace,
        accent_strategy=brief.accent_strategy,
        icon_motifs=list(brief.icon_motifs),
        chart=chart,
        rationale=brief.rationale,
        design_notes=brief.design_notes,
        generated_by=brief.generated_by,
    )


def record_value_map(record: LegalRecord) -> Dict[str, object]:
    """Compact field map used by the prompt and by deterministic test briefs."""
    return {
        BriefSourceField.HOLDING.value: record.holding_or_operative_order,
        BriefSourceField.FACTS.value: list(record.material_facts),
        BriefSourceField.ISSUES.value: list(record.questions_or_issues),
        BriefSourceField.REASONING.value: list(record.legal_reasoning),
        BriefSourceField.STATUTES.value: list(record.relevant_statutes),
        BriefSourceField.IMPLICATIONS.value: list(record.practical_implications),
        BriefSourceField.PRECEDENTS.value: list(record.precedents_cited),
        BriefSourceField.QUOTATIONS.value: list(record.exact_quotations),
        BriefSourceField.PROCEDURAL.value: record.procedural_history,
        BriefSourceField.ARGUMENTS.value: list(record.arguments_parties),
        BriefSourceField.UNCERTAINTIES.value: list(record.uncertainties),
        BriefSourceField.ARTICLE_TITLE.value: record.article_title,
        BriefSourceField.CASE_NAME.value: record.case_name,
        BriefSourceField.CITATION.value: record.citation,
        BriefSourceField.COURT.value: record.court_or_tribunal,
        BriefSourceField.JUDGMENT_DATE.value: record.judgment_date,
    }


def available_sources(record: LegalRecord) -> Dict[str, int]:
    """Pointers the model may realistically use, with their usable item counts."""
    counts: Dict[str, int] = {}
    for name, value in record_value_map(record).items():
        if isinstance(value, list):
            if value:
                counts[name] = len(value)
        elif isinstance(value, str) and value.strip():
            counts[name] = 1
    return counts
