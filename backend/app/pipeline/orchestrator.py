import asyncio
import base64
import logging
from pathlib import Path
from typing import List, Optional
from xml.etree import ElementTree as ET

from app.config import settings
from app.database import get_job, list_jobs, update_job
from app.schemas import JobStage, STAGE_NAMES
from app.pipeline.discovery import discover_sources
from app.pipeline.retrieval import retrieve_and_extract
from app.pipeline.extraction import build_analysis_corpus, count_words, structure_legal_text
from app.pipeline.hf_ai import (
    HFProviderError,
    analyze_legal_with_hf,
    generate_design_brief_with_hf,
    generate_explainer_illustrations,
    generate_legal_artwork,
)
from app.pipeline.legal_validator import validate_legal_record
from app.pipeline.content_planner import plan_infographic_content
from app.pipeline.svg_designer import generate_legal_snaps_svg
from app.pipeline.png_renderer import PNG_MAGIC_BYTES, get_png_dimensions, render_svg_to_png

logger = logging.getLogger(__name__)

# A page below this length rarely contains an operable holding, so the pipeline keeps
# looking through the remaining candidates instead of analysing a stub.
MIN_SOURCE_CHARS = 1200


class PipelineError(RuntimeError):
    """A stage's real operation failed. Recorded on the job instead of a success state."""


def _render_png(svg_markup: str, png_path: Path, width: int, height: int) -> None:
    ok, err = render_svg_to_png(svg_markup, str(png_path), expected_width=width, expected_height=height)
    if not ok or not png_path.is_file():
        raise PipelineError(f"SVG rasterisation failed: {err or 'no output file'}")


def _stored_layout_key(job: dict) -> Optional[str]:
    """Rebuild DesignBrief.layout_key from a stored job, without revalidating its pointers."""
    brief = job.get("design_brief") or {}
    sections = brief.get("sections") or []
    family = brief.get("layout_family")
    family = getattr(family, "value", family)
    if not family or not sections:
        return None
    return "/".join([str(family), str(brief.get("headline_scale")), str(len(sections))])


def _quality_check(svg_markup: str, plan, png_path: Optional[Path],
                   width: int, height: int) -> List[str]:
    """Verify the artifacts actually contain this job's content and selected structure."""
    problems: List[str] = []

    root = None
    try:
        root = ET.fromstring(svg_markup)
    except ET.ParseError as e:
        problems.append(f"SVG is not well-formed XML: {e}")

    if len(svg_markup) < 800:
        problems.append(f"SVG is implausibly small ({len(svg_markup)} chars).")

    # The rendered title is upper-cased and truncated, so only the leading words can be
    # expected to appear.
    for word in [w for w in plan.headline.split() if len(w) > 3][:2]:
        if word.upper() not in svg_markup.upper():
            problems.append(f"Headline word '{word}' is missing from the rendered SVG.")

    if plan.source_url:
        domain = plan.source_url.split("//")[-1].split("/")[0]
        if domain and domain not in svg_markup:
            problems.append("Source domain is missing from the rendered SVG.")

    # Brand invariants that must survive every art-direction family.
    if "Legal Snaps" not in svg_markup:
        problems.append("Legal Snaps brand lockup is missing from the rendered SVG.")
    if plan.design_brief is not None:
        if "#CFA444" not in svg_markup:
            problems.append("Brand gold #CFA444 is missing from the dynamic layout.")
        if "#4A4C5A" not in svg_markup:
            problems.append("Brand charcoal #4A4C5A is missing from the dynamic layout.")
        if 'data-layout-family=' not in svg_markup:
            problems.append("Dynamic SVG does not declare its selected layout family.")

    brief = plan.design_brief
    if brief is not None and root is not None:
        expected_family = brief.layout_family.value
        actual_family = root.attrib.get("data-layout-family")
        if actual_family != expected_family:
            problems.append(
                f"Rendered layout family is '{actual_family}', brief selected '{expected_family}'."
            )
        try:
            bottom = float(root.attrib.get("data-content-bottom", "inf"))
            limit = float(root.attrib.get("data-canvas-bottom", "inf"))
        except ValueError:
            bottom = limit = float("inf")
            problems.append("Dynamic layout bounds are not numeric.")
        if bottom > limit + 1:
            problems.append(
                f"Dynamic layout overflows its canvas by {bottom - limit:.1f} design units."
            )
        if brief.layout_signature not in svg_markup:
            problems.append("Rendered layout signature does not match the validated brief.")
        if brief.layout_family.value == "chart_led":
            bars = [
                element
                for element in root.iter("{http://www.w3.org/2000/svg}rect")
                if element.attrib.get("fill") in {"#CFA444", "#232836"}
            ]
            chart = brief.chart
            expected_bars = len(chart.data) if chart else 0
            if len(bars) < expected_bars:
                problems.append(
                    f"Chart-led layout rendered {len(bars)} bars, expected {expected_bars}."
                )
            if chart:
                for datum in chart.data:
                    if datum.value_text not in svg_markup:
                        problems.append(
                            f"Chart value '{datum.value_text}' was not rendered verbatim."
                        )

    if png_path is not None:
        if not png_path.is_file():
            problems.append("PNG artifact is missing from storage.")
        else:
            data = png_path.read_bytes()
            if not data.startswith(PNG_MAGIC_BYTES):
                problems.append("PNG artifact has no PNG signature.")
            else:
                w, h = get_png_dimensions(data)
                if (w, h) != (width, height):
                    problems.append(f"PNG dimensions are {w}x{h}, expected {width}x{height}.")
                if len(data) < 8192:
                    problems.append(f"PNG is implausibly small ({len(data)} bytes).")

    return problems


async def run_pipeline(job_id: str, preferred_layout: Optional[str] = None):
    """
    Execute the 10-stage Legal Snaps pipeline.

    preferred_layout pins the composition when an editor has explicitly chosen one; the
    brief still has to ground every section in the record. Each stage performs its real
    operation before reporting progress, and any failure ends the job with the underlying
    """
    preferred_layout = preferred_layout or "briefing_sheet"
    job = get_job(job_id)
    if not job:
        logger.error("Job %s not found in database", job_id)
        return

    logs: List[str] = job.get("logs") or []
    warnings: List[str] = job.get("warnings") or []

    def stage_in_progress(stage_num: int, stage_key: JobStage, msg: str, pct: int):
        log_entry = f"[{stage_num}/10] {STAGE_NAMES.get(stage_num, '')}: {msg}"
        logs.append(log_entry)
        logger.info(log_entry)
        update_job(job_id, {
            "status": stage_key.value,
            "current_stage": stage_num,
            "progress_percent": pct,
            "logs": logs,
            "warnings": warnings,
        })

    def stage_done(stage_num: int, stage_key: JobStage, msg: str, pct: int):
        log_entry = f"[{stage_num}/10] {STAGE_NAMES.get(stage_num, '')} done: {msg}"
        logs.append(log_entry)
        logger.info(log_entry)
        update_job(job_id, {"progress_percent": pct, "logs": logs, "warnings": warnings})

    try:
        storage_dir = Path(settings.storage_dir)
        storage_dir.mkdir(parents=True, exist_ok=True)

        target_url = job.get("article_url")
        pdf_url = job.get("pdf_url")
        article_name = job.get("article_name")
        output_format = job.get("output_format", "both")
        want_artwork = bool(job.get("enable_image_generation", False))
        width = job.get("width", 800)
        height = job.get("height", 1240)

        # ------------------------------------------------------------------
        # Stage 1: Searching for the article
        # ------------------------------------------------------------------
        stage_in_progress(1, JobStage.SEARCHING, "Discovering legal sources for this topic...", 8)

        if target_url or pdf_url:
            direct = target_url or pdf_url
            candidates_to_try = [direct]
            stage_done(1, JobStage.SEARCHING, f"Using caller-supplied source URL {direct}", 14)
        else:
            if not article_name:
                raise PipelineError("No article name/topic or direct source URL was provided.")
            selected, candidates = await discover_sources(article_name)
            if not candidates:
                raise PipelineError(
                    f"Web search returned no results for '{article_name}'. "
                    "Check the search provider configuration or supply a direct URL."
                )
            candidates_to_try = [c.url for c in candidates]
            stage_done(
                1, JobStage.SEARCHING,
                f"{len(candidates)} candidates; best: {candidates[0].title} "
                f"({candidates[0].publisher}, credibility {candidates[0].credibility_score})",
                14,
            )

        # ------------------------------------------------------------------
        # Stage 2: Retrieving the source
        # ------------------------------------------------------------------
        extracted_raw = None
        source_meta = None
        last_error: Optional[str] = None

        for idx, candidate_url in enumerate(candidates_to_try):
            stage_in_progress(
                2, JobStage.RETRIEVING,
                f"Fetching source {idx + 1}/{len(candidates_to_try)}: {candidate_url}", 18
            )
            try:
                extracted_raw, source_meta = await retrieve_and_extract(
                    candidate_url, is_pdf=candidate_url.lower().endswith(".pdf")
                )
                if extracted_raw and extracted_raw.strip():
                    raw_len = len(extracted_raw.strip())
                    if raw_len >= MIN_SOURCE_CHARS or idx == len(candidates_to_try) - 1:
                        break
                    last_error = (
                        f"source {candidate_url} yielded only {raw_len} characters; "
                        "trying the next candidate"
                    )
                    logger.warning("Thin source skipped: %s", last_error)
                    extracted_raw, source_meta = None, None
            except Exception as e:
                last_error = str(e)
                logger.warning("Retrieval failed for %s: %s", candidate_url, e)

        if not extracted_raw or not source_meta:
            raise PipelineError(
                f"No candidate source could be retrieved. Last error: {last_error or 'empty extraction'}"
            )

        warnings.extend(source_meta.warnings)
        update_job(job_id, {
            "source_metadata": source_meta.model_dump(),
            "article_url": source_meta.url,
        })
        stage_done(
            2, JobStage.RETRIEVING,
            f"Retrieved {source_meta.text_length} chars via {source_meta.extraction_method} "
            f"from {source_meta.url}",
            28,
        )

        # ------------------------------------------------------------------
        # Stage 3: Extracting text
        # ------------------------------------------------------------------
        stage_in_progress(3, JobStage.EXTRACTING, "Sanitising source text and structuring sections...", 32)

        extraction = structure_legal_text(extracted_raw)
        if extraction.char_count < 300:
            raise PipelineError(
                f"Source produced only {extraction.char_count} characters of substantive legal text "
                f"from {source_meta.url}; the page is likely navigation-only or access-restricted."
            )
        warnings.extend(extraction.warnings)

        source_meta.word_count = count_words(extraction.text)
        source_meta.boilerplate_lines_removed = extraction.boilerplate_lines_removed
        source_meta.text_length = extraction.char_count
        update_job(job_id, {"source_metadata": source_meta.model_dump()})

        stage_done(
            3, JobStage.EXTRACTING,
            f"{extraction.line_count} lines / {source_meta.word_count} words kept, "
            f"{extraction.boilerplate_lines_removed} boilerplate lines dropped, "
            f"{len(extraction.section_headings)} section headings found",
            38,
        )

        # ------------------------------------------------------------------
        # Stage 4: Analysing legal information with Qwen
        # ------------------------------------------------------------------
        stage_in_progress(4, JobStage.ANALYSING, f"Running legal analysis with {settings.hf_text_model}...", 42)

        doc_title = article_name or source_meta.title or "Legal Document"
        corpus = build_analysis_corpus(extraction)
        legal_record = await analyze_legal_with_hf(corpus, doc_title, source_meta.url)

        update_job(job_id, {"legal_record": legal_record.model_dump()})
        stage_done(
            4, JobStage.ANALYSING,
            f"Structured record from {legal_record.analysis_source}: "
            f"{legal_record.case_name or legal_record.article_title} "
            f"({len(legal_record.material_facts)} facts, {len(legal_record.relevant_statutes)} provisions)",
            55,
        )

        # ------------------------------------------------------------------
        # Stage 5: Validating legal claims
        # ------------------------------------------------------------------
        stage_in_progress(5, JobStage.VALIDATING, "Auditing claims against the retrieved source text...", 58)

        validation = validate_legal_record(legal_record, extraction.text)
        warnings.extend(validation.warnings)
        update_job(job_id, {"validation_summary": validation.model_dump()})

        if validation.has_critical_unverified:
            logger.warning(
                "Job %s: operative holding is not verifiable against the source (%d/%d claims verified)",
                job_id, validation.verified_claims, validation.total_claims
            )
        stage_done(
            5, JobStage.VALIDATING,
            f"{validation.verified_claims}/{validation.total_claims} claims verified; "
            f"{validation.unverified_claims} unverified",
            66,
        )

        # ------------------------------------------------------------------
        # Stage 6: Designing the infographic
        # ------------------------------------------------------------------
        stage_in_progress(6, JobStage.DESIGNING, "Choosing article-specific art direction...", 68)

        # Variation has to be measured against what was just published, otherwise a run of
        # similar judgments quietly produces the same poster shape every time.
        recent_layouts: List[str] = []
        for previous in list_jobs(limit=12):
            if previous.get("job_id") == job_id:
                continue
            key = _stored_layout_key(previous)
            if key:
                recent_layouts.append(key)
        design_brief = await generate_design_brief_with_hf(
            legal_record,
            validation,
            avoid_layouts=recent_layouts,
            preferred_family=preferred_layout,
        )
        if design_brief.layout_key in recent_layouts and preferred_layout is None:
            warnings.append(
                "This poster uses the same composition as a recent job; the art direction "
                f"model kept choosing {design_brief.layout_family.value} for this record."
            )
        update_job(job_id, {"design_brief": design_brief.model_dump()})

        plan = plan_infographic_content(
            legal_record, validation, source_meta, design_brief=design_brief
        )
        update_job(job_id, {"content_plan": plan.model_dump()})
        stage_done(
            6, JobStage.DESIGNING,
            f"Layout {design_brief.layout_family.value}; signature {design_brief.layout_signature}; "
            f"headline '{plan.headline[:50]}'",
            74,
        )

        # ------------------------------------------------------------------
        # Stage 7: Generating optional illustrations
        # ------------------------------------------------------------------
        stage_in_progress(7, JobStage.GENERATING_ARTWORK, "Preparing artwork for this job...", 76)

        artwork_data_uri: Optional[str] = None
        artwork_filename: Optional[str] = None
        illustration_uris: dict = {}

        if not want_artwork:
            stage_done(7, JobStage.GENERATING_ARTWORK, "skipped - artwork disabled for this request", 80)
        else:
            artwork_path = storage_dir / f"{job_id}_artwork.png"
            # The briefing sheet carries a picture on each card, so Qwen names those
            # pictures and Krea draws them in parallel with the hero illustration.
            wants_card_art = design_brief.layout_family.value == "briefing_sheet"
            if wants_card_art:
                (ok, err), (illustration_uris, art_warnings) = await asyncio.gather(
                    generate_legal_artwork(str(artwork_path), plan),
                    generate_explainer_illustrations(
                        str(storage_dir), job_id, plan, legal_record
                    ),
                )
                warnings.extend(art_warnings)
            else:
                ok, err = await generate_legal_artwork(str(artwork_path), plan)

            if ok and artwork_path.is_file():
                artwork_data_uri = "data:image/png;base64," + base64.b64encode(
                    artwork_path.read_bytes()
                ).decode("ascii")
                artwork_filename = artwork_path.name
                update_job(job_id, {"artwork_filename": artwork_filename})
                detail = f"generated with {settings.hf_image_model} ({artwork_path.stat().st_size} bytes)"
                if wants_card_art:
                    detail += f"; {len(illustration_uris)} card pictures embedded"
                stage_done(7, JobStage.GENERATING_ARTWORK, detail, 80)
            else:
                message = err or "artwork generation returned no file"
                raise PipelineError(
                    f"Hugging Face artwork generation failed with {settings.hf_image_model}: "
                    f"{message}. No substitute artwork was used."
                )

        svg_markup = generate_legal_snaps_svg(
            plan,
            width=width,
            height=height,
            artwork_base64_data_uri=artwork_data_uri,
            record=legal_record,
            illustrations=illustration_uris,
        )
        svg_filename = f"{job_id}_infographic.svg"
        svg_path = storage_dir / svg_filename
        svg_path.write_text(svg_markup, encoding="utf-8")
        update_job(job_id, {"svg_filename": svg_filename})

        # ------------------------------------------------------------------
        # Stage 8: Rendering the final image
        # ------------------------------------------------------------------
        png_filename: Optional[str] = None
        png_path: Optional[Path] = None

        if output_format == "svg":
            stage_in_progress(8, JobStage.RENDERING_IMAGE, "Rasterisation skipped (SVG-only output)", 86)
            stage_done(8, JobStage.RENDERING_IMAGE, "no PNG requested", 88)
        else:
            stage_in_progress(8, JobStage.RENDERING_IMAGE, f"Rasterising this job's SVG to {width}x{height} PNG...", 86)
            png_path = storage_dir / f"{job_id}_infographic.png"
            _render_png(svg_markup, png_path, width, height)
            png_filename = png_path.name
            update_job(job_id, {"png_filename": png_filename})
            stage_done(8, JobStage.RENDERING_IMAGE,
                       f"rendered {png_path.stat().st_size} bytes from this job's SVG", 90)

        # ------------------------------------------------------------------
        # Stage 9: Running quality checks
        # ------------------------------------------------------------------
        stage_in_progress(9, JobStage.CHECKING_QUALITY, "Validating markup, dimensions and article-specific content...", 92)

        problems = _quality_check(svg_markup, plan, png_path, width, height)
        if illustration_uris and 'class="card-art"' not in svg_markup:
            problems.append(
                f"{len(illustration_uris)} card pictures were generated but none reached the poster."
            )
        if problems:
            raise PipelineError("Quality checks failed: " + "; ".join(problems))

        stage_done(9, JobStage.CHECKING_QUALITY, "XML well-formed, dimensions and content verified", 98)

        # ------------------------------------------------------------------
        # Stage 10: Saving the output
        # ------------------------------------------------------------------
        stage_in_progress(10, JobStage.SAVING, "Finalising artifact storage...", 99)

        if not svg_path.is_file():
            raise PipelineError(f"SVG artifact vanished before save: {svg_path}")
        if png_path is not None and not png_path.is_file():
            raise PipelineError(f"PNG artifact vanished before save: {png_path}")

        update_job(job_id, {
            "status": JobStage.COMPLETED.value,
            "current_stage": 10,
            "progress_percent": 100,
            "svg_filename": svg_filename,
            "png_filename": png_filename,
            "artwork_filename": artwork_filename,
            "logs": logs,
            "warnings": warnings,
        })
        logger.info("Pipeline completed for job %s", job_id)

    except Exception as e:
        detail = str(e).strip() or type(e).__name__
        if isinstance(e, HFProviderError):
            detail = f"Hugging Face legal analysis failed: {detail}"
        logger.exception("Pipeline failed for job %s: %s", job_id, detail)
        logs.append(f"FAILURE: {detail}")
        update_job(job_id, {
            "status": JobStage.FAILED.value,
            "error_message": detail[:2000],
            "logs": logs,
            "warnings": warnings,
        })
