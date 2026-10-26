import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from app.schemas import InfographicContentPlan, TakeawayItem
from app.pipeline.svg_designer import generate_legal_snaps_svg, wrap_text_into_lines
from app.pipeline.png_renderer import render_svg_to_png, PNG_MAGIC_BYTES, get_png_dimensions

def test_wrap_text_into_lines():
    text = "The Supreme Court of the United States held that separate educational facilities are inherently unequal."
    lines = wrap_text_into_lines(text, max_chars_per_line=30)
    assert len(lines) >= 3
    for line in lines:
        assert len(line) <= 35

def test_generate_svg_xml_validity_canonical_style():
    plan = InfographicContentPlan(
        headline="India's New Criminal Laws: Reform or Overreach?",
        subtitle="A look into the Bharatiya Nyaya Sanhita (BNS), BNSS, and BSA – replacing colonial statutes.",
        header_icon="scales",
        overview_text="Effective July 1, 2024, India implemented new criminal laws. Legal experts raise concerns about increased police powers.",
        takeaways=[
            TakeawayItem(icon_type="gavel", description="New laws replace IPC, CrPC, and Evidence Act."),
            TakeawayItem(icon_type="book", description="Critics argue old provisions retained."),
            TakeawayItem(icon_type="prohibited", description="Concerns include longer police remand.")
        ],
        comparison_title="Key Changes in India's Criminal Laws",
        comparison_old_title="OLD LAWS (IPC / CrPC)",
        comparison_old_items=["Police Remand: 15 days", "Sedition: Section 124A (IPC)"],
        comparison_new_title="NEW LAWS (BNS / BNSS)",
        comparison_new_items=["Police Remand: Up to 60/90 days", "Sedition: Section 152 (BNS)"],
        comparison_footnote="Clearly compares main features impacting legal outcomes.",
        footer_brand="Legal Snaps",
        footer_date="June 27, 2025"
    )

    svg_str = generate_legal_snaps_svg(plan, width=800, height=1240)

    # Validate that SVG string is well-formed XML
    root = ET.fromstring(svg_str)
    assert root.tag.endswith("svg")
    assert root.attrib["width"] == "800"
    assert root.attrib["height"] == "1240"
    assert "Legal Snaps" in svg_str
    assert "OVERVIEW" in svg_str
    assert "KEY TAKEAWAYS" in svg_str
    assert "#CFA444" in svg_str  # Canonical Gold color
    assert "#4A4C5A" in svg_str  # Canonical Gray color

def test_svg_to_png_rendering_canonical():
    plan = InfographicContentPlan(
        headline="Minimum Three-Year Practice Rule for Civil Judges",
        subtitle="Supreme Court reinstates experience mandate for judicial service aspirants",
        header_icon="gavel",
        overview_text="On 20 May 2025, the Supreme Court ruled that candidates must have minimum 3 years of legal practice before appearing for judicial service exams.",
        takeaways=[
            TakeawayItem(icon_type="gavel", description="Practical skills needed before appointment"),
            TakeawayItem(icon_type="court", description="Better case management in district courts")
        ],
        comparison_old_title="BEFORE",
        comparison_old_items=["Fresh graduates eligible", "Faster entry into judiciary"],
        comparison_new_title="AFTER",
        comparison_new_items=["3-year practice mandatory", "Only experienced lawyers eligible"],
        footer_brand="Legal Snaps",
        footer_date="August 2025"
    )
    svg_str = generate_legal_snaps_svg(plan, width=800, height=1240)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_png = Path(tmpdir) / "canonical_legal_snap.png"
        success, err = render_svg_to_png(svg_str, str(output_png), expected_width=800, expected_height=1240)
        assert success is True
        assert err is None
        assert output_png.exists()
        
        png_data = output_png.read_bytes()
        assert png_data.startswith(PNG_MAGIC_BYTES)
        assert len(png_data) > 10000
        
        w, h = get_png_dimensions(png_data)
        assert w == 800
        assert h == 1240


def test_square_canvas_keeps_full_editorial_composition():
    plan = InfographicContentPlan(
        headline="Sukanya Shantha vs Union Of India",
        subtitle="Caste Discrimination in Prisons",
        meta_line="Supreme Court of India · 2024",
        header_icon="scales",
        overview_text=(
            "The Court held that caste-based discrimination in prisons is unconstitutional "
            "and directed the government to prevent such discrimination."
        ),
        takeaways=[
            TakeawayItem(icon_type="gavel", description="Caste-based discrimination violates constitutional equality"),
            TakeawayItem(icon_type="court", description="Article 17 abolishes untouchability"),
            TakeawayItem(icon_type="book", description="Article 21 guarantees life and personal liberty"),
            TakeawayItem(icon_type="prohibited", description="Article 23 prohibits forced labour"),
        ],
        comparison_title="The Law and the Ruling",
        comparison_old_title="THE LAW",
        comparison_old_items=["Article 14", "Article 15"],
        comparison_new_title="THE COURT'S READING",
        comparison_new_items=["Prison authorities must treat prisoners equally", "Caste segregation is unconstitutional"],
        comparison_footnote="Claims verified against the retrieved source.",
        footer_brand="Legal Snaps",
        footer_date="3 October, 2024",
        source_url="https://indiankanoon.org/doc/137753759/",
        artwork_subject="Caste equality in prisons",
    )

    svg = generate_legal_snaps_svg(
        plan,
        width=1200,
        height=1200,
        artwork_base64_data_uri="data:image/png;base64,AAAA",
    )

    root = ET.fromstring(svg)
    # Read the flattened copy rather than the raw markup: a long sentence may wrap onto
    # two tspans at a square aspect ratio, which is still the full sentence on the poster.
    chunks = [node.text or "" for node in root.iter() if node.tag.endswith("tspan")]
    chunks += [
        node.text or ""
        for node in root.iter()
        if node.tag.endswith("text") and not any(child.tag.endswith("tspan") for child in node)
    ]
    visible = " ".join(" ".join(chunks).split())
    assert all(item.description in visible for item in plan.takeaways)
    assert "The Law and the Ruling" in visible
    assert "Prison authorities must treat prisoners equally" in visible
    assert "…" not in visible
    assert '<image ' in svg
    assert "data:image/png;base64,AAAA" in svg
