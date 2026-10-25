'use client';

import React, { useState } from 'react';
import { ValidationSummary, SourceMetadata, LegalRecord } from '@/types';

interface LegalValidationCardProps {
  validation?: ValidationSummary;
  sourceMetadata?: SourceMetadata;
  legalRecord?: LegalRecord;
}

export const LegalValidationCard: React.FC<LegalValidationCardProps> = ({
  validation,
  sourceMetadata,
  legalRecord,
}) => {
  const [showAllClaims, setShowAllClaims] = useState(false);

  if (!validation && !sourceMetadata) return null;

  const verifiedPercent = validation?.total_claims
    ? Math.round((validation.verified_claims / validation.total_claims) * 100)
    : 100;
  const isCritical = Boolean(validation?.has_critical_unverified);
  const visibleClaims = validation?.claims
    ? showAllClaims
      ? validation.claims
      : validation.claims.slice(0, 4)
    : [];

  return (
    <div className="glass overflow-hidden">
      <div className="flex flex-wrap items-end justify-between gap-4 px-6 py-5 sm:px-7">
        <div>
          <span className="eyebrow">Audit</span>
          <h3 className="display mt-2 text-[1.5rem] leading-none text-paper">
            Every claim, sourced.
          </h3>
        </div>
        {validation && (
          <div className="text-right">
            <div
              className={`display text-[2.1rem] leading-none tabular-nums ${
                isCritical ? 'text-warn' : 'text-ok'
              }`}
            >
              {verifiedPercent}%
            </div>
            <div className="meta mt-1.5 text-[9px] uppercase tracking-[0.16em]">
              {isCritical ? 'Critical flag' : 'Claims verified'}
            </div>
          </div>
        )}
      </div>

      {validation && (
        <div className="px-6 sm:px-7">
          <div className="progress-track">
            <div
              className="progress-fill"
              data-failed={isCritical}
              data-done={!isCritical}
              style={{ width: `${verifiedPercent}%` }}
              aria-hidden="true"
            />
          </div>
        </div>
      )}

      <div className="space-y-7 px-6 py-6 sm:px-7">
        {sourceMetadata && (
          <section>
            <div className="flex items-baseline justify-between gap-3">
              <span className="eyebrow">Primary source</span>
              <span className="meta text-[9px] uppercase tracking-[0.14em]">
                {sourceMetadata.extraction_method.toUpperCase()}
              </span>
            </div>
            <h4 className="display mt-2 text-[1.15rem] leading-snug text-paper">
              {sourceMetadata.title}
            </h4>
            {sourceMetadata.url && (
              <a
                href={sourceMetadata.url}
                target="_blank"
                rel="noopener noreferrer"
                className="link-gold mt-1 block break-all font-mono text-[10.5px] leading-relaxed"
              >
                {sourceMetadata.url}
              </a>
            )}
            <dl className="mt-4">
              <div className="flex items-baseline justify-between gap-4 border-t border-line py-1.5">
                <dt className="meta text-[9px] uppercase tracking-[0.14em]">Length</dt>
                <dd className="font-mono text-[10px] text-paper/65">
                  {sourceMetadata.text_length.toLocaleString()} chars
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-4 border-t border-line py-1.5">
                <dt className="meta text-[9px] uppercase tracking-[0.14em]">Retrieved</dt>
                <dd className="font-mono text-[10px] text-paper/65">
                  {new Date(sourceMetadata.retrieval_time).toLocaleTimeString()}
                </dd>
              </div>
              {sourceMetadata.publisher && (
                <div className="flex items-baseline justify-between gap-4 border-t border-line py-1.5">
                  <dt className="meta text-[9px] uppercase tracking-[0.14em]">Publisher</dt>
                  <dd className="max-w-[65%] truncate text-right font-mono text-[10px] text-paper/65">
                    {sourceMetadata.publisher}
                  </dd>
                </div>
              )}
            </dl>
          </section>
        )}

        {validation && (
          <dl className="glass-sunken grid grid-cols-3">
            <div className="py-4 pl-4 pr-3">
              <dd className="display text-[1.9rem] leading-none tabular-nums text-paper">
                {validation.total_claims}
              </dd>
              <dt className="meta mt-1.5 text-[9px] uppercase tracking-[0.14em]">Audited</dt>
            </div>
            <div className="border-l border-line px-3 py-4">
              <dd className="display text-[1.9rem] leading-none tabular-nums text-ok">
                {validation.verified_claims}
              </dd>
              <dt className="meta mt-1.5 text-[9px] uppercase tracking-[0.14em]">Verified</dt>
            </div>
            <div className="border-l border-line py-4 pl-3 pr-4">
              <dd className="display text-[1.9rem] leading-none tabular-nums text-warn">
                {validation.unverified_claims}
              </dd>
              <dt className="meta mt-1.5 text-[9px] uppercase tracking-[0.14em]">Flagged</dt>
            </div>
          </dl>
        )}

        {(legalRecord?.analysis_source || (legalRecord?.uncertainties?.length ?? 0) > 0) && (
          <section className="space-y-2">
            <span className="eyebrow">Provenance</span>
            {legalRecord?.analysis_source && (
              <p className="text-[11.5px] leading-relaxed text-paper/50">
                Structured extraction produced by{' '}
                <span className="font-mono text-paper/75">{legalRecord.analysis_source}</span>.
              </p>
            )}
            {legalRecord?.uncertainties && legalRecord.uncertainties.length > 0 && (
              <div className="mt-3 border-l border-line-strong pl-4">
                <div className="meta text-[9px] uppercase tracking-[0.14em]">
                  Not established by the source
                </div>
                <ul className="mt-2 space-y-1.5">
                  {legalRecord.uncertainties.map((uncertainty, index) => (
                    <li
                      key={index}
                      className="text-[11.5px] leading-relaxed text-paper/55"
                    >
                      {uncertainty}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {validation?.warnings && validation.warnings.length > 0 && (
          <div className="rounded-lg border border-warn/25 bg-warn/[0.06] px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-warn">
              Editorial warnings
            </div>
            <ul className="mt-2 space-y-1.5">
              {validation.warnings.map((warning, index) => (
                <li key={index} className="text-[11.5px] leading-relaxed text-warn/80">
                  {warning}
                </li>
              ))}
            </ul>
          </div>
        )}

        {validation?.claims && validation.claims.length > 0 && (
          <section className="border-t border-line pt-4">
            <div className="flex items-baseline justify-between gap-3">
              <span className="eyebrow">Claim ledger</span>
              <button
                onClick={() => setShowAllClaims(!showAllClaims)}
                aria-expanded={showAllClaims}
                className="btn-quiet cursor-pointer"
              >
                {showAllClaims ? 'Fewer' : `All ${validation.claims.length}`}
              </button>
            </div>

            <ul className="mt-2 max-h-80 overflow-y-auto">
              {visibleClaims.map((claim) => (
                <li key={claim.claim_id} className="border-t border-line py-3 first:border-t-0">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-mono text-[8.5px] uppercase tracking-[0.16em] text-paper/35">
                      {claim.claim_type}
                    </span>
                    <span
                      className={`font-mono text-[8.5px] uppercase tracking-[0.14em] ${
                        claim.verified ? 'text-ok' : 'text-warn'
                      }`}
                    >
                      {claim.verified ? 'verified' : 'flagged'}
                    </span>
                  </div>
                  <p className="mt-1 text-[12px] leading-snug text-paper/85">{claim.claim_text}</p>
                  {claim.source_reference && (
                    <p className="display mt-1.5 text-[11.5px] italic leading-snug text-paper/45">
                      &ldquo;{claim.source_reference}&rdquo;
                    </p>
                  )}
                  {claim.warning_notes && (
                    <p className="mt-1.5 text-[10.5px] leading-relaxed text-warn/80">
                      {claim.warning_notes}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
};
