import pytest
from pydantic import ValidationError
from app.schemas import InfographicCreateRequest, LegalRecord, ClaimValidation, ValidationSummary

def test_infographic_create_request_valid():
    req = InfographicCreateRequest(
        article_name="Brown v. Board of Education",
        language="en",
        output_format="both",
        width=1200,
        height=1200
    )
    req.validate_input_present()
    assert req.article_name == "Brown v. Board of Education"
    assert req.output_format == "both"

def test_infographic_create_request_missing_all_inputs():
    req = InfographicCreateRequest()
    with pytest.raises(ValueError, match="must supply an article name"):
        req.validate_input_present()

def test_infographic_create_request_invalid_dimensions():
    with pytest.raises(ValidationError):
        InfographicCreateRequest(article_name="Valid Name", width=100) # Below min 600

def test_legal_record_defaults_and_nulls():
    record = LegalRecord(
        article_title="Statutory Reform Overview",
        holding_or_operative_order="Statute repealed previous provisions."
    )
    assert record.article_title == "Statutory Reform Overview"
    assert record.court_or_tribunal is None
    assert record.case_name is None
    assert record.bench_composition == []
    assert record.relevant_statutes == []
