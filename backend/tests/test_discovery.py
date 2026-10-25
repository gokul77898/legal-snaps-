import pytest
from app.pipeline.discovery import calculate_credibility, discover_sources
from app.schemas import SourceCandidate

def test_calculate_credibility_primary_court():
    score, is_primary = calculate_credibility("https://www.supremecourt.gov/opinions/23pdf/21-1271.pdf", "US Supreme Court Opinion")
    assert is_primary is True
    assert score >= 0.95

def test_calculate_credibility_gov():
    score, is_primary = calculate_credibility("https://main.sci.gov.in/judgment/123.pdf", "Supreme Court of India Judgment")
    assert is_primary is True
    assert score >= 0.92

def test_calculate_credibility_legal_news():
    score, is_primary = calculate_credibility("https://www.livelaw.in/top-stories/supreme-court-ruling-12345", "Supreme Court Ruling")
    assert is_primary is False
    assert score >= 0.80

def test_candidate_ranking_order():
    c1 = SourceCandidate(title="Generic Blog", url="https://randomblog.com/case", credibility_score=0.5, is_primary_source=False)
    c2 = SourceCandidate(title="Legal Portal", url="https://law360.com/case", credibility_score=0.82, is_primary_source=False)
    c3 = SourceCandidate(title="Supreme Court Official", url="https://supremecourt.gov/case", credibility_score=0.95, is_primary_source=True)

    candidates = [c1, c2, c3]
    candidates.sort(key=lambda x: (x.is_primary_source, x.credibility_score), reverse=True)

    assert candidates[0].title == "Supreme Court Official"
    assert candidates[1].title == "Legal Portal"
    assert candidates[2].title == "Generic Blog"
