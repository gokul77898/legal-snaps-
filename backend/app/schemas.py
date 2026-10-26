from typing import List, Literal, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator

class JobStage(str, Enum):
    IDLE = "idle"
    SEARCHING = "searching"                 # 1. Searching for the article
    RETRIEVING = "retrieving"               # 2. Retrieving the source
    EXTRACTING = "extracting"               # 3. Extracting text
    ANALYSING = "analysing"                 # 4. Analysing legal information
    VALIDATING = "validating"               # 5. Validating legal claims
    DESIGNING = "designing"                 # 6. Designing the infographic
    GENERATING_ARTWORK = "generating_art"   # 7. Generating optional illustrations
    RENDERING_IMAGE = "rendering_image"     # 8. Rendering the final image
    CHECKING_QUALITY = "checking_quality"   # 9. Running quality checks
    SAVING = "saving"                       # 10. Saving the output
    COMPLETED = "completed"
    FAILED = "failed"

STAGE_NAMES = {
    1: "Searching for the article",
    2: "Retrieving the source",
    3: "Extracting text",
    4: "Analysing legal information",
    5: "Validating legal claims",
    6: "Designing the infographic",
    7: "Generating optional illustrations",
    8: "Rendering the final image",
    9: "Running quality checks",
    10: "Saving the output",
}

class InfographicCreateRequest(BaseModel):
    article_name: Optional[str] = Field(None, description="Article name or legal topic")
    article_url: Optional[str] = Field(None, description="Direct URL to article or judgment")
    pdf_url: Optional[str] = Field(None, description="Direct URL to PDF")
    language: str = Field("en", description="Output language (en, etc.)")
    output_format: str = Field("both", description="svg, png, or both")
    enable_image_generation: bool = Field(True, description="Enable optional artwork for this job")
    layout_family: Optional[str] = Field(
        None,
        description="Pin the composition instead of letting the art director choose one",
    )
    width: int = Field(800, ge=600, le=3840, description="Output image width")
    height: int = Field(1240, ge=600, le=3840, description="Output image height")

    @field_validator("article_name", "article_url", "pdf_url")
    @classmethod
    def strip_whitespace(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    def validate_input_present(self):
        if not self.article_name and not self.article_url and not self.pdf_url:
            raise ValueError("You must supply an article name/topic, an article URL, or a PDF URL.")

class SourceCandidate(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = None
    publisher: Optional[str] = None
    publication_date: Optional[str] = None
    credibility_score: float = 0.5
    is_primary_source: bool = False
    relevance_score: float = 0.0

class SourceMetadata(BaseModel):
    title: str
    url: Optional[str] = None
    publisher: Optional[str] = None
    retrieval_time: str
    extraction_method: str = "html_direct"
    text_length: int = 0
    status: str = "success"
    warnings: List[str] = []
    word_count: int = 0
    boilerplate_lines_removed: int = 0

class ExtractionResult(BaseModel):
    """Output of the stage-3 sanitising/structuring step. Feeds analysis and validation."""
    text: str
    section_headings: List[str] = Field(default_factory=list)
    line_count: int = 0
    char_count: int = 0
    boilerplate_lines_removed: int = 0
    warnings: List[str] = Field(default_factory=list)

class LegalRecord(BaseModel):
    article_title: str
    court_or_tribunal: Optional[str] = None
    case_name: Optional[str] = None
    citation: Optional[str] = None
    case_number: Optional[str] = None
    bench_composition: List[str] = Field(default_factory=list)
    judgment_date: Optional[str] = None
    relevant_statutes: List[str] = Field(default_factory=list)
    material_facts: List[str] = Field(default_factory=list)
    procedural_history: Optional[str] = None
    questions_or_issues: List[str] = Field(default_factory=list)
    arguments_parties: List[str] = Field(default_factory=list)
    legal_reasoning: List[str] = Field(default_factory=list)
    holding_or_operative_order: str
    precedents_cited: List[str] = Field(default_factory=list)
    exact_quotations: List[str] = Field(default_factory=list)
    practical_implications: List[str] = Field(default_factory=list)
    supporting_source_passages: List[str] = Field(default_factory=list)
    unverified_fields: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    is_court_judgment: bool = False
    legislation_or_article_type: Optional[str] = None
    analysis_source: Optional[str] = None

class ClaimValidation(BaseModel):
    claim_id: str
    claim_text: str
    claim_type: str
    verified: bool
    source_reference: Optional[str] = None
    confidence_score: float = 1.0
    warning_notes: Optional[str] = None

class ValidationSummary(BaseModel):
    total_claims: int = 0
    verified_claims: int = 0
    unverified_claims: int = 0
    has_critical_unverified: bool = False
    warnings: List[str] = Field(default_factory=list)
    claims: List[ClaimValidation] = Field(default_factory=list)


class LayoutFamily(str, Enum):
    """Structural poster families. The family changes geometry, not just colours."""

    LANDMARK_COVER = "landmark_cover"
    SPLIT_COMPARISON = "split_comparison"
    TIMELINE = "timeline"
    DECISION_TREE = "decision_tree"
    STATUTORY_MAP = "statutory_map"
    CHART_LED = "chart_led"
    PROCESS_FLOW = "process_flow"
    ARGUMENT_OUTCOME = "argument_outcome"
    BRIEFING_SHEET = "briefing_sheet"
    HYBRID = "hybrid"


class BriefSourceField(str, Enum):
    """Validated record fields a brief may cite. Text is resolved server-side."""

    HOLDING = "holding_or_operative_order"
    FACTS = "material_facts"
    ISSUES = "questions_or_issues"
    REASONING = "legal_reasoning"
    STATUTES = "relevant_statutes"
    IMPLICATIONS = "practical_implications"
    PRECEDENTS = "precedents_cited"
    QUOTATIONS = "exact_quotations"
    PROCEDURAL = "procedural_history"
    ARGUMENTS = "arguments_parties"
    UNCERTAINTIES = "uncertainties"
    ARTICLE_TITLE = "article_title"
    CASE_NAME = "case_name"
    CITATION = "citation"
    COURT = "court_or_tribunal"
    JUDGMENT_DATE = "judgment_date"


class DesignSectionKind(str, Enum):
    CONTEXT = "context"
    FACTS = "facts"
    ISSUES = "issues"
    REASONING = "reasoning"
    STATUTES = "statutes"
    HOLDING = "holding"
    IMPLICATIONS = "implications"
    TIMELINE = "timeline"
    COMPARISON = "comparison"
    PROCESS = "process"
    ARGUMENT = "argument"
    OUTCOME = "outcome"


class BriefItem(BaseModel):
    """A pointer into the validated LegalRecord; never free-form legal text."""

    source: BriefSourceField
    index: int = Field(0, ge=0, le=40)


class DesignSection(BaseModel):
    heading: str = Field(..., min_length=1, max_length=52)
    kind: DesignSectionKind
    items: List[BriefItem] = Field(..., min_length=1, max_length=4)
    emphasis: Literal["primary", "secondary", "quiet"] = "secondary"

    @field_validator("heading")
    @classmethod
    def clean_heading(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("heading cannot be blank")
        return cleaned


class ChartDatum(BaseModel):
    label: str = Field(..., min_length=1, max_length=28)
    value_text: str = Field(
        ..., min_length=1, max_length=24,
        description="Exact figure and unit as written in the source, e.g. '3 years' or '60 days'.",
    )

    @field_validator("label", "value_text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.split())


class ChartSpec(BaseModel):
    """Bar chart whose values must appear verbatim in the validated record text."""

    title: str = Field(..., min_length=1, max_length=64)
    unit: Optional[str] = Field(None, max_length=16)
    data: List[ChartDatum] = Field(..., min_length=2, max_length=5)


class DesignBrief(BaseModel):
    """
    Article-specific art direction, generated from the validated record before rendering.

    The model chooses a structure and points at record fields; it cannot invent poster
    text. A resolver turns these pointers into verbatim strings, so a design brief can
    never smuggle a sample article into an infographic.
    """

    layout_family: LayoutFamily
    secondary_family: Optional[LayoutFamily] = None
    rationale: str = Field(..., min_length=10, max_length=500)
    # Editorial metadata requested by the brief contract. These describe the article for the
    # art direction and artwork prompt; they are never rendered as legal copy, so a model
    # paraphrase here cannot smuggle invented facts onto the poster.
    article_title: Optional[str] = Field(None, max_length=240)
    content_type: Optional[str] = Field(None, max_length=120)
    central_issue: Optional[str] = Field(None, max_length=400)
    main_takeaway: Optional[str] = Field(None, max_length=400)
    diagram_type: Optional[str] = Field(None, max_length=120)
    illustration_concept: Optional[str] = Field(None, max_length=400)
    visual_emphasis: Optional[str] = Field(None, max_length=240)
    source_attribution: Optional[str] = Field(None, max_length=240)
    uncertainties: List[str] = Field(default_factory=list, max_length=6)
    headline_source: Literal["case_name", "article_title"] = "case_name"
    headline_scale: Literal["compact", "standard", "dramatic"] = "standard"
    headline_alignment: Literal["left", "center"] = "left"
    hero_visual: Literal[
        "none", "scales", "gavel", "timeline", "map", "tree", "chart", "flow", "columns"
    ] = "none"
    sections: List[DesignSection] = Field(..., min_length=2, max_length=5)
    flow_direction: Literal["vertical", "horizontal", "stepped", "radial"] = "vertical"
    whitespace: Literal["tight", "balanced", "airy"] = "balanced"
    accent_strategy: Literal["gold_rules", "gold_panels", "dark_panels", "outline"] = "gold_rules"
    icon_motifs: List[str] = Field(default_factory=list, max_length=4)
    chart: Optional[ChartSpec] = None
    design_notes: Optional[str] = Field(None, max_length=400)
    generated_by: Optional[str] = None

    @field_validator(
        "rationale",
        "design_notes",
        "article_title",
        "content_type",
        "central_issue",
        "main_takeaway",
        "diagram_type",
        "illustration_concept",
        "visual_emphasis",
        "source_attribution",
    )
    @classmethod
    def clean_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("uncertainties")
    @classmethod
    def clean_uncertainties(cls, values: List[str]) -> List[str]:
        return [" ".join(item.split()) for item in values if item and item.strip()][:6]

    @model_validator(mode="after")
    def validate_structure(self):
        if self.layout_family == LayoutFamily.HYBRID:
            if self.secondary_family is None or self.secondary_family == LayoutFamily.HYBRID:
                raise ValueError("hybrid layouts require a different secondary_family")
        if self.layout_family == LayoutFamily.CHART_LED and self.chart is None:
            raise ValueError("chart_led layouts require chart data taken from the source")
        if self.chart is not None and self.layout_family != LayoutFamily.CHART_LED:
            # A chart is allowed as supporting evidence only when it is the lead structure;
            # otherwise the renderer would have to invent space for it.
            self.chart = None
        return self

    @property
    def layout_key(self) -> str:
        """Coarse structure key used to stop consecutive articles reusing one composition.

        It ignores the wording and the per-section item counts on purpose: family, headline
        scale and section count are what make two posters read as the same design at a
        glance, whatever the legal text inside them says.
        """
        return "/".join(
            [
                self.layout_family.value,
                self.headline_scale,
                str(len(self.sections)),
            ]
        )

    @property
    def layout_signature(self) -> str:
        """Stable structural fingerprint used by QC and regression tests."""
        section_sig = "|".join(
            f"{section.kind.value}:{len(section.items)}" for section in self.sections
        )
        return (
            f"{self.layout_family.value}/{self.flow_direction}/{self.headline_scale}/"
            f"{len(self.sections)}/{section_sig}"
        )


class TakeawayItem(BaseModel):
    icon_type: str = "gavel"  # "gavel", "parliament", "book", "prohibited", "clock", "court"
    title: str = ""
    description: str

class InfographicContentPlan(BaseModel):
    """
    Layout data for one job. Every field with legal meaning must be derived from that
    job's LegalRecord — the defaults are intentionally content-free so an unset field
    can never leak another article's text into an infographic.
    """
    headline: str
    subtitle: Optional[str] = None
    meta_line: Optional[str] = None
    header_icon: str = "gavel"  # "gavel", "scales", "court"
    overview_text: str
    takeaways: List[TakeawayItem] = Field(default_factory=list)
    comparison_title: str = ""
    comparison_old_title: str = ""
    comparison_old_items: List[str] = Field(default_factory=list)
    comparison_new_title: str = ""
    comparison_new_items: List[str] = Field(default_factory=list)
    comparison_footnote: Optional[str] = None
    footer_brand: str = "Legal Snaps"
    footer_date: Optional[str] = None
    source_url: Optional[str] = None
    publisher: Optional[str] = None
    verification_note: Optional[str] = None
    artwork_subject: Optional[str] = None
    analysis_source: Optional[str] = None
    design_brief: Optional[DesignBrief] = None

class JobResponse(BaseModel):
    job_id: str
    status: JobStage
    current_stage: int = 0
    current_stage_name: str = ""
    progress_percent: int = 0
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
    article_name: Optional[str] = None
    article_url: Optional[str] = None
    output_format: str = "both"
    enable_image_generation: bool = False
    source_metadata: Optional[SourceMetadata] = None
    legal_record: Optional[LegalRecord] = None
    validation_summary: Optional[ValidationSummary] = None
    design_brief: Optional[DesignBrief] = None
    content_plan: Optional[InfographicContentPlan] = None
    svg_filename: Optional[str] = None
    png_filename: Optional[str] = None
    artwork_filename: Optional[str] = None
    has_svg: bool = False
    has_png: bool = False
    artwork_generated: bool = False
    analysis_source: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)

class JobListItem(BaseModel):
    job_id: str
    status: JobStage
    article_name: Optional[str] = None
    created_at: str
    updated_at: str
    has_svg: bool = False
    has_png: bool = False
    headline: Optional[str] = None
    court_case_info: Optional[str] = None
    validation_verified_count: int = 0
    validation_total_count: int = 0

class HealthCheckResponse(BaseModel):
    status: str
    app_name: str
    ai_provider: str = "Hugging Face Inference Providers"
    provider_configured: bool
    analysis_model: str
    image_model: str
    search_provider: str
    ocr_provider: str
    renderer_available: bool
    storage_writable: bool
    timestamp: str
    provider_error: Optional[str] = None
