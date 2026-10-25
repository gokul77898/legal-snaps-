'use client';

import React, { useState } from 'react';
import { Check, ChevronDown, Loader2 } from 'lucide-react';
import { JobResponse } from '@/types';

interface ProcessingTimelineProps {
  job: JobResponse;
}

const STAGES = [
  'Searching for the article',
  'Retrieving the source',
  'Extracting text',
  'Analysing legal information',
  'Validating legal claims',
  'Designing the infographic',
  'Generating illustrations',
  'Rendering final image',
  'Running quality checks',
  'Saving the output',
];

type StageState = 'done' | 'live' | 'halted' | 'waiting';

export const ProcessingTimeline: React.FC<ProcessingTimelineProps> = ({ job }) => {
  const [showLogs, setShowLogs] = useState(false);
  const currentStage = job.current_stage || 0;
  const isFailed = job.status === 'failed';
  const isCompleted = job.status === 'completed';
  const progress = Math.min(100, Math.max(0, job.progress_percent));

  const stageState = (id: number): StageState => {
    if (isCompleted || currentStage > id) return 'done';
    if (isFailed && currentStage === id) return 'halted';
    if (currentStage === id) return 'live';
    return 'waiting';
  };

  const nameTone: Record<StageState, string> = {
    done: 'text-paper/55',
    live: 'text-gold-bright',
    halted: 'text-warn',
    waiting: 'text-paper/35',
  };

  const numberTone: Record<StageState, string> = {
    done: 'text-gold/50',
    live: 'text-gold',
    halted: 'text-warn/80',
    waiting: 'text-paper/20',
  };

  return (
    <div className="glass overflow-hidden">
      <div className="flex flex-wrap items-end justify-between gap-6 px-6 py-5 sm:px-7">
        <div>
          <span className="eyebrow">Execution</span>
          <h3 className="display mt-2 text-[1.6rem] leading-none text-paper">
            Ten stages, in the open.
          </h3>
        </div>
        <div className="text-right">
          <div
            className={`display text-[2.6rem] leading-none tabular-nums ${
              isFailed ? 'text-warn' : isCompleted ? 'text-ok' : 'text-gold-bright'
            }`}
          >
            {progress}%
          </div>
          <div className="meta mt-1.5 text-[9px] uppercase tracking-[0.18em]">{job.status}</div>
        </div>
      </div>

      <div className="px-6 sm:px-7">
        <div className="progress-track mb-1">
          <div
            className="progress-fill"
            data-failed={isFailed}
            data-done={isCompleted && !isFailed}
            style={{ width: `${progress}%` }}
            aria-hidden="true"
          />
        </div>
      </div>

      <div className="px-6 py-5 sm:px-7">
        <div className="mb-3 flex items-baseline justify-between gap-4">
          <span className="meta text-[9px] uppercase tracking-[0.16em] text-paper/35">
            Stage {String(Math.min(10, Math.max(1, currentStage))).padStart(2, '0')} / 10
          </span>
          <span className="meta text-[9px] uppercase tracking-[0.16em] text-paper/25">
            {job.current_stage_name || 'Awaiting dispatch'}
          </span>
        </div>

        <ol className="grid grid-cols-1 gap-x-10 sm:grid-cols-2">
          {STAGES.map((name, index) => {
            const id = index + 1;
            const state = stageState(id);

            return (
              <li
                key={name}
                data-state={state}
                aria-current={state === 'live' ? 'step' : undefined}
                className="stage-row flex items-baseline gap-3 border-t border-line py-2.5"
              >
                <span
                  className={`w-5 shrink-0 font-mono text-[9px] tabular-nums ${numberTone[state]}`}
                >
                  {id.toString().padStart(2, '0')}
                </span>
                <span className={`flex-1 text-[12.5px] leading-snug ${nameTone[state]}`}>
                  {name}
                </span>
                <span className="flex w-10 shrink-0 justify-end">
                  {state === 'done' ? (
                    <Check className="h-3 w-3 text-ok" strokeWidth={2.5} />
                  ) : state === 'live' ? (
                    <Loader2 className="h-3 w-3 animate-spin text-gold" />
                  ) : state === 'halted' ? (
                    <span className="font-mono text-[8px] uppercase tracking-[0.14em] text-warn">
                      halt
                    </span>
                  ) : (
                    <span className="font-mono text-[10px] text-paper/20">&mdash;</span>
                  )}
                </span>
              </li>
            );
          })}
        </ol>

        {isFailed && job.error_message && (
          <div className="mt-5 rounded-lg border border-warn/25 bg-warn/[0.06] px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-warn">
              Pipeline halted
            </div>
            <p className="mt-1.5 break-words font-mono text-[11px] leading-relaxed text-warn/90">
              {job.error_message}
            </p>
          </div>
        )}
      </div>

      {job.logs && job.logs.length > 0 && (
        <div className="border-t border-line px-6 py-3.5 sm:px-7">
          <button
            onClick={() => setShowLogs(!showLogs)}
            aria-expanded={showLogs}
            className="flex w-full cursor-pointer items-center justify-between text-paper/40 transition-colors duration-300 hover:text-paper/70"
          >
            <span className="btn-quiet">
              Execution log <span className="text-paper/30">({job.logs.length})</span>
            </span>
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform duration-300 ${
                showLogs ? 'rotate-180' : ''
              }`}
            />
          </button>

          {showLogs && (
            <div className="glass-sunken animate-fade mt-3 max-h-56 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed">
              {job.logs.map((log, index) => (
                <div
                  key={index}
                  className={`flex gap-2.5 border-t border-line/60 py-1 first:border-t-0 first:pt-0 ${
                    log.includes('FAILURE') ? 'text-warn' : 'text-paper/55'
                  }`}
                >
                  <span className="shrink-0 select-none text-paper/20">
                    {(index + 1).toString().padStart(2, '0')}
                  </span>
                  <span className="break-words">{log}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
