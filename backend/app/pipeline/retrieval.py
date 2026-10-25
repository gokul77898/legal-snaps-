import os
import io
import re
import logging
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
import pymupdf
from app.config import settings
from app.schemas import SourceMetadata

logger = logging.getLogger(__name__)

async def fetch_url_bytes(url: str) -> Tuple[bytes, str, int]:
    """Fetch URL and return bytes, final URL after redirects, and HTTP status."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }
    async with httpx.AsyncClient(timeout=settings.api_timeout_seconds, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        return resp.content, str(resp.url), resp.status_code

def extract_html_content(html_bytes: bytes, url: str) -> Tuple[str, str, Dict[str, Any]]:
    """Clean and extract article text, title, and metadata from HTML."""
    soup = BeautifulSoup(html_bytes, "html.parser")
    
    # Extract Title
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        title = soup.title.string.strip()
    else:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
            
    # Remove script, style, nav, footer, ads, header tags
    for tag in soup(["script", "style", "nav", "footer", "aside", "header", "noscript", "iframe", "svg"]):
        tag.decompose()
        
    main_elem = (
        soup.find("article") or
        soup.find("main") or
        soup.find(class_=re.compile(r"judgment|judgment-body|article-content|post-content|entry-content|case-content|law-text|opinion", re.I)) or
        soup.find(id=re.compile(r"content|judgment|article|main|opinion", re.I)) or
        soup.body
    )
    
    if not main_elem:
        return "", title, {}
        
    paragraphs = []
    for elem in main_elem.find_all(["h1", "h2", "h3", "h4", "p", "blockquote", "pre"]):
        text = elem.get_text(" ", strip=True)
        if len(text) > 15:
            if elem.name in ["h1", "h2", "h3", "h4"]:
                paragraphs.append(f"\n### {text}\n")
            elif elem.name == "blockquote":
                paragraphs.append(f"> {text}")
            else:
                paragraphs.append(text)
                
    content_text = "\n\n".join(paragraphs).strip()
    
    publisher = ""
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        publisher = og_site["content"].strip()
        
    return content_text, title, {"publisher": publisher}

def extract_pdf_content(pdf_bytes: bytes) -> Tuple[str, str, Dict[str, Any]]:
    """Extract text and metadata from PDF using PyMuPDF."""
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.error("Failed to open PDF stream with PyMuPDF: %s", e)
        raise ValueError(f"Invalid or corrupted PDF file: {e}")

    meta = doc.metadata or {}
    pdf_title = meta.get("title") or ""
    page_texts = []
    total_chars = 0
    total_images = 0
    
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = page.get_text()
        total_chars += len(text.strip())
        image_list = page.get_images(full=True)
        total_images += len(image_list)
        
        if text.strip():
            page_texts.append(f"--- [Page {page_idx + 1}] ---\n{text.strip()}")
            
    is_scanned = (total_chars < 100 and total_images > 0 and len(doc) > 0)
    
    metadata = {
        "page_count": len(doc),
        "total_chars": total_chars,
        "is_scanned": is_scanned,
        "author": meta.get("author", ""),
        "subject": meta.get("subject", ""),
        "producer": meta.get("producer", "")
    }
    
    doc.close()
    return "\n\n".join(page_texts), pdf_title, metadata

async def perform_ocr(pdf_bytes: bytes) -> Tuple[str, bool]:
    """Execute OCR when configured. Never claims OCR succeeded if not actually executed."""
    if settings.ocr_provider == "disabled":
        return "", False
        
    if settings.ocr_provider == "tesseract":
        tess_path = settings.tesseract_cmd
        if not os.path.exists(tess_path):
            return "", False
            
        try:
            import subprocess
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            ocr_text_parts = []
            
            pages_to_ocr = min(len(doc), 5)
            for i in range(pages_to_ocr):
                page = doc[i]
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                
                proc = subprocess.run(
                    [tess_path, "stdin", "stdout", "-l", "eng"],
                    input=img_bytes,
                    capture_output=True,
                    timeout=30
                )
                if proc.returncode == 0:
                    ocr_text_parts.append(f"--- [Page {i + 1} OCR] ---\n{proc.stdout.decode('utf-8', errors='ignore')}")
            doc.close()
            return "\n\n".join(ocr_text_parts), True
        except Exception as e:
            logger.error("OCR execution error: %s", e)
            return "", False

    return "", False

async def retrieve_and_extract(url: str, is_pdf: bool = False) -> Tuple[str, SourceMetadata]:
    """
    Main retrieval function:
    Fetches URL, handles redirects, extracts content, and checks size limits.
    """
    retrieval_time = datetime.now(timezone.utc).isoformat()
    warnings = []
    
    content_bytes, final_url, status_code = await fetch_url_bytes(url)

    if status_code != 200:
        raise ValueError(f"Source server returned HTTP {status_code} for {url}")

    if len(content_bytes) > settings.max_source_size_bytes:
        raise ValueError(f"Source document exceeds maximum allowed size ({len(content_bytes)} bytes > {settings.max_source_size_bytes} bytes).")

    is_pdf_content = is_pdf or final_url.lower().endswith(".pdf") or content_bytes.startswith(b"%PDF-")
    
    extracted_text = ""
    title = ""
    method = "html_direct"
    publisher = ""

    if is_pdf_content:
        method = "pymupdf_pdf"
        extracted_text, title, pdf_meta = extract_pdf_content(content_bytes)
        
        if pdf_meta.get("is_scanned"):
            ocr_text, ocr_success = await perform_ocr(content_bytes)
            if ocr_success and ocr_text.strip():
                extracted_text = ocr_text
                method = "ocr_scanned_pdf"
            else:
                method = "pymupdf_pdf_scanned_unocr"
                warnings.append("Document appears to be a scanned image-based PDF. OCR was not executed or produced no text.")
    else:
        method = "html_direct"
        extracted_text, title, html_meta = extract_html_content(content_bytes, final_url)
        publisher = html_meta.get("publisher", "")

    if not extracted_text.strip():
        raise ValueError(f"Could not extract any readable text from source at {url}.")

    if not title:
        first_line = extracted_text.strip().split("\n")[0][:120]
        title = first_line if first_line else "Legal Document"

    source_meta = SourceMetadata(
        title=title,
        url=final_url,
        publisher=publisher,
        retrieval_time=retrieval_time,
        extraction_method=method,
        text_length=len(extracted_text),
        status="success",
        warnings=warnings
    )

    return extracted_text, source_meta
