import re
import logging
from typing import List, Tuple
from app.schemas import LegalRecord, ClaimValidation, ValidationSummary

logger = logging.getLogger(__name__)

def normalize_text(text: str) -> str:
    """Normalize whitespace and punctuation for fuzzy matching."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()

def check_text_in_source(claim: str, source_text: str) -> Tuple[bool, float, str]:
    """
    Check if a claim or its constituent entities appear in the source text.
    Returns (verified, confidence_score, matching_snippet).
    """
    clean_claim = claim.strip()
    if not clean_claim:
        return True, 1.0, ""

    # Direct substring search
    if clean_claim.lower() in source_text.lower():
        idx = source_text.lower().find(clean_claim.lower())
        snippet = source_text[max(0, idx - 40): min(len(source_text), idx + len(clean_claim) + 40)]
        return True, 1.0, snippet.strip()

    # Normalized entity search
    norm_source = normalize_text(source_text)
    norm_claim = normalize_text(clean_claim)
    if norm_claim in norm_source:
        return True, 0.95, "Found via normalized match"

    # Token overlap heuristic (for long sentences)
    claim_words = [w for w in norm_claim.split() if len(w) > 3]
    if not claim_words:
        return True, 0.8, ""

    matched_words = [w for w in claim_words if w in norm_source]
    overlap_ratio = len(matched_words) / len(claim_words)

    if overlap_ratio >= 0.75:
        return True, round(overlap_ratio, 2), f"{len(matched_words)}/{len(claim_words)} key terms verified in source"
    elif overlap_ratio >= 0.45:
        return False, round(overlap_ratio, 2), f"Partial term overlap ({len(matched_words)}/{len(claim_words)} terms). Needs human verification."
    else:
        return False, 0.2, "Claim terms absent from source document."

def validate_legal_record(record: LegalRecord, source_text: str) -> ValidationSummary:
    """
    Separately audits and verifies every critical legal claim against source evidence.
    Verifies holdings vs party arguments, citations, dates, quotations, and statutory provisions.
    """
    claims: List[ClaimValidation] = []
    warnings: List[str] = []
    
    # 1. Validate Court & Case Name
    if record.case_name:
        verified, conf, snippet = check_text_in_source(record.case_name, source_text)
        claims.append(ClaimValidation(
            claim_id="case_name",
            claim_text=f"Case Title: {record.case_name}",
            claim_type="case_identity",
            verified=verified,
            source_reference=snippet,
            confidence_score=conf,
            warning_notes=None if verified else "Case title not directly found in source text."
        ))
        if not verified:
            warnings.append(f"Case name '{record.case_name}' could not be verified from the source text.")

    # 2. Validate Citation
    if record.citation:
        verified, conf, snippet = check_text_in_source(record.citation, source_text)
        claims.append(ClaimValidation(
            claim_id="citation",
            claim_text=f"Citation: {record.citation}",
            claim_type="statutory_citation",
            verified=verified,
            source_reference=snippet,
            confidence_score=conf,
            warning_notes=None if verified else "Legal citation not confirmed in source document."
        ))
        if not verified:
            warnings.append(f"Citation '{record.citation}' could not be verified in the retrieved source text.")

    # 3. Validate Judgment Date
    if record.judgment_date:
        verified, conf, snippet = check_text_in_source(record.judgment_date, source_text)
        claims.append(ClaimValidation(
            claim_id="judgment_date",
            claim_text=f"Judgment Date: {record.judgment_date}",
            claim_type="factual_date",
            verified=verified,
            source_reference=snippet,
            confidence_score=conf,
            warning_notes=None if verified else "Date not explicitly verified in source text."
        ))

    # 4. CRITICAL: Validate Operative Holding (distinguishing from party arguments)
    if record.holding_or_operative_order:
        verified, conf, snippet = check_text_in_source(record.holding_or_operative_order, source_text)
        
        # Check if holding accidentally contains party argument markers
        argument_markers = ["petitioner contended", "appellant argued", "respondent submitted", "counsel urged"]
        has_arg_marker = any(m in record.holding_or_operative_order.lower() for m in argument_markers)
        
        warning_msg = None
        if has_arg_marker:
            verified = False
            warning_msg = "WARNING: Extracted holding contains party argument language instead of authoritative court ruling."
            warnings.append(warning_msg)
        elif not verified:
            warning_msg = "Operative holding has low textual overlap with source document."
            warnings.append("Critical claim warning: The court's holding requires manual legal verification against primary judgment.")

        claims.append(ClaimValidation(
            claim_id="holding",
            claim_text=f"Court Holding: {record.holding_or_operative_order[:180]}...",
            claim_type="holding",
            verified=verified,
            source_reference=snippet,
            confidence_score=conf if not has_arg_marker else 0.3,
            warning_notes=warning_msg
        ))

    # 5. Validate Statutory Provisions
    for i, statute in enumerate(record.relevant_statutes):
        verified, conf, snippet = check_text_in_source(statute, source_text)
        claims.append(ClaimValidation(
            claim_id=f"statute_{i}",
            claim_text=f"Statute: {statute}",
            claim_type="statute",
            verified=verified,
            source_reference=snippet,
            confidence_score=conf,
            warning_notes=None if verified else "Statutory section not found in source text."
        ))

    # 6. Validate Exact Quotations
    for i, quote in enumerate(record.exact_quotations):
        verified, conf, snippet = check_text_in_source(quote, source_text)
        claims.append(ClaimValidation(
            claim_id=f"quote_{i}",
            claim_text=f'"{quote[:120]}..."',
            claim_type="quotation",
            verified=verified,
            source_reference=snippet,
            confidence_score=conf,
            warning_notes=None if verified else "Direct quotation mismatch in source text."
        ))
        if not verified:
            warnings.append(f"Quotation #{i+1} was not found verbatim in the source text.")

    total = len(claims)
    verified_count = sum(1 for c in claims if c.verified)
    unverified_count = total - verified_count
    
    # Check if holding is unverified (critical)
    holding_claim = next((c for c in claims if c.claim_id == "holding"), None)
    has_critical_unverified = bool(holding_claim and not holding_claim.verified)

    return ValidationSummary(
        total_claims=total,
        verified_claims=verified_count,
        unverified_claims=unverified_count,
        has_critical_unverified=has_critical_unverified,
        warnings=warnings,
        claims=claims
    )
