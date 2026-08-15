import { Download, FileQuestion, FileText, FolderOpen, Trash2, X } from 'lucide-react';
import type { DocumentDetail, SubmissionDetail } from '../api/client';
import { api } from '../api/client';
import { formatPct } from '../api/analytics';
import { CompletenessChecklist } from './CompletenessChecklist';
import { DocumentCard } from './DocumentCard';
import { StatusBadge } from './StatusBadge';

export function SubmissionDrawer({
  submission,
  onClose,
  onDeleteDocument,
  onDeleteSubmission,
  onInspect,
}: {
  submission: SubmissionDetail;
  onClose: () => void;
  onDeleteDocument: (d: DocumentDetail) => void;
  onDeleteSubmission: () => void;
  onInspect: (d: DocumentDetail) => void;
}) {
  const summary = (submission.summary ?? {}) as Record<string, unknown>;
  const issues = submission.documents.flatMap((d) =>
    (d.verification?.issues ?? []).map((i) => ({ ...i, file: d.file_name }))
  );
  const critical = issues.filter((i) => i.severity === 'critical');

  return (
    <div className="overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 44, height: 44, borderRadius: 12, display: 'grid', placeItems: 'center', background: 'linear-gradient(135deg,rgba(34,211,238,.18),rgba(167,139,250,.18))', border: '1px solid var(--border)' }}>
              <FolderOpen size={20} style={{ color: 'var(--cyan)' }} />
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 800 }}>Submission #{submission.id}</div>
              <div className="muted mono" style={{ fontSize: 12 }}>
                {submission.applicant_ref || 'No applicant ref'} · {new Date(submission.created_at).toLocaleString()}
              </div>
            </div>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <StatusBadge status={submission.status} />
            <button className="icon-btn" onClick={onClose}><X size={16} /></button>
          </div>
        </div>

        <div className="row" style={{ marginTop: 18, gap: 10 }}>
          <a className="btn sm" href={api.reportUrl(submission.id, 'html')} target="_blank" rel="noreferrer">
            <FileText size={14} /> HTML Report
          </a>
          <a className="btn ghost sm" href={api.reportUrl(submission.id, 'pdf')} target="_blank" rel="noreferrer">
            <Download size={14} /> PDF
          </a>
          <button className="btn danger sm" onClick={onDeleteSubmission}>
            <Trash2 size={14} /> Delete submission
          </button>
        </div>

        <div className="drawer-grid">
          <div className="panel" style={{ marginTop: 18, padding: 16 }}>
            <div className="muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Document checklist</div>
            <CompletenessChecklist submission={submission} />
          </div>

          <div>
            <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}>
              <div className="kpi">
                <div className="kpi-label">Completeness</div>
                <div className="kpi-value">{Math.round(submission.completeness_score * 100)}<span className="unit">%</span></div>
              </div>
              <div className="kpi">
                <div className="kpi-label">Confidence</div>
                <div className="kpi-value">{formatPct(submission.overall_confidence)}</div>
              </div>
              <div className="kpi">
                <div className="kpi-label">Documents</div>
                <div className="kpi-value">{submission.documents.length}</div>
              </div>
              <div className="kpi">
                <div className="kpi-label">Missing</div>
                <div className="kpi-value">{submission.missing_documents.length}</div>
              </div>
            </div>

            {submission.missing_documents.length > 0 && (
              <div className="panel" style={{ marginTop: 12, padding: 14, borderColor: 'rgba(251,113,133,0.35)' }}>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--rose)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <FileQuestion size={15} /> Missing documents
                </div>
                <div className="row" style={{ gap: 8 }}>
                  {submission.missing_documents.map((m) => (
                    <span key={m} className="badge FAILED">{m}</span>
                  ))}
                </div>
              </div>
            )}

            {Boolean(summary.overall_comment) && (
              <div className="panel" style={{ marginTop: 12, padding: 14 }}>
                <div className="muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>Engine comment</div>
                <div style={{ fontSize: 13, lineHeight: 1.6 }}>{String(summary.overall_comment)}</div>
              </div>
            )}
          </div>
        </div>

        {critical.length > 0 && (
          <div className="panel" style={{ marginTop: 16, padding: 16, borderColor: 'rgba(251,113,133,0.35)' }}>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--rose)', marginBottom: 8 }}>Critical issues</div>
            {critical.map((c, i) => (
              <div key={i} className="mono" style={{ fontSize: 12.5, color: 'var(--text)', padding: '4px 0' }}>
                {c.file}: {c.message}
              </div>
            ))}
          </div>
        )}

        <h3 className="panel-title" style={{ margin: '24px 0 12px' }}>Document analysis</h3>
        <div className="doc-grid" style={{ gridTemplateColumns: '1fr' }}>
          {submission.documents.map((d) => (
            <DocumentCard key={d.id} doc={d} onDelete={onDeleteDocument} onInspect={onInspect} />
          ))}
        </div>
      </div>
    </div>
  );
}
