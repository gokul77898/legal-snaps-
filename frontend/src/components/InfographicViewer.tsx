'use client';

import React, { useState } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { JobResponse } from '@/types';
import { getSvgDownloadUrl, getPngDownloadUrl, getPreviewUrl } from '@/lib/api';

interface InfographicViewerProps {
  job: JobResponse;
}

export const InfographicViewer: React.FC<InfographicViewerProps> = ({ job }) => {
  const [zoom, setZoom] = useState(1);
  const [viewMode, setViewMode] = useState<'svg' | 'png'>(job.has_png ? 'png' : 'svg');

  // Re-render the <img> when the backend artifact changes, without calling Date.now()
  // during render (React requires render to be pure).
  const cacheKey = encodeURIComponent(job.updated_at);
  const previewSvgUrl = `${getPreviewUrl(job.job_id, 'svg')}&v=${cacheKey}`;
  const previewPngUrl = `${getPreviewUrl(job.job_id, 'png')}&v=${cacheKey}`;
  const svgUrl = getSvgDownloadUrl(job.job_id);
  const pngUrl = getPngDownloadUrl(job.job_id);
  const fullscreenUrl = job.has_png ? previewPngUrl : previewSvgUrl;

  const handleZoomIn = () => setZoom((prev) => Math.min(prev + 0.25, 2.5));
  const handleZoomOut = () => setZoom((prev) => Math.max(prev - 0.25, 0.5));
  const handleResetZoom = () => setZoom(1);

  return (
    <div className="glass flex flex-col overflow-hidden">
      <div className="flex flex-wrap items-end justify-between gap-5 px-6 py-5 sm:px-7">
        <div>
          <span className="eyebrow">Artifact</span>
          <h3 className="display mt-2 text-[1.6rem] leading-none text-paper">
            The composed page.
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          <div className="flex items-center gap-4 font-mono text-[9.5px] uppercase tracking-[0.16em]">
            <button
              onClick={() => setViewMode('png')}
              disabled={!job.has_png}
              aria-pressed={viewMode === 'png'}
              className={`relative cursor-pointer pb-1 transition-colors duration-300 disabled:cursor-not-allowed disabled:opacity-30 ${
                viewMode === 'png' ? 'text-gold' : 'text-paper/35 hover:text-paper/70'
              }`}
            >
              Poster
              {viewMode === 'png' && <span aria-hidden="true" className="tab-underline" />}
            </button>
            <button
              onClick={() => setViewMode('svg')}
              disabled={!job.has_svg}
              aria-pressed={viewMode === 'svg'}
              className={`relative cursor-pointer pb-1 transition-colors duration-300 disabled:cursor-not-allowed disabled:opacity-30 ${
                viewMode === 'svg' ? 'text-gold' : 'text-paper/35 hover:text-paper/70'
              }`}
            >
              Vector
              {viewMode === 'svg' && <span aria-hidden="true" className="tab-underline" />}
            </button>
          </div>

          <span className="hidden h-4 w-px bg-line sm:block" aria-hidden="true" />

          <div className="glass-quiet flex items-center gap-1.5 rounded-full px-2 py-1 font-mono text-[10px] text-paper/45">
            <button
              onClick={handleZoomOut}
              aria-label="Zoom out"
              className="flex h-5 w-5 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-white/[0.06] hover:text-gold"
            >
              &minus;
            </button>
            <span className="w-9 text-center tabular-nums text-paper/65">
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={handleZoomIn}
              aria-label="Zoom in"
              className="flex h-5 w-5 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-white/[0.06] hover:text-gold"
            >
              +
            </button>
            <button
              onClick={handleResetZoom}
              className="ml-1 cursor-pointer px-1 uppercase tracking-[0.14em] transition-colors hover:text-gold"
            >
              Reset
            </button>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-y border-line bg-white/[0.012] px-6 py-2.5 sm:px-7">
        <div className="flex items-center gap-3 font-mono text-[9px] uppercase tracking-[0.14em] text-paper/35">
          <span>{job.output_format.toUpperCase()}</span>
          <span aria-hidden="true">&middot;</span>
          <span>{job.has_png ? 'Raster export' : 'Vector only'}</span>
          {job.artwork_generated && (
            <>
              <span aria-hidden="true">&middot;</span>
              <span className="text-gold/60">FLUX artwork</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-4">
          {job.has_svg && (
            <a href={svgUrl} download className="btn-quiet">
              SVG &darr;
            </a>
          )}
          {job.has_png && (
            <a
              href={pngUrl}
              download
              className="rounded-full border border-gold/50 px-3 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-gold transition-colors duration-300 hover:bg-gold hover:text-ink"
            >
              PNG &darr;
            </a>
          )}
        </div>
      </div>

      <div className="artifact-stage relative flex min-h-[520px] max-h-[760px] items-center justify-center overflow-auto p-4 sm:p-8">
        <div
          className="artifact-frame rim relative origin-center p-1"
          style={{ transform: `scale(${zoom})` }}
        >
          {viewMode === 'png' && job.has_png ? (
            <img
              src={previewPngUrl}
              alt={job.article_name || 'Legal Snaps infographic'}
              className="block h-auto w-full max-w-[860px] object-contain"
            />
          ) : viewMode === 'svg' && job.has_svg ? (
            <img
              src={previewSvgUrl}
              alt={job.article_name || 'Legal Snaps infographic'}
              className="block h-auto w-full max-w-[860px] bg-ink object-contain"
            />
          ) : (
            <div className="px-12 py-16 text-center">
              <p className="display text-[1.1rem] italic text-paper/50">
                The page is still being set.
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-6 py-3.5 sm:px-7">
        <dl className="flex flex-wrap items-center gap-x-5 gap-y-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-paper/35">
          <div className="flex items-center gap-1.5">
            <dt>Job</dt>
            <dd className="text-paper/65">{job.job_id.slice(0, 13)}</dd>
          </div>
          <div className="flex items-center gap-1.5">
            <dt>Format</dt>
            <dd className="text-paper/65">{job.output_format.toUpperCase()}</dd>
          </div>
          {job.analysis_source && (
            <div className="flex items-center gap-1.5">
              <dt>Analysis</dt>
              <dd className="normal-case tracking-normal text-paper/65">{job.analysis_source}</dd>
            </div>
          )}
          {job.has_png && (
            <div className="flex items-center gap-1.5">
              <dt>Composition</dt>
              <dd className="text-paper/65">
                {job.artwork_generated ? 'FLUX artwork · SVG type' : 'SVG type only'}
              </dd>
            </div>
          )}
        </dl>

        <a
          href={fullscreenUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-quiet group"
        >
          Fullscreen
          <ArrowUpRight className="h-3 w-3 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
        </a>
      </div>
    </div>
  );
};
