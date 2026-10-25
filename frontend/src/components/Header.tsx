'use client';

import React, { useEffect, useRef, useState } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { HealthStatus } from '@/types';

interface HeaderProps {
  health: HealthStatus | null;
  onOpenHistory: () => void;
  historyCount: number;
  hasActiveJob?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  onOpenHistory,
  historyCount,
  hasActiveJob = false,
}) => {
  const isHealthy = health?.status === 'healthy';
  const isReady = isHealthy && Boolean(health?.provider_configured);
  const [scrolled, setScrolled] = useState(false);
  const progressRef = useRef<HTMLDivElement | null>(null);
  const frameRef = useRef<number>(0);

  const statusLabel = !health
    ? 'Connecting'
    : !isHealthy
      ? 'Degraded'
      : isReady
        ? 'Systems nominal'
        : 'Token required';

  useEffect(() => {
    const update = () => {
      frameRef.current = 0;
      const y = window.scrollY;
      setScrolled(y > 10);

      const max = document.documentElement.scrollHeight - window.innerHeight;
      if (progressRef.current) {
        const ratio = max > 0 ? Math.min(1, Math.max(0, y / max)) : 0;
        progressRef.current.style.transform = `scaleX(${ratio})`;
      }
    };

    const onScroll = () => {
      if (!frameRef.current) {
        frameRef.current = window.requestAnimationFrame(update);
      }
    };

    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (frameRef.current) window.cancelAnimationFrame(frameRef.current);
    };
  }, []);

  return (
    <>
      <div ref={progressRef} className="scroll-progress" aria-hidden="true" />

      <header className="site-header" data-scrolled={scrolled}>
        <div className="shell flex h-[4.4rem] items-center justify-between gap-4">
          <a href="#top" className="group flex shrink-0 items-center gap-3">
            <span className="brand-mark transition-transform duration-500 group-hover:-rotate-6">
              L
            </span>
            <span className="flex flex-col leading-none">
              <span className="display text-[1.35rem] leading-none text-paper transition-colors group-hover:text-gold-bright">
                Legal Snaps
              </span>
              <span className="mt-[5px] hidden font-mono text-[8px] uppercase tracking-[0.3em] text-paper/35 sm:block">
                Editorial infographic engine
              </span>
            </span>
          </a>

          <nav aria-label="Sections" className="hidden items-center gap-8 md:flex">
            <a href="#intake" className="nav-link">
              Commission
            </a>
            <a href="#method" className="nav-link">
              Method
            </a>
            {hasActiveJob && (
              <a href="#execution" className="nav-link">
                Record
              </a>
            )}
          </nav>

          <div className="flex items-center gap-2.5 sm:gap-3.5">
            <div className="glass-quiet hidden items-center gap-2 rounded-full px-3 py-1.5 lg:flex">
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 rounded-full ${
                  isReady ? 'pulse-dot bg-ok' : isHealthy ? 'bg-warn' : 'bg-paper/30'
                }`}
              />
              <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-paper/55">
                {statusLabel}
              </span>
              <span aria-hidden="true" className="h-3 w-px bg-line" />
              <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-paper/30">
                HF
              </span>
            </div>

            <button
              onClick={onOpenHistory}
              className="btn-ghost group"
              aria-label={`Open archive, ${historyCount} records`}
            >
              <span className="font-mono text-[9px] uppercase tracking-[0.18em] sm:text-[10px]">
                Archive
              </span>
              <span className="font-mono text-[9px] tabular-nums text-gold/80">
                {String(historyCount).padStart(2, '0')}
              </span>
              <ArrowUpRight className="h-3 w-3 text-gold/70 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
            </button>
          </div>
        </div>
      </header>
    </>
  );
};
