import pytest
import pymupdf
from app.pipeline.retrieval import extract_html_content, extract_pdf_content

def test_extract_html_content():
    sample_html = b"""
    <!DOCTYPE html>
    <html>
    <head><title>Kesavananda Bharati v. State of Kerala</title></head>
    <body>
        <nav><a href="/">Home</a></nav>
        <article>
            <h1>Landmark Constitutional Ruling</h1>
            <p>The Supreme Court of India established the Basic Structure Doctrine.</p>
            <blockquote>The Constitution cannot be altered in its basic features.</blockquote>
        </article>
        <footer>Copyright 2026 Legal Journal</footer>
    </body>
    </html>
    """
    text, title, meta = extract_html_content(sample_html, "https://lawjournal.example/case")
    assert "Kesavananda Bharati" in title or "Landmark" in title
    assert "Basic Structure Doctrine" in text
    assert "Copyright 2026" not in text  # Footer removed

def test_extract_pdf_content_pymupdf():
    # Create an in-memory PDF using PyMuPDF
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "SUPREME COURT OF THE UNITED STATES\nBrown v. Board of Education, 347 U.S. 483 (1954)")
    pdf_bytes = doc.tobytes()
    doc.close()

    text, title, meta = extract_pdf_content(pdf_bytes)
    assert "Brown v. Board of Education" in text
    assert meta["page_count"] == 1
    assert meta["is_scanned"] is False
    assert meta["total_chars"] > 20

def test_scanned_pdf_detection():
    # Create a PDF with zero text (simulating a scanned image page)
    doc = pymupdf.open()
    doc.new_page()  # Blank page
    pdf_bytes = doc.tobytes()
    doc.close()

    text, title, meta = extract_pdf_content(pdf_bytes)
    assert meta["total_chars"] == 0
