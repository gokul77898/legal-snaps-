'use client';

import React, { useState } from 'react';
import { ArrowRight, ChevronDown, Loader2, Plus } from 'lucide-react';

interface ArticleInputFormProps {
  onGenerate: (payload: {
    article_name?: string;
    article_url?: string;
    pdf_url?: string;
    language: string;
    output_format: string;
    enable_image_generation: boolean;
    width: number;
    height: number;
  }) => void;
  isLoading: boolean;
}

const PRESET_TOPICS = [
  'Sukanya Shantha v. Union of India',
  'K.S. Puttaswamy v. Union of India',
  'Brown v. Board of Education',
  'Donoghue v Stevenson',
];

export const ArticleInputForm: React.FC<ArticleInputFormProps> = ({ onGenerate, isLoading }) => {
  const [articleName, setArticleName] = useState('');
  const [articleUrl, setArticleUrl] = useState('');
  const [pdfUrl, setPdfUrl] = useState('');
  const [language, setLanguage] = useState('en');
  const [outputFormat, setOutputFormat] = useState('both');
  const [enableArtwork, setEnableArtwork] = useState(true);
  const [dimensions, setDimensions] = useState('1080x1350');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!articleName.trim() && !articleUrl.trim() && !pdfUrl.trim()) {
      setError('Provide a case name, a direct source URL, or a PDF link.');
      return;
    }

    const [wStr, hStr] = dimensions.split('x');
    const width = parseInt(wStr, 10) || 1080;
    const height = parseInt(hStr, 10) || 1350;

    onGenerate({
      article_name: articleName.trim() || undefined,
      article_url: articleUrl.trim() || undefined,
      pdf_url: pdfUrl.trim() || undefined,
      language,
      output_format: outputFormat,
      enable_image_generation: enableArtwork,
      width,
      height,
    });
  };

  const handleSelectPreset = (topic: string) => {
    setArticleName(topic);
    setArticleUrl('');
    setPdfUrl('');
    setError(null);
  };

  const segBase =
    'block rounded-full px-3.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] transition-all duration-300 peer-checked:bg-paper peer-checked:text-ink peer-checked:shadow-[0_8px_20px_-10px_rgba(0,0,0,0.95)] peer-focus-visible:outline peer-focus-visible:outline-1 peer-focus-visible:outline-gold';

  return (
    <div
      className="glass glass-spot relative overflow-hidden p-6 sm:p-8"
      onPointerMove={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        e.currentTarget.style.setProperty('--mx', `${e.clientX - rect.left}px`);
        e.currentTarget.style.setProperty('--my', `${e.clientY - rect.top}px`);
      }}
    >
      <div
        className="pointer-events-none absolute -right-10 -top-16 h-48 w-48 rounded-full bg-gold/[0.06] blur-3xl"
        style={{ position: 'absolute' }}
        aria-hidden="true"
      />

      <div className="relative flex items-start justify-between gap-4">
        <div>
          <span className="eyebrow">Intake &middot; commission</span>
          <h3 className="display mt-3 text-[1.8rem] leading-none text-paper">
            A case, a citation, a question.
          </h3>
        </div>
        <span className="meta hidden text-right text-[9px] uppercase leading-relaxed tracking-[0.16em] text-paper/30 sm:block">
          Searches
          <br />
          primary sources
        </span>
      </div>

      <form onSubmit={handleSubmit} className="relative mt-8 space-y-7">
        {error && (
          <p
            role="alert"
            className="animate-rise rounded-lg border border-warn/25 bg-warn/[0.05] px-3.5 py-2.5 font-mono text-[11px] leading-relaxed text-warn"
          >
            {error}
          </p>
        )}

        <div>
          <label htmlFor="case-name" className="field-label">
            Case name, citation, or legal topic
          </label>
          <input
            id="case-name"
            type="text"
            value={articleName}
            onChange={(e) => setArticleName(e.target.value)}
            placeholder="Justice K.S. Puttaswamy v. Union of India, (2017) 10 SCC 1"
            disabled={isLoading}
            autoComplete="off"
            className="field field-lg"
          />

          <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-2">
            <span className="meta mr-1 text-[9px] uppercase tracking-[0.18em] text-paper/30">
              Try
            </span>
            {PRESET_TOPICS.map((topic) => (
              <button
                key={topic}
                type="button"
                onClick={() => handleSelectPreset(topic)}
                disabled={isLoading}
                className="cursor-pointer rounded-full border border-line px-3 py-1 font-mono text-[9.5px] tracking-[0.02em] text-paper/45 transition-all duration-300 hover:border-gold/40 hover:bg-gold/[0.06] hover:text-gold-bright disabled:opacity-40"
              >
                {topic}
              </button>
            ))}
          </div>
        </div>

        <div>
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            aria-expanded={showAdvanced}
            className="btn-quiet group cursor-pointer disabled:opacity-40"
            disabled={isLoading}
          >
            <span className="flex h-4 w-4 items-center justify-center rounded-full border border-line-strong transition-colors duration-300 group-hover:border-gold/50">
              <Plus
                className={`h-2.5 w-2.5 transition-transform duration-300 ${
                  showAdvanced ? 'rotate-45' : ''
                }`}
              />
            </span>
            <span>Direct source &amp; output settings</span>
          </button>

          {showAdvanced && (
            <div className="glass-sunken animate-fade mt-5 grid gap-x-6 gap-y-5 p-5 sm:grid-cols-2">
              <div>
                <label htmlFor="article-url" className="field-label">
                  Direct article or judgment URL
                </label>
                <input
                  id="article-url"
                  type="url"
                  value={articleUrl}
                  onChange={(e) => setArticleUrl(e.target.value)}
                  placeholder="https://indiankanoon.org/doc/…"
                  disabled={isLoading}
                  className="field text-[12px]"
                />
              </div>

              <div>
                <label htmlFor="pdf-url" className="field-label">
                  Direct PDF judgment
                </label>
                <input
                  id="pdf-url"
                  type="url"
                  value={pdfUrl}
                  onChange={(e) => setPdfUrl(e.target.value)}
                  placeholder="https://…/decision.pdf"
                  disabled={isLoading}
                  className="field text-[12px]"
                />
              </div>

              <div>
                <label htmlFor="dimensions" className="field-label">
                  Canvas
                </label>
                <div className="relative">
                  <select
                    id="dimensions"
                    value={dimensions}
                    onChange={(e) => setDimensions(e.target.value)}
                    disabled={isLoading}
                    className="field cursor-pointer appearance-none pr-9 text-[12px]"
                  >
                    <option value="1080x1350" className="bg-ink-raised">
                      1080 × 1350 — editorial portrait
                    </option>
                    <option value="1200x1200" className="bg-ink-raised">
                      1200 × 1200 — editorial square
                    </option>
                    <option value="1200x675" className="bg-ink-raised">
                      1200 × 675 — landscape
                    </option>
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-paper/35" />
                </div>
              </div>

              <div>
                <label htmlFor="language" className="field-label">
                  Language
                </label>
                <div className="relative">
                  <select
                    id="language"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    disabled={isLoading}
                    className="field cursor-pointer appearance-none pr-9 text-[12px]"
                  >
                    <option value="en" className="bg-ink-raised">
                      English — court terminology
                    </option>
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-paper/35" />
                </div>
              </div>

              <p className="meta text-[9px] leading-relaxed text-paper/30 sm:col-span-2">
                A name searches the open web and Indian Kanoon. A URL bypasses search and reads
                the page directly.
              </p>
            </div>
          )}
        </div>

        <div className="grid gap-7 border-t border-line pt-6 sm:grid-cols-2">
          <fieldset>
            <legend className="field-label mb-3">Artifacts</legend>
            <div className="inline-flex items-center rounded-full border border-line bg-ink-sunken/60 p-1">
              <label className="cursor-pointer">
                <input
                  type="radio"
                  name="format"
                  value="both"
                  checked={outputFormat === 'both'}
                  onChange={() => setOutputFormat('both')}
                  disabled={isLoading}
                  className="peer sr-only"
                />
                <span className={segBase}>SVG + PNG</span>
              </label>
              <label className="cursor-pointer">
                <input
                  type="radio"
                  name="format"
                  value="svg"
                  checked={outputFormat === 'svg'}
                  onChange={() => setOutputFormat('svg')}
                  disabled={isLoading}
                  className="peer sr-only"
                />
                <span className={segBase}>SVG only</span>
              </label>
            </div>
          </fieldset>

          <fieldset>
            <legend className="field-label mb-3">Artwork</legend>
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-[12px] text-paper/80">FLUX.1 illustration</div>
                <div className="meta mt-0.5 text-[10px] normal-case tracking-normal">
                  Composited under the typeset layout
                </div>
              </div>
              <label className="relative inline-flex cursor-pointer items-center">
                <input
                  type="checkbox"
                  checked={enableArtwork}
                  onChange={(e) => setEnableArtwork(e.target.checked)}
                  disabled={isLoading}
                  className="peer sr-only"
                />
                <span className="relative h-6 w-11 rounded-full border border-line-strong bg-white/[0.04] transition-colors duration-300 peer-checked:border-gold/70 peer-checked:bg-gold/85 peer-focus-visible:outline peer-focus-visible:outline-1 peer-focus-visible:outline-gold peer-focus-visible:outline-offset-2" />
                <span className="pointer-events-none absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-paper/60 shadow-[0_2px_8px_rgba(0,0,0,0.6)] transition-all duration-300 peer-checked:translate-x-5 peer-checked:bg-ink" />
              </label>
            </div>
          </fieldset>
        </div>

        <div className="flex flex-col gap-5 border-t border-line pt-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-4">
            <button type="submit" disabled={isLoading} className="btn-gold group">
              {isLoading ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Working the record…</span>
                </>
              ) : (
                <>
                  <span>Generate page</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-0.5" />
                </>
              )}
            </button>
            <span className="meta text-[10px] text-paper/35">Typically one to two minutes</span>
          </div>

          <p className="meta max-w-[250px] text-[10px] leading-relaxed text-paper/30">
            If the provider rejects the request, the record stops there and states why.
          </p>
        </div>
      </form>
    </div>
  );
};
