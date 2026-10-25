'use client';

import React from 'react';
import { X, Trash2, ArrowUpRight } from 'lucide-react';
import { JobListItem } from '@/types';
import { getSvgDownloadUrl, getPngDownloadUrl } from '@/lib/api';

interface HistoryDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  history: JobListItem[];
  onSelectJob: (jobId: string) => void;
  onDeleteJob: (jobId: string) => void;
  activeJobId?: string;
}

export const HistoryDrawer: React.FC<HistoryDrawerProps> = ({
  isOpen,
  onClose,
  history,
  onSelectJob,
  onDeleteJob,
  activeJobId,
}) => {
  if (!isOpen) return null;

  return (
    <div className="animate-fade fixed inset-0 z-[75] flex justify-end">
      <button
        type="button"
        aria-label="Close archive"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-ink/70 backdrop-blur-xl"
      />

      <aside
        className="drawer animate-slide-in relative flex h-full w-full max-w-md flex-col"
        aria-label="Archive"
      >
        <div className="flex items-start justify-between border-b border-line px-6 py-6">
          <div>
            <span className="eyebrow">Archive</span>
            <h3 className="display mt-2 text-[1.55rem] leading-none text-paper">
              Previously typeset.
            </h3>
            <p className="meta mt-2 text-[10px]">
              {history.length} {history.length === 1 ? 'record' : 'records'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close archive"
            className="glass-quiet cursor-pointer rounded-full p-2 text-paper/45 transition-colors duration-300 hover:text-gold-bright"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {history.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
            <p className="display text-[1.3rem] italic text-paper/60">No pages yet.</p>
            <p className="meta mt-3 max-w-[16rem] text-[10px] leading-relaxed">
              Commission a case and the finished page will be filed here.
            </p>
          </div>
        ) : (
          <ul className="flex-1 overflow-y-auto px-6">
            {history.map((item, index) => {
              const isActive = item.job_id === activeJobId;
              const dateStr = new Date(item.created_at).toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              });

              return (
                <li
                  key={item.job_id}
                  className="animate-rise archive-row border-t border-line first:border-t-0"
                  style={{ animationDelay: `${Math.min(index, 7) * 45}ms` }}
                >
                  <div className="relative py-4 pl-4">
                    {isActive && (
                      <span
                        aria-hidden="true"
                        className="absolute bottom-4 left-0 top-4 w-px bg-gold shadow-[0_0_10px_rgba(207,164,68,0.7)]"
                      />
                    )}
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-mono text-[9px] tracking-[0.14em] text-paper/30">
                          {(index + 1).toString().padStart(2, '0')}
                        </div>
                        <button
                          type="button"
                          onClick={() => onSelectJob(item.job_id)}
                          className="mt-1 line-clamp-2 block cursor-pointer text-left text-[13px] font-medium leading-snug text-paper/90 transition-colors duration-300 hover:text-gold-bright"
                        >
                          {item.headline || item.article_name || 'Legal brief'}
                        </button>
                        {item.court_case_info && (
                          <div className="mt-1 truncate font-mono text-[9.5px] text-paper/35">
                            {item.court_case_info}
                          </div>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => onDeleteJob(item.job_id)}
                        title="Delete artifact"
                        aria-label="Delete artifact"
                        className="shrink-0 cursor-pointer p-1 text-paper/25 transition-colors duration-300 hover:text-warn"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>

                    <div className="mt-3 flex items-center justify-between gap-3">
                      <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-paper/35">
                        {dateStr}
                      </span>
                      <div className="flex items-center gap-3 font-mono text-[9px] uppercase tracking-[0.12em]">
                        {item.has_svg && (
                          <a
                            href={getSvgDownloadUrl(item.job_id)}
                            download
                            className="text-paper/45 transition-colors duration-300 hover:text-gold"
                          >
                            SVG
                          </a>
                        )}
                        {item.has_png && (
                          <a
                            href={getPngDownloadUrl(item.job_id)}
                            download
                            className="text-paper/45 transition-colors duration-300 hover:text-gold"
                          >
                            PNG
                          </a>
                        )}
                        <button
                          type="button"
                          onClick={() => onSelectJob(item.job_id)}
                          className="flex cursor-pointer items-center gap-1 text-gold/85 transition-colors duration-300 hover:text-gold-bright"
                        >
                          Open
                          <ArrowUpRight className="h-2.5 w-2.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <div className="border-t border-line px-6 py-4">
          <p className="meta text-[9px] uppercase tracking-[0.14em] text-paper/25">
            Artifacts remain on this machine
          </p>
        </div>
      </aside>
    </div>
  );
};
