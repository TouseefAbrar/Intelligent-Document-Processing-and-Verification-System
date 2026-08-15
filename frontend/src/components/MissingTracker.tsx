import { CheckCircle2, XCircle } from 'lucide-react';
import type { SubmissionListRow } from '../api/client';
import { REQUIRED_DOCS, requiredDocsTracker } from '../api/analytics';

export function MissingTracker({ rows }: { rows: SubmissionListRow[] }) {
  const tracker = requiredDocsTracker(rows);
  const total = rows.length;
  const overall = REQUIRED_DOCS.length
    ? tracker.reduce((a, b) => a + b.presentCount, 0) / (REQUIRED_DOCS.length * (total || 1))
    : 0;

  if (total === 0) {
    return <div className="empty">Upload a batch — the required-document tracker will appear here.</div>;
  }

  return (
    <div>
      <div className="tracker-head">
        <div>
          <div className="tracker-title">Required-document coverage</div>
          <div className="muted" style={{ fontSize: 12.5 }}>
            Across {total} submission{total > 1 ? 's' : ''} — required set: {REQUIRED_DOCS.map((d) => docLabelShort(d)).join(', ')}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="tracker-score">{Math.round(overall * 100)}<span className="unit">%</span></div>
          <div className="muted" style={{ fontSize: 11 }}>coverage</div>
        </div>
      </div>

      {tracker.map((t) => {
        const pct = Math.round(t.rate * 100);
        const missing = t.missingCount;
        return (
          <div className="tracker-row" key={t.type}>
            <div className="tracker-row-top">
              <span className="tracker-doc" style={{ ['--chip' as string]: `${t.color}2e`, ['--chip-b' as string]: `${t.color}55` }}>
                <i style={{ background: t.color }} /> {t.label}
              </span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 12.5, color: missing > 0 ? 'var(--rose)' : 'var(--emerald)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                {missing > 0 ? <XCircle size={13} /> : <CheckCircle2 size={13} />}
                {missing > 0 ? `${missing} missing` : 'always present'}
              </span>
            </div>
            <div className="bar" style={{ height: 8 }}>
              <div
                style={{
                  width: `${pct}%`,
                  background: missing > 0 ? 'linear-gradient(90deg, var(--rose), var(--amber))' : `linear-gradient(90deg, ${t.color}, var(--emerald))`,
                }}
              />
            </div>
            <div className="tracker-row-foot">
              <span className="muted mono">present in {t.presentCount}/{total}</span>
              <span className="muted mono">{pct}% of batches</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function docLabelShort(t: string) {
  return { resume: 'Resume', cnic: 'CNIC', offer_letter: 'Offer Letter', degree: 'Degree', transcript: 'Transcript' }[t] ?? t;
}
