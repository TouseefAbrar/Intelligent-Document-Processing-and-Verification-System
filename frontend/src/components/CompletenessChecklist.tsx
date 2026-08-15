import { CheckCircle2, FileQuestion, XCircle } from 'lucide-react';
import type { SubmissionDetail } from '../api/client';
import { completenessChecklist, docColor, isRejected } from '../api/analytics';
import { StatusBadge } from './StatusBadge';

export function CompletenessChecklist({ submission }: { submission: SubmissionDetail }) {
  const items = completenessChecklist(submission);
  const present = items.filter((i) => i.present).length;

  return (
    <div className="checklist">
      <div className="checklist-head">
        <div>
          <div className="tracker-title">Applicant document checklist</div>
          <div className="muted" style={{ fontSize: 12.5 }}>Required set for a complete application</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="tracker-score">{present}<span className="unit">/{items.length}</span></div>
          <div className="muted" style={{ fontSize: 11 }}>present</div>
        </div>
      </div>
      {items.map((it) => {
        const doc = it.doc;
        const rejected = Boolean(doc && isRejected(doc.verification_status));
        return (
          <div className="checklist-row" key={it.type}>
            {it.present ? (
              <CheckCircle2 size={17} style={{ color: 'var(--emerald)', flexShrink: 0 }} />
            ) : (
              <XCircle size={17} style={{ color: 'var(--rose)', flexShrink: 0 }} />
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 13.5 }}>{it.label}</div>
              <div className="muted mono" style={{ fontSize: 11 }}>
                {doc
                  ? rejected
                    ? `${doc.verification_status} — upload rejected, does not count as present`
                    : `${doc.verification_status} · ${Math.round(doc.ocr_confidence * 100)}% OCR`
                  : 'Not uploaded'}
              </div>
            </div>
            <StatusBadge status={doc ? doc.verification_status : 'MISSING'} />
          </div>
        );
      })}
    </div>
  );
}
