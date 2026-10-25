from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator

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
    enable_image_generation: bool = Field(True, description="Enable optional FLUX artwork for this job")
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
