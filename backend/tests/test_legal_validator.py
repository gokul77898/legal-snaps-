import pytest
from app.pipeline.legal_validator import validate_legal_record
from app.schemas import LegalRecord

SOURCE_TEXT = """
Supreme Court of the United States
Gideon v. Wainwright, 372 U.S. 335 (1963)
Decided: March 18, 1963
The petitioner contended that he had been denied due process.
The Court held that the Sixth Amendment's guarantee of counsel is a fundamental right essential to a fair trial.
"In our adversary system of criminal justice, any person haled into court, who is too poor to hire a lawyer, cannot be assured a fair trial unless counsel is provided for him."
Section 1 of the Fourteenth Amendment makes this applicable to the states.
"""

def test_validate_legal_record_accurate():
    record = LegalRecord(
        article_title="Gideon v. Wainwright",
        court_or_tribunal="Supreme Court of the United States",
        case_name="Gideon v. Wainwright",
        citation="372 U.S. 335",
        judgment_date="March 18, 1963",
        relevant_statutes=["Fourteenth Amendment"],
        holding_or_operative_order="The Court held that the Sixth Amendment's guarantee of counsel is a fundamental right essential to a fair trial.",
        exact_quotations=["In our adversary system of criminal justice, any person haled into court, who is too poor to hire a lawyer, cannot be assured a fair trial unless counsel is provided for him."]
    )

    summary = validate_legal_record(record, SOURCE_TEXT)
    assert summary.total_claims > 0
    assert summary.verified_claims == summary.total_claims
    assert summary.has_critical_unverified is False
    assert len(summary.warnings) == 0

def test_validate_legal_record_party_argument_mistaken_for_holding():
    # If the holding is actually an argument of the petitioner
    record = LegalRecord(
        article_title="Gideon v. Wainwright",
        case_name="Gideon v. Wainwright",
        holding_or_operative_order="The petitioner contended that he had been denied due process."
    )

    summary = validate_legal_record(record, SOURCE_TEXT)
    holding_claim = next(c for c in summary.claims if c.claim_id == "holding")
    assert holding_claim.verified is False
    assert "party argument language" in (holding_claim.warning_notes or "")
    assert summary.has_critical_unverified is True

def test_validate_legal_record_unverified_quotation():
    record = LegalRecord(
        article_title="Gideon v. Wainwright",
        case_name="Gideon v. Wainwright",
        holding_or_operative_order="The Court held that counsel is essential to a fair trial.",
        exact_quotations=["This is a completely fabricated quote that never appeared in the text."]
    )

    summary = validate_legal_record(record, SOURCE_TEXT)
    quote_claim = next(c for c in summary.claims if c.claim_id == "quote_0")
    assert quote_claim.verified is False
    assert any("Quotation #1 was not found" in w for w in summary.warnings)
