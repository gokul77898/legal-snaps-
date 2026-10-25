import json
import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, get_origin

import httpx
from huggingface_hub import AsyncInferenceClient
from pydantic import ValidationError

from app.config import settings
from app.schemas import InfographicContentPlan, LegalRecord

logger = logging.getLogger(__name__)


class HFProviderError(RuntimeError):
    """Raised when a Hugging Face Inference Provider call cannot be completed.

    The pipeline turns this into a failed job. Analysis is never satisfied by a regex
    parser, a sample record, or any other local stand-in.
    """


ANALYSIS_MAX_TOKENS = 6000
ANALYSIS_TIMEOUT_SECONDS = 300.0
ANALYSIS_ATTEMPTS = 2
ARTWORK_TIMEOUT_SECONDS = 240.0


ANALYSIS_JSON_SCHEMA_HINT = """{
  "article_title": "short title of this specific article or case",
  "court_or_tribunal": "string or null",
  "case_name": "string or null - exactly the party names, one line, no judge list",
  "citation": "string or null - only when this document itself is that decision",
  "case_number": "string or null",
  "bench_composition": ["judge names if the text lists them, otherwise []"],
  "judgment_date": "string or null - the decision date, never the article publication date",
  "relevant_statutes": ["provisions this document actually decides or explains"],
  "material_facts": ["facts stated in the text"],
  "procedural_history": "string or null",
  "questions_or_issues": ["legal issues framed in the text"],
  "arguments_parties": [],
  "legal_reasoning": ["reasoning steps stated in the text"],
  "holding_or_operative_order": "the operative conclusion stated in the text",
  "precedents_cited": ["case names the text cites"],
  "exact_quotations": ["verbatim passages copied from the text"],
  "practical_implications": ["consequences stated in the text"],
  "supporting_source_passages": ["short verbatim excerpts backing the holding"],
  "unverified_fields": ["names of fields the text does not support"],
  "uncertainties": ["what the text fails to establish"],
  "is_court_judgment": "true only when this document IS a judgment, otherwise false",
  "legislation_or_article_type": "court-judgment | news-article | statute | law-review | government-order"
}"""


def build_analysis_prompt(corpus: str, title: str, source_url: Optional[str]) -> str:
    return f"""You are a senior legal researcher preparing structured data for an infographic.

Analyse ONLY the DOCUMENT below. Write nothing that is not supported by it.

Rules:
1. Report the specific matter in this document. Never reuse generic phrasing.
2. A law-firm article, news report, commentary, statute or government order that DISCUSSES a
   decision is not itself a judgment. Set is_court_judgment to false and name the type in
   legislation_or_article_type. Set it true only when the document contains the court's own
   caption, coram and operative order. For commentary leave court_or_tribunal and judgment_date
   null and bench_composition as an empty list unless the document states them.
3. case_name must be a single short line of party names. Do not put judge names, headings,
   cover pages or table-of-contents text into it.
4. citation and case_number identify only the decision this document itself is. For commentary
   put the discussed decision's citation in precedents_cited and leave citation null.
   judgment_date is the decision date, never the article publication date; otherwise null.
   Add every absent identifier to unverified_fields.
5. exact_quotations must be copied verbatim from the document. Do not paraphrase them.
6. holding_or_operative_order is the document's own conclusion, not a party's argument. If the
   document reports only arguments, say so in uncertainties.
7. Distinguish quoted precedent from this document's reasoning: cases merely cited belong in
   precedents_cited, not in relevant_statutes.
8. Anything the document does not establish goes into uncertainties. Do not fill gaps from
   general knowledge of Indian or comparative law.
9. Each item in legal_reasoning and practical_implications is one declarative sentence under
   28 words. Questions belong only in questions_or_issues, never in legal_reasoning.

Return ONLY one JSON object with exactly these keys. No prose, no markdown fences, no
comments, and no trailing text. Every key must be present: use [] for an empty list and
null only for absent optional text:
{ANALYSIS_JSON_SCHEMA_HINT}

SOURCE URL: {source_url or "not recorded"}
REQUESTED TOPIC: {title}

DOCUMENT:
{corpus}
"""


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:400] or "no error body"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail")
            if message:
                return str(message)[:400]
        if isinstance(error, str):
            return error[:400]
        if payload.get("message"):
            return str(payload["message"])[:400]
    return json.dumps(payload)[:400]


async def _hf_request(
    path: str,
    payload: Dict[str, Any],
    timeout: float,
) -> httpx.Response:
    token = settings.get_effective_hf_token()
    if not token:
        raise HFProviderError(
            "No Hugging Face token configured. Set HF_TOKEN in backend/.env "
            "(or run `hf auth login`) to use the inference providers."
        )

    url = (
        path
        if path.startswith("http")
        else f"{settings.hf_router_base_url.rstrip('/')}/{path.lstrip('/')}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as e:
        raise HFProviderError(f"Hugging Face request to {path} timed out after {timeout:.0f}s.") from e
    except httpx.HTTPError as e:
        raise HFProviderError(f"Hugging Face request to {path} failed: {e}") from e

    if response.status_code != 200:
        raise HFProviderError(
            f"Hugging Face {path} returned {response.status_code}: {_extract_error_detail(response)}"
        )
    return response


async def _hf_chat_completion(payload: Dict[str, Any]) -> Dict[str, Any]:
    response = await _hf_request("chat/completions", payload, ANALYSIS_TIMEOUT_SECONDS)
    try:
        return response.json()
    except ValueError as e:
        raise HFProviderError(
            f"Hugging Face chat endpoint returned non-JSON: {response.text[:200]}"
        ) from e


def _extract_completion_text(body: Dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise HFProviderError(
            f"Hugging Face returned no choices: {json.dumps(body)[:300]}"
        )

    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")

    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )

    if not isinstance(content, str) or not content.strip():
        raise HFProviderError("Hugging Face returned an empty completion.")

    if choice.get("finish_reason") == "length":
        raise HFProviderError(
            "Hugging Face stopped at the token limit before finishing the JSON document."
        )
    return content


def _parse_json_object(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise HFProviderError(f"Hugging Face returned no JSON object. Received: {cleaned[:200]}")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as e:
        raise HFProviderError(f"Hugging Face returned malformed JSON: {e}") from e


def _normalise_null_lists(data: Dict[str, Any]) -> Dict[str, Any]:
    """Treat a null list field as an empty list.

    The model occasionally sends null for list fields that the prompt marks optional
    (for example bench_composition when the source is a news article). Null means the
    source did not provide the information, not that the record is invalid.
    """
    if not isinstance(data, dict):
        raise ValueError("Hugging Face response must be a JSON object.")
    normalised = dict(data)
    for name, field in LegalRecord.model_fields.items():
        if get_origin(field.annotation) is list and normalised.get(name, ...) is None:
            normalised[name] = []
    return normalised


def _scrub_unsupported_quotations(record: LegalRecord, source_text: str) -> List[str]:
    """Drop quotations the source does not contain, so a paraphrase is never shown as a quote."""
    from app.pipeline.legal_validator import normalize_text

    norm_source = normalize_text(source_text)
    kept: List[str] = []
    dropped: List[str] = []
    for quote in record.exact_quotations:
        (kept if normalize_text(quote) in norm_source else dropped).append(quote)
    record.exact_quotations = kept
    return dropped


def _analysis_messages(prompt: str, feedback: Optional[str]) -> List[Dict[str, str]]:
    user_content = prompt
    if feedback:
        user_content = (
            f"{prompt}\n\n"
            "VALIDATION FEEDBACK FOR YOUR PREVIOUS ATTEMPT:\n"
            f"{feedback}\n"
            "Return the complete JSON object again. Every key in the schema must be present; "
            "use [] for empty lists and null for absent optional text. Do not omit "
            "holding_or_operative_order."
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a legal-research data extraction engine. You reply with a single "
                "valid JSON object only, never with prose or markdown."
            ),
        },
        {"role": "user", "content": user_content},
    ]


async def analyze_legal_with_hf(
    text: str,
    title: str,
    source_url: Optional[str] = None,
) -> LegalRecord:
    """
    Analyse the retrieved document with the configured Qwen model and return a
    schema-validated LegalRecord.

    Raises HFProviderError on a missing token, a provider error, or output that fails
    schema validation. There is no local fallback.
    """
    prompt = build_analysis_prompt(text, title, source_url)
    feedback: Optional[str] = None
    record: Optional[LegalRecord] = None

    for attempt in range(ANALYSIS_ATTEMPTS):
        body = await _hf_chat_completion({
            "model": settings.hf_text_model,
            "messages": _analysis_messages(prompt, feedback),
            "temperature": 0.1,
            "max_tokens": ANALYSIS_MAX_TOKENS,
        })

        try:
            data = _normalise_null_lists(_parse_json_object(_extract_completion_text(body)))
            if (
                not isinstance(data.get("holding_or_operative_order"), str)
                or not data["holding_or_operative_order"].strip()
            ):
                raise ValueError("holding_or_operative_order is missing or empty")
            record = LegalRecord.model_validate(data)
            break
        except (HFProviderError, ValidationError, ValueError) as e:
            feedback = str(e)
            if attempt + 1 < ANALYSIS_ATTEMPTS:
                logger.warning(
                    "Analysis attempt %s rejected; retrying once: %s",
                    attempt + 1,
                    feedback,
                )
                continue

    if record is None:
        raise HFProviderError(
            "Hugging Face output did not match the legal record schema after "
            f"{ANALYSIS_ATTEMPTS} attempts: {feedback}"
        )

    dropped = _scrub_unsupported_quotations(record, text)
    if dropped:
        record.unverified_fields = list(record.unverified_fields) + [
            f"exact_quotations ({len(dropped)} removed: not verbatim in source)"
        ]
        record.uncertainties = list(record.uncertainties) + [
            f"Removed quotation absent from source: {q[:90]}" for q in dropped
        ]

    record.analysis_source = f"huggingface:{settings.hf_text_model}"
    logger.info(
        "Legal record for '%s' analysed via %s",
        record.case_name or record.article_title, record.analysis_source,
    )
    return record


# ---------------------------------------------------------------------------
# Article-specific artwork (FLUX.1-dev via Hugging Face Inference Providers)
# ---------------------------------------------------------------------------

def build_artwork_prompt(plan: InfographicContentPlan) -> str:
    """
    Build an illustration prompt from this job's validated content.

    Deliberately excludes headings, citations and quotations: those are rendered as real
    text by the SVG designer, because image models distort precise legal text.
    """
    subject = plan.artwork_subject or plan.headline
    return (
        "Premium flat-vector editorial spot illustration for a legal publication, isolated on "
        "pure white. Absolutely no text, letters, words, numbers, brand names, logos, watermarks, "
        "signatures, banners, flags, emblems, frames, or borders anywhere in the image. "
        f"Article-specific visual brief: {subject}. "
        "Show exactly one contemporary professional woman advocate with medium-brown skin and "
        "natural black hair, wearing a simple dark navy business suit and white shirt. She has "
        "no wig, no judicial robe, no head covering, and no colonial dress. Choose exactly one "
        "legal object: either a balanced golden scales-of-justice icon or one closed slate law "
        "book, never both. Use only the isolated person and that one object: no courtroom, bench, "
        "furniture, architecture, scenery, floor, circular halo, panel, rectangle, backdrop, or "
        "other background element. Communicate the article's subject through the legal object, "
        "not through flags or national symbols. "
        "Sophisticated modern editorial vector style, clean geometric silhouettes, crisp edges, "
        "subtle two-tone shading, anatomically correct hands, no sketch lines, no gradients, "
        "no 3D, no photorealism. Strict palette only: warm gold #CFA444, dark slate navy "
        "#2A2E3D, muted slate #4A4C5A, and white; use a restrained warm skin tone where needed. "
        "Pure white background extending uninterrupted to every edge, with no floor, cast shadow, "
        "or shading shape behind the subject. Balanced square composition with the complete "
        "subject visible and comfortable white space at the edges."
    )


async def generate_legal_artwork(
    output_path: str,
    plan: InfographicContentPlan,
) -> Tuple[bool, Optional[str]]:
    """Generate article-specific artwork through HF's native text-to-image task.

    The official client selects the provider's supported native route instead of
    relying on the inconsistently supported OpenAI-compatible images route. The returned
    image is re-encoded as PNG so the SVG always receives the correct data MIME type.
    """
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    token = settings.get_effective_hf_token()
    if not token:
        return False, "No Hugging Face token configured for artwork generation."

    side = getattr(settings, "artwork_max_side", 1024)
    try:
        client = AsyncInferenceClient(
            provider=settings.hf_image_provider,
            api_key=token,
            timeout=ARTWORK_TIMEOUT_SECONDS,
        )
        image = await client.text_to_image(
            build_artwork_prompt(plan),
            negative_prompt=(
                "text, letters, words, numbers, brand names, logo, watermark, signature, "
                "banner, flag, emblem, wig, judicial robe, colonial dress, courtroom, bench, "
                "furniture, architecture, scenery, red, green, multicolor, border, frame, "
                "background shape, circle, halo, panel, rectangle, floor, cast shadow, "
                "photorealism, 3d"
            ),
            model=settings.hf_image_model,
            width=side,
            height=side,
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
    except Exception as e:
        logger.warning(
            "Artwork generation failed (%s via %s): %s",
            settings.hf_image_model,
            settings.hf_image_provider,
            e,
        )
        return False, str(e)

    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, "Generated artwork could not be encoded as a PNG."
    if len(image_bytes) < 2048:
        return False, f"Generated artwork is implausibly small ({len(image_bytes)} bytes), likely blank."

    target.write_bytes(image_bytes)
    logger.info(
        "Artwork for this job written to %s (%d bytes) using %s via %s",
        output_path,
        len(image_bytes),
        settings.hf_image_model,
        settings.hf_image_provider,
    )
    return True, None
