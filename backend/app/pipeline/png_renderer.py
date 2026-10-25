import os
import struct
import logging
from pathlib import Path
from typing import Tuple, Optional
import resvg_py

logger = logging.getLogger(__name__)

PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"

# Poppins is bundled with the app so resvg renders the poster in the Legal Snaps
# typeface on every machine instead of falling back to a generic sans.
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"


def _font_files() -> list[str]:
    if not FONT_DIR.is_dir():
        return []
    return sorted(str(path) for path in FONT_DIR.glob("*.ttf"))


def get_png_dimensions(png_bytes: bytes) -> Tuple[int, int]:
    """Parse IHDR chunk of PNG to extract exact width and height."""
    if len(png_bytes) < 24 or not png_bytes.startswith(PNG_MAGIC_BYTES):
        return 0, 0
    # IHDR chunk starts at byte 12; width at 16, height at 20
    w, h = struct.unpack(">II", png_bytes[16:24])
    return w, h

def render_svg_to_png(
    svg_string: str,
    output_path: str,
    expected_width: int = 1200,
    expected_height: int = 1200
) -> Tuple[bool, Optional[str]]:
    """
    Renders SVG markup into a verified PNG image file using resvg.
    Validates output existence, PNG magic header, non-zero file size, and image dimensions.
    """
    try:
        # Convert SVG to PNG bytes via resvg
        png_bytes = resvg_py.svg_to_bytes(svg_string, font_files=_font_files() or None)
        
        # 1. Check validity of PNG signature
        if not png_bytes.startswith(PNG_MAGIC_BYTES):
            return False, "Rendered output is not a valid PNG (missing PNG magic signature)."

        # 2. Check file size (a 1200x1200 infographic with text and cards is typically > 25 KB)
        if len(png_bytes) < 1024:
            return False, f"Rendered image file is unexpectedly tiny ({len(png_bytes)} bytes); possible blank canvas."

        # 3. Check PNG dimensions
        actual_w, actual_h = get_png_dimensions(png_bytes)
        if actual_w == 0 or actual_h == 0:
            return False, "Failed to read PNG dimensions from IHDR chunk."

        # 4. Save to destination path
        target_file = Path(output_path)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_bytes(png_bytes)

        if not target_file.exists() or target_file.stat().st_size == 0:
            return False, "Failed to persist rendered PNG to disk."

        logger.info(
            "Successfully rendered PNG to %s (%d bytes, %dx%d px)",
            output_path, len(png_bytes), actual_w, actual_h
        )
        return True, None

    except Exception as e:
        logger.error("SVG-to-PNG rendering exception: %s", e)
        return False, f"PNG rendering exception: {str(e)}"
