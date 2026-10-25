'use client';

import React, { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUpRight, Check } from 'lucide-react';
import { Header } from '@/components/Header';
import { ArticleInputForm } from '@/components/ArticleInputForm';
import { ProcessingTimeline } from '@/components/ProcessingTimeline';
import { InfographicViewer } from '@/components/InfographicViewer';
import { LegalValidationCard } from '@/components/LegalValidationCard';
import { HistoryDrawer } from '@/components/HistoryDrawer';
import { AmbientField } from '@/components/AmbientField';
import { Reveal } from '@/components/Reveal';
import { JobResponse, JobListItem, HealthStatus } from '@/types';
import {
  createInfographic,
  getInfographic,
  listInfographics,
  deleteInfographic,
  getHealth,
} from '@/lib/api';

function SectionHead({
  number,
  title,
  note,
}: {
  number: string;
  title: string;
  note?: string;
}) {
  return (
    <Reveal className="flex flex-col gap-3 sm:flex-row sm:items-baseline sm:justify-between">
      <div className="flex items-baseline gap-4">
        <span className="relative font-mono text-[10px] tracking-[0.2em] text-gold">
          {number}
          <span
            aria-hidden="true"
            className="absolute -bottom-2 left-0 h-px w-full bg-gold/35"
          />
        </span>
        <h2 className="display text-[clamp(1.85rem,3.4vw,2.6rem)] leading-none text-paper">
          {title}
        </h2>
      </div>
      {note && (
        <span className="meta hidden text-[10px] uppercase tracking-[0.18em] sm:block">
          {note}
        </span>
      )}
    </Reveal>
  );
}

function DossierRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="group flex items-baseline justify-between gap-4 border-t border-line py-2.5 transition-colors duration-300 first:border-t-0 first:pt-0 hover:border-gold/25">
      <dt className="meta text-[10px] uppercase tracking-[0.15em] transition-colors duration-300 group-hover:text-paper/70">
        {label}
      </dt>
      <dd
        className="max-w-[62%] truncate text-right font-mono text-[10.5px] text-paper/75"
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}

const PRINCIPLES = [
  {
    n: '01',
    title: 'Ratio, not rhetoric',
    body: 'The holding is separated from the arguments of the parties before anything is typeset.',
  },
  {
    n: '02',
    title: 'Quotation, not paraphrase',
    body: 'Quotes that do not appear verbatim in the retrieved source are struck from the record.',
  },
  {
    n: '03',
    title: 'No silent fallback',
    body: 'If the provider rejects the request, the job fails and says why. Nothing is fabricated.',
  },
];

const TICKER = [
  'Ratio decidendi',
  'Obiter dicta',
  'Audi alteram partem',
  'Stare decisis',
  'Res judicata',
  'Certiorari',
  'Mandamus',
  'Habeas corpus',
  'Ultra vires',
  'Natural justice',
];

const SURVIVES = [
  {
    n: '01',
    title: 'Facts',
    body: 'Only what the retrieved text states, with the source recorded beside it.',
  },
  {
    n: '02',
    title: 'Quotations',
    body: 'Verified verbatim. Anything that does not match is removed and disclosed.',
  },
  {
    n: '03',
    title: 'Uncertainty',
    body: 'Named openly rather than filled in from general knowledge.',
  },
];

export default function Home() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [history, setHistory] = useState<JobListItem[]>([]);
  const [activeJob, setActiveJob] = useState<JobResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [year, setYear] = useState<number | null>(null);

  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const heroRef = useRef<HTMLElement | null>(null);
  const dossierRef = useRef<HTMLDivElement | null>(null);

  // Hoisted so the mount effect below can call them before their definitions.
  async function startPolling(jobId: string) {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);

    pollIntervalRef.current = setInterval(async () => {
      try {
        const updated = await getInfographic(jobId);
        setActiveJob(updated);

        if (updated.status === 'completed' || updated.status === 'failed') {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          setIsSubmitting(false);
          const freshHistory = await listInfographics(30);
          setHistory(freshHistory);
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 1500);
  }

  async function loadJobDetails(jobId: string) {
    try {
      const job = await getInfographic(jobId);
      setActiveJob(job);
      if (job.status !== 'completed' && job.status !== 'failed') {
        startPolling(jobId);
      }
    } catch (e) {
      console.error('Error loading job:', e);
    }
  }

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const h = await getHealth();
        if (cancelled) return;
        setHealth(h);

        const hist = await listInfographics(30);
        if (cancelled) return;
        setHistory(hist);

        if (hist.length > 0) {
          await loadJobDetails(hist[0].job_id);
        }
      } catch (e) {
        console.error('Error fetching initial data:', e);
      }
    })();

    return () => {
      cancelled = true;
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Read the clock after mount so the prerender stays deterministic.
  useEffect(() => {
    setYear(new Date().getFullYear());
  }, []);

  const handleGenerate = async (payload: {
    article_name?: string;
    article_url?: string;
    pdf_url?: string;
    language: string;
    output_format: string;
    enable_image_generation: boolean;
    width: number;
    height: number;
  }) => {
    setIsSubmitting(true);
    setGeneralError(null);

    try {
      const newJob = await createInfographic(payload);
      setActiveJob(newJob);
      startPolling(newJob.job_id);
      // Bring the execution record into view once a commission is accepted.
      requestAnimationFrame(() => {
        document.getElementById('execution')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    } catch (err) {
      setGeneralError(err instanceof Error ? err.message : 'Failed to submit generation job');
      setIsSubmitting(false);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    try {
      const ok = await deleteInfographic(jobId);
      if (ok) {
        setHistory((prev) => prev.filter((item) => item.job_id !== jobId));
        if (activeJob?.job_id === jobId) {
          setActiveJob(null);
        }
      }
    } catch (e) {
      console.error('Failed to delete job:', e);
    }
  };

  const handleSelectJobFromHistory = (jobId: string) => {
    loadJobDetails(jobId);
    setIsHistoryOpen(false);
  };

  const handleHeroMove = (event: React.MouseEvent<HTMLElement>) => {
    const el = heroRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty('--mx', `${((event.clientX - rect.left) / rect.width) * 100}%`);
    el.style.setProperty('--my', `${((event.clientY - rect.top) / rect.height) * 100}%`);
  };

  const handleDossierMove = (event: React.MouseEvent<HTMLDivElement>) => {
    const el = dossierRef.current;
    if (!el) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const rect = el.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - 0.5;
    const y = (event.clientY - rect.top) / rect.height - 0.5;
    el.style.transform = `perspective(1100px) rotateX(${(-y * 4).toFixed(2)}deg) rotateY(${(x * 6).toFixed(2)}deg) translateY(-2px)`;
  };

  const handleDossierLeave = () => {
    if (dossierRef.current) dossierRef.current.style.transform = '';
  };

  const providerLine = !health
    ? 'Connecting to provider'
    : health.provider_configured
      ? 'Provider token present'
      : 'Provider token missing';

  const providerShort = !health
    ? 'Connecting'
    : health.provider_configured
      ? 'Provider online'
      : 'Token required';

  return (
    <div className="relative z-10 flex min-h-screen flex-col">
      <AmbientField />

      <Header
        health={health}
        onOpenHistory={() => setIsHistoryOpen(true)}
        historyCount={history.length}
        hasActiveJob={Boolean(activeJob)}
      />

      <main className="flex-1">
        {/* Hero */}
        <section ref={heroRef} id="top" className="hero" onMouseMove={handleHeroMove}>
          <div className="hero__spot" aria-hidden="true" />

          <div className="shell pt-[clamp(3.25rem,7vw,6rem)] pb-[clamp(3rem,6vw,5.5rem)]">
            <div className="grid gap-12 lg:grid-cols-12 lg:gap-10">
              <div className="lg:col-span-7 xl:col-span-8">
                <div
                  className="hero-fade flex flex-wrap items-center gap-3"
                  style={{ animationDelay: '40ms' }}
                >
                  <span className="eyebrow">Legal Snaps</span>
                  <span className="gold-rule" />
                  <span className="meta text-[10px] uppercase tracking-[0.18em]">
                    Qwen 2.5 &middot; FLUX.1
                  </span>
                  <span className="hidden h-3 w-px bg-line sm:block" aria-hidden="true" />
                  <span className="meta hidden text-[10px] uppercase tracking-[0.18em] text-paper/35 sm:block">
                    Chamber edition
                  </span>
                </div>

                <h1 className="display mt-7 text-[clamp(2.8rem,8vw,6rem)] leading-[0.92] text-paper">
                  <span className="hero-line">
                    <span>The holding,</span>
                  </span>
                  <span className="hero-line">
                    <span>
                      <em className="hero-underline italic text-gold-bright">
                        set in type.
                        <svg viewBox="0 0 300 14" preserveAspectRatio="none" aria-hidden="true">
                          <defs>
                            <linearGradient id="hero-underline" x1="0" x2="1" y1="0" y2="0">
                              <stop offset="0%" stopColor="#cfa444" stopOpacity="0.15" />
                              <stop offset="35%" stopColor="#edd7a4" stopOpacity="0.9" />
                              <stop offset="100%" stopColor="#cfa444" stopOpacity="0.35" />
                            </linearGradient>
                          </defs>
                          <path
                            d="M2 9 C 70 4, 160 3, 298 7"
                            fill="none"
                            stroke="url(#hero-underline)"
                            strokeWidth="2.5"
                            strokeLinecap="round"
                          />
                        </svg>
                      </em>
                    </span>
                  </span>
                </h1>

                <p
                  className="hero-fade mt-8 max-w-xl text-[15px] leading-[1.8] text-paper/[0.58]"
                  style={{ animationDelay: '300ms' }}
                >
                  Give the engine a case name. It retrieves the primary judgment, separates the
                  ratio from argument, audits every claim against the source text, and composes a
                  single editorial page for publication.
                </p>

                <div
                  className="hero-fade mt-8 flex flex-wrap items-center gap-x-6 gap-y-3"
                  style={{ animationDelay: '380ms' }}
                >
                  <a href="#intake" className="btn-gold group">
                    <span>Commission a page</span>
                    <ArrowDown className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-y-0.5" />
                  </a>
                  <a href="#method" className="btn-quiet group">
                    Read the method
                    <span className="h-px w-6 bg-gold/40 transition-all duration-300 group-hover:w-9 group-hover:bg-gold" />
                    <ArrowUpRight className="h-3 w-3" />
                  </a>
                </div>

                <dl
                  className="hero-fade mt-11 grid max-w-2xl grid-cols-1 gap-x-8 gap-y-1 sm:grid-cols-3"
                  style={{ animationDelay: '460ms' }}
                >
                  <div className="stat-cell">
                    <dt className="meta flex items-baseline justify-between text-[9px] uppercase tracking-[0.18em]">
                      <span>Retrieval</span>
                      <span className="font-mono text-gold/50">01</span>
                    </dt>
                    <dd className="mt-2 pb-2 text-[12.5px] text-paper/80">
                      Indian Kanoon &amp; DuckDuckGo
                    </dd>
                  </div>
                  <div className="stat-cell">
                    <dt className="meta flex items-baseline justify-between text-[9px] uppercase tracking-[0.18em]">
                      <span>Analysis</span>
                      <span className="font-mono text-gold/50">02</span>
                    </dt>
                    <dd className="mt-2 pb-2 text-[12.5px] text-paper/80">
                      Qwen 2.5 &middot; 72B
                    </dd>
                  </div>
                  <div className="stat-cell">
                    <dt className="meta flex items-baseline justify-between text-[9px] uppercase tracking-[0.18em]">
                      <span>Typesetting</span>
                      <span className="font-mono text-gold/50">03</span>
                    </dt>
                    <dd className="mt-2 pb-2 text-[12.5px] text-paper/80">
                      Deterministic SVG
                    </dd>
                  </div>
                </dl>
              </div>

              {/* Dossier */}
              <div className="lg:col-span-5 xl:col-span-4">
                <Reveal delay={120}>
                  <div
                    ref={dossierRef}
                    className="dossier glass relative p-6 sm:p-7"
                    onMouseMove={handleDossierMove}
                    onMouseLeave={handleDossierLeave}
                  >
                    <span className="dossier__float">
                      <span
                        aria-hidden="true"
                        className={`h-1.5 w-1.5 rounded-full ${
                          health?.provider_configured ? 'pulse-dot bg-ok' : 'bg-warn'
                        }`}
                      />
                      {providerShort}
                    </span>

                    <div className="flex items-center justify-between">
                      <span className="eyebrow">Dossier</span>
                      <span className="meta text-[9px] uppercase tracking-[0.2em] text-paper/28">
                        No. 001
                      </span>
                    </div>

                    <p className="display mt-4 text-[1.7rem] leading-none text-paper">
                      The instruments.
                    </p>

                    <dl className="mt-6">
                      <DossierRow
                        label="Reasoning"
                        value={health?.analysis_model || 'Qwen/Qwen2.5-72B-Instruct'}
                      />
                      <DossierRow
                        label="Artwork"
                        value={health?.image_model || 'black-forest-labs/FLUX.1-dev'}
                      />
                      <DossierRow
                        label="Rasteriser"
                        value={
                          health
                            ? health.renderer_available
                              ? 'resvg'
                              : 'unavailable'
                            : 'checking'
                        }
                      />
                      <DossierRow
                        label="Archive"
                        value={
                          health
                            ? health.storage_writable
                              ? 'writable'
                              : 'unavailable'
                            : 'checking'
                        }
                      />
                    </dl>

                    <div className="mt-6 border-t border-line pt-4">
                      <p className="display text-[1.05rem] italic leading-snug text-paper/70">
                        &ldquo;No claim renders unverified.&rdquo;
                      </p>
                      <p className="meta mt-2 text-[9px] uppercase tracking-[0.16em]">
                        Editorial rule &mdash; applied to every page
                      </p>
                    </div>
                  </div>
                </Reveal>

                <Reveal delay={220} variant="soft">
                  <p className="mt-5 border-l border-gold/30 pl-4 text-[12px] italic leading-relaxed text-paper/40">
                    Every page names its source, its model, and its doubts.{' '}
                    {providerLine.toLowerCase()}.
                  </p>
                </Reveal>
              </div>
            </div>
          </div>
        </section>

        {/* Ticker */}
        <div className="ticker" aria-hidden="true">
          <div className="ticker__track">
            {[...TICKER, ...TICKER].map((term, index) => (
              <span className="ticker__item" key={`${term}-${index}`}>
                {term}
              </span>
            ))}
          </div>
        </div>

        {generalError && (
          <div className="shell pt-8">
            <div className="animate-rise flex items-start gap-3 rounded-xl border border-warn/25 bg-warn/[0.06] px-4 py-3 backdrop-blur-xl">
              <span className="meta mt-0.5 text-[10px] uppercase tracking-[0.16em] text-warn">
                Error
              </span>
              <p className="font-mono text-[11.5px] leading-relaxed text-warn/90">{generalError}</p>
            </div>
          </div>
        )}

        {/* Intake */}
        <section id="intake" className="section">
          <div className="shell">
            <SectionHead
              number="01"
              title="Commission a page"
              note="One primary source, one page"
            />

            <div className="mt-10 grid gap-8 lg:grid-cols-12 lg:gap-10">
              <Reveal className="lg:col-span-8" delay={60}>
                <ArticleInputForm onGenerate={handleGenerate} isLoading={isSubmitting} />
              </Reveal>

              <Reveal className="lg:col-span-4" delay={140}>
                <aside className="glass-quiet h-full p-6 sm:p-7">
                  <div className="flex items-center justify-between">
                    <span className="eyebrow">What survives</span>
                    <span className="meta text-[9px] uppercase tracking-[0.16em] text-paper/28">
                      Rule set
                    </span>
                  </div>
                  <p className="display mt-4 text-[1.35rem] leading-[1.15] text-paper/85">
                    A page earns its space.
                  </p>

                  <ul className="mt-5">
                    {SURVIVES.map((item) => (
                      <li
                        key={item.n}
                        className="group flex gap-4 border-t border-line py-4 transition-colors duration-300 hover:border-gold/25"
                      >
                        <span className="mt-0.5 font-mono text-[9px] text-gold/60">{item.n}</span>
                        <div>
                          <div className="text-[12px] font-medium text-paper/85 transition-colors group-hover:text-paper">
                            {item.title}
                          </div>
                          <p className="mt-1 text-[11.5px] leading-relaxed text-paper/42">
                            {item.body}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>

                  <div className="mt-6 flex items-start gap-3 border-t border-line pt-4">
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ok" strokeWidth={2.5} />
                    <p className="meta text-[10px] leading-relaxed">
                      Output is informational and educational. It is not legal advice.
                    </p>
                  </div>
                </aside>
              </Reveal>
            </div>
          </div>
        </section>

        {/* Method */}
        <section id="method" className="section">
          <div className="shell">
            <SectionHead number="02" title="The method" note="Enforced in code, not in a prompt" />

            <div className="mt-10 grid gap-10 lg:grid-cols-12 lg:gap-12">
              <div className="lg:col-span-4">
                <Reveal>
                  <p className="display text-[clamp(1.7rem,3.4vw,2.5rem)] leading-[1.12] text-paper/85">
                    A page is only as good as the record beneath it.
                  </p>
                </Reveal>
                <Reveal delay={100} variant="soft">
                  <p className="mt-5 max-w-sm text-[13px] leading-[1.85] text-paper/42">
                    Retrieval happens first. Analysis is measured against the retrieved text.
                    Typesetting is deterministic, so the same verified record always sets the
                    same page.
                  </p>
                </Reveal>
                <Reveal delay={180} variant="soft">
                  <div className="mt-7 flex items-center gap-3">
                    <span className="pulse-dot" aria-hidden="true" />
                    <span className="meta text-[9px] uppercase tracking-[0.18em] text-paper/40">
                      Three rules &middot; no exceptions
                    </span>
                  </div>
                </Reveal>
              </div>

              <div className="lg:col-span-8">
                <div className="space-y-3">
                  {PRINCIPLES.map((principle, index) => (
                    <Reveal key={principle.n} delay={index * 90}>
                      <article className="group glass-quiet relative overflow-hidden p-5 transition-[transform,border-color,box-shadow] duration-500 hover:-translate-y-0.5 hover:border-gold/30 hover:shadow-[0_30px_60px_-46px_rgba(0,0,0,0.9)] sm:p-6">
                        <div className="flex gap-5">
                          <span className="pt-1 font-mono text-[10px] tracking-[0.15em] text-gold/65">
                            {principle.n}
                          </span>
                          <div className="flex-1">
                            <h3 className="display text-[1.4rem] leading-none text-paper">
                              {principle.title}
                            </h3>
                            <p className="mt-2.5 max-w-xl text-[12.5px] leading-relaxed text-paper/45">
                              {principle.body}
                            </p>
                          </div>
                          <Check
                            aria-hidden="true"
                            className="mt-1 hidden h-3.5 w-3.5 shrink-0 text-paper/15 transition-colors duration-500 group-hover:text-gold/70 sm:block"
                            strokeWidth={2.5}
                          />
                        </div>
                        <span
                          aria-hidden="true"
                          className="absolute inset-y-0 left-0 w-px bg-gold/0 transition-colors duration-500 group-hover:bg-gold/60"
                        />
                      </article>
                    </Reveal>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Execution record */}
        {activeJob && (
          <section id="execution" className="section">
            <div className="shell">
              <SectionHead
                number="03"
                title="Execution record"
                note={`Job ${activeJob.job_id.slice(0, 8)}`}
              />
              <div className="mt-10 space-y-8">
                <Reveal>
                  <ProcessingTimeline job={activeJob} />
                </Reveal>

                {(activeJob.has_svg || activeJob.has_png) && (
                  <div className="grid items-start gap-8 lg:grid-cols-12">
                    <Reveal className="lg:col-span-8" delay={80}>
                      <InfographicViewer job={activeJob} />
                    </Reveal>
                    <Reveal className="lg:col-span-4" delay={160}>
                      <LegalValidationCard
                        validation={activeJob.validation_summary}
                        sourceMetadata={activeJob.source_metadata}
                        legalRecord={activeJob.legal_record}
                      />
                    </Reveal>
                  </div>
                )}
              </div>
            </div>
          </section>
        )}
      </main>

      <HistoryDrawer
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        history={history}
        onSelectJob={handleSelectJobFromHistory}
        onDeleteJob={handleDeleteJob}
        activeJobId={activeJob?.job_id}
      />

      <footer className="relative mt-6 overflow-hidden border-t border-line">
        <div className="shell pt-12">
          <div className="grid gap-10 md:grid-cols-12 md:gap-8">
            <div className="md:col-span-5">
              <a href="#top" className="group inline-flex items-center gap-3">
                <span className="brand-mark">L</span>
                <span className="display text-[1.5rem] leading-none text-paper transition-colors group-hover:text-gold-bright">
                  Legal Snaps
                </span>
              </a>
              <p className="mt-4 max-w-xs text-[12px] leading-[1.8] text-paper/40">
                An editorial infographic engine for primary legal sources. Retrieved, audited,
                and set in type.
              </p>
              <div className="mt-5 flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={`h-1.5 w-1.5 rounded-full ${
                    health?.provider_configured ? 'pulse-dot bg-ok' : 'bg-warn'
                  }`}
                />
                <span className="meta text-[9px] uppercase tracking-[0.16em]">
                  {providerLine}
                </span>
              </div>
            </div>

            <div className="md:col-span-3 md:col-start-7">
              <span className="eyebrow">Instruments</span>
              <ul className="mt-4 space-y-2 font-mono text-[10.5px] text-paper/45">
                <li>Qwen 2.5 &middot; 72B</li>
                <li>FLUX.1 &middot; dev</li>
                <li>Deterministic SVG</li>
                <li>Instrument Serif &middot; Plex Mono</li>
              </ul>
            </div>

            <div className="md:col-span-3">
              <span className="eyebrow">Notice</span>
              <p className="mt-4 text-[11.5px] leading-[1.8] text-paper/40">
                Informational and educational use only. Nothing here constitutes legal counsel.
                Source text remains the authority.
              </p>
            </div>
          </div>

          <div className="mt-10 flex flex-col gap-2 border-t border-line py-5 sm:flex-row sm:items-center sm:justify-between">
            <span className="meta text-[9px] uppercase tracking-[0.16em] text-paper/30">
              Established for the record
            </span>
            <span className="meta text-[9px] uppercase tracking-[0.16em] text-paper/30">
              Legal Snaps{year ? ` \u00b7 ${year}` : ''}
            </span>
          </div>
        </div>

        <div className="shell">
          <div className="footer-ghost -mb-[0.16em] mt-2" aria-hidden="true">
            Legal Snaps
          </div>
        </div>
      </footer>
    </div>
  );
}
