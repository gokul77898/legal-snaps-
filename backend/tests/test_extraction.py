from app.schemas import ExtractionResult
from app.pipeline.extraction import build_analysis_corpus, count_words, structure_legal_text


def test_boilerplate_is_removed_and_substance_kept():
    raw = "\n\n".join([
        "### Unlock Advanced Research with PRISM AI",
        "designed for legal practitioners, researchers, students and institutions",
        "### Supreme Court of India",
        "### Justice K.S.Puttaswamy(Retd) And Anr. vs Union Of India And Ors. on 24 August, 2017",
        "Download as PDF",
        "Share this judgment",
        "Held: the right to privacy is an intrinsic part of the right to life under Article 21.",
        "Cookie policy | Terms of use | All rights reserved",
    ])

    result = structure_legal_text(raw)

    assert "PRISM AI" not in result.text
    assert "designed for legal practitioners" not in result.text
    assert "Download as PDF" not in result.text
    assert "Cookie policy" not in result.text
    assert "right to privacy is an intrinsic part" in result.text
    assert "Puttaswamy" in result.text
    assert result.boilerplate_lines_removed >= 4
    assert "### Supreme Court of India" in result.section_headings[0] or result.section_headings


def test_short_sources_are_flagged_instead_of_silently_passed_on():
    result = structure_legal_text("Buy now\nSubscribe\nContact us")
    assert result.char_count < 300
    assert result.warnings


def test_analysis_corpus_reaches_the_holding_deep_in_a_long_judgment():
    """
    Regression for the root cause of identical infographics: a blind prefix of a 900k
    character judgment is cover-page noise, so the model never saw the operative holding.
    """
    filler = [f"### Paragraph {i} of the bench's recitation of procedural history." for i in range(1, 120)]
    holding = (
        "Held: Article 21 protects the right to privacy as an intrinsic part of the right to "
        "life and personal liberty; the petition is allowed on that ground."
    )
    text = "\n\n".join(filler + [holding, "### Costs and directions on the operative order."])

    extraction = structure_legal_text(text)
    corpus = build_analysis_corpus(extraction, max_chars=1500)

    assert len(corpus) <= 1500
    assert "right to privacy as an intrinsic part" in corpus
    assert "operative order" in corpus


def test_short_documents_pass_through_unchanged():
    text = "A two paragraph note.\n\nIt states the holding plainly."
    extraction = structure_legal_text(text)
    assert build_analysis_corpus(extraction, max_chars=5000) == extraction.text


def test_word_count_counts_the_sanitised_text():
    extraction = structure_legal_text("The court held that privacy is a fundamental right.")
    assert count_words(extraction.text) == 9
