export type JobStage =
  | 'idle'
  | 'searching'
  | 'retrieving'
  | 'extracting'
  | 'analysing'
  | 'validating'
  | 'designing'
  | 'generating_art'
  | 'rendering_image'
  | 'checking_quality'
  | 'saving'
  | 'completed'
  | 'failed';

export interface SourceCandidate {
  title: string;
  url: string;
  snippet?: string;
  publisher?: string;
  publication_date?: string;
  credibility_score: number;
  is_primary_source: boolean;
}

export interface SourceMetadata {
  title: string;
  url?: string;
  publisher?: string;
  retrieval_time: string;
  extraction_method: string;
  text_length: number;
  status: string;
  warnings: string[];
  word_count: number;
  boilerplate_lines_removed: number;
}

export interface LegalRecord {
  article_title: string;
  court_or_tribunal?: string;
  case_name?: string;
  citation?: string;
  case_number?: string;
  bench_composition: string[];
  judgment_date?: string;
  relevant_statutes: string[];
  material_facts: string[];
  procedural_history?: string;
  questions_or_issues: string[];
  arguments_parties: string[];
  legal_reasoning: string[];
  holding_or_operative_order: string;
  precedents_cited: string[];
  exact_quotations: string[];
  practical_implications: string[];
  supporting_source_passages: string[];
  unverified_fields: string[];
  uncertainties: string[];
  is_court_judgment: boolean;
  legislation_or_article_type?: string;
  analysis_source?: string;
}

export interface ClaimValidation {
  claim_id: string;
  claim_text: string;
  claim_type: string;
  verified: boolean;
  source_reference?: string;
  confidence_score: number;
  warning_notes?: string;
}

export interface ValidationSummary {
  total_claims: number;
  verified_claims: number;
  unverified_claims: number;
  has_critical_unverified: boolean;
  warnings: string[];
  claims: ClaimValidation[];
}

export interface TakeawayItem {
  icon_type: string;
  title: string;
  description: string;
}

export interface InfographicContentPlan {
  headline: string;
  subtitle?: string;
  header_icon: string;
  overview_text: string;
  takeaways: TakeawayItem[];
  comparison_title: string;
  comparison_old_title: string;
  comparison_old_items: string[];
  comparison_new_title: string;
  comparison_new_items: string[];
  comparison_footnote?: string;
  footer_brand: string;
  footer_date?: string;
  source_url?: string;
  publisher?: string;
  verification_note?: string;
  artwork_subject?: string;
  analysis_source?: string;
}

export interface JobResponse {
  job_id: string;
  status: JobStage;
  current_stage: number;
  current_stage_name: string;
  progress_percent: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
  article_name?: string;
  article_url?: string;
  output_format: string;
  enable_image_generation: boolean;
  source_metadata?: SourceMetadata;
  legal_record?: LegalRecord;
  validation_summary?: ValidationSummary;
  content_plan?: InfographicContentPlan;
  svg_filename?: string;
  png_filename?: string;
  artwork_filename?: string;
  has_svg: boolean;
  has_png: boolean;
  artwork_generated: boolean;
  analysis_source?: string;
  warnings: string[];
  logs: string[];
}

export interface JobListItem {
  job_id: string;
  status: JobStage;
  article_name?: string;
  created_at: string;
  updated_at: string;
  has_svg: boolean;
  has_png: boolean;
  headline?: string;
  court_case_info?: string;
  validation_verified_count: number;
  validation_total_count: number;
}

export interface HealthStatus {
  status: string;
  app_name: string;
  ai_provider: string;
  provider_configured: boolean;
  analysis_model: string;
  image_model: string;
  search_provider: string;
  ocr_provider: string;
  renderer_available: boolean;
  storage_writable: boolean;
  timestamp: string;
}
