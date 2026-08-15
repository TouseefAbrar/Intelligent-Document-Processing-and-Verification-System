import { useState } from 'react';
import { ChevronDown, ChevronUp, Copy, ScanEye, ShieldAlert, Trash2 } from 'lucide-react';
import type { DocumentDetail } from '../api/client';
import { docColor, docLabel, formatBytes, isRejected } from '../api/analytics';
import { StatusBadge, SeverityBadge } from './StatusBadge';

function barClass(v: number) {
  if (v >= 0.75) return 'good';
  if (v >= 0.5) return 'mid';
  return 'bad';
}

export function DocumentCard({
  doc,
  onDelete,
  onInspect,
}: {
  doc: DocumentDetail;
  onDelete?: (d: DocumentDetail) => void;
  onInspect?: (d: DocumentDetail) => void;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const extracted = Object.entries(doc.extracted ?? {});
  const issues = doc.verification?.issues ?? [];
  const q = doc.quality ?? {};
  const dup = doc.duplicate ?? {};
  const forg = doc.forgery ?? {};
  const forgeryLevel: 'RED' | 'YELLOW' | 'GREEN' = forg.level ?? 'GREEN';
  const rejected = isRejected(doc.verification_status);
  const rejection = rejected ? (issues[0]?.message ?? doc.verification_status) : '';

  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(doc.raw_text_preview || '');
    } catch { /* ignore */ }
  };

  return (
    <div className="doc-card">
      <div className="doc-head">
        <div style={{ minWidth: 0 }}>
          <div className="doc-name">{doc.file_name}</div>
          <div className="doc-meta">
            <span className="doc-type-chip" style={{ ['--chip' as string]: `${docColor(doc.doc_type)}2e`, ['--chip-b' as string]: `${docColor(doc.doc_type)}55`, color: docColor(doc.doc_type) }}>
              {docLabel(doc.doc_type)}
            </span>{' '}
            {doc.expected_doc_type && (
              <span className="doc-type-chip" style={{ ['--chip' as string]: 'rgba(148,163,184,0.12)', ['--chip-b' as string]: 'rgba(148,163,184,0.3)', color: 'var(--muted)' }}>
                expected: {docLabel(doc.expected_doc_type)}
              </span>
            )}{' '}
            #{doc.id} · {doc.language ?? '—'} · {formatBytes(doc.file_size)}
          </div>
        </div>
        <StatusBadge status={doc.verification_status} />
      </div>

      {rejection && (
        <div className="badge critical" style={{ marginTop: 10, textTransform: 'none' }}>
          <ShieldAlert size={12} /> {rejection}
        </div>
      )}

      <div className="metric-row">
        <div className="metric">
          <div className="m-label"><span>OCR confidence</span><b>{Math.round(doc.ocr_confidence * 100)}%</b></div>
          <div className={`bar ${barClass(doc.ocr_confidence)}`}><div style={{ width: `${doc.ocr_confidence * 100}%` }} /></div>
        </div>
        <div className="metric">
          <div className="m-label"><span>Classification</span><b>{Math.round(doc.classification_confidence * 100)}%</b></div>
          <div className={`bar ${barClass(doc.classification_confidence)}`}><div style={{ width: `${doc.classification_confidence * 100}%` }} /></div>
        </div>
      </div>

      {q.quality_score != null && (
        <div className="metric" style={{ marginTop: 12 }}>
          <div className="m-label">
            <span><ScanEye size={12} style={{ verticalAlign: '-1px' }} /> Scan quality</span>
            <b>{Math.round(q.quality_score * 100)}%</b>
          </div>
          <div className={`bar ${barClass(q.quality_score)}`}><div style={{ width: `${q.quality_score * 100}%` }} /></div>
          <div className="muted" style={{ fontSize: 11, marginTop: 4, fontFamily: 'var(--mono)' }}>
            blur {q.blur?.toFixed(2)} · brightness {q.brightness} · contrast {q.contrast?.toFixed(2)}
          </div>
        </div>
      )}

      {dup.is_duplicate && (
        <div className="badge critical" style={{ marginTop: 12 }}>
          <ShieldAlert size={12} /> DUPLICATE · {Math.round(dup.similarity * 100)}% match {dup.method ? `(${dup.method})` : ''}
        </div>
      )}

      {forgeryLevel !== 'GREEN' && (
        <div className={`badge ${forgeryLevel === 'RED' ? 'critical' : 'warning'}`} style={{ marginTop: 12, textTransform: 'none' }}>
          <ShieldAlert size={12} />{' '}
          {forgeryLevel === 'RED' ? 'FORGERY DETECTED' : 'POSSIBLE FORGERY'} · score{' '}
          {Math.round((forg.score ?? 0) * 100)}% · {forg.note ?? ''}
        </div>
      )}

      {extracted.length > 0 ? (
        <table className="fields">
          <thead><tr><th>Extracted field</th><th>Value</th></tr></thead>
          <tbody>
            {extracted.map(([k, v]) => (
              <tr key={k}>
                <td className="muted">{k.replace(/_/g, ' ')}</td>
                <td>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="muted" style={{ fontSize: 13, marginTop: 12 }}>No structured fields extracted.</div>
      )}

      {issues.length > 0 && (
        <ul className="issues">
          {issues.map((iss, i) => (
            <li key={i}>
              <SeverityBadge severity={iss.severity} /> {iss.message}
            </li>
          ))}
        </ul>
      )}

      {doc.raw_text_preview && (
        <div style={{ marginTop: 12 }}>
          <button className="btn ghost sm" onClick={() => setShowRaw((s) => !s)}>
            {showRaw ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {showRaw ? 'Hide raw text' : 'Show raw OCR text'}
          </button>
          {showRaw && (
            <pre className="mono" style={{ fontSize: 11.5, color: 'var(--muted)', whiteSpace: 'pre-wrap', background: 'rgba(255,255,255,0.03)', padding: 12, borderRadius: 10, marginTop: 8 }}>
              {doc.raw_text_preview}
            </pre>
          )}
        </div>
      )}

      <div className="doc-actions">
        <div className="row" style={{ gap: 8 }}>
          <button className="btn ghost sm" onClick={copyText} disabled={!doc.raw_text_preview}>
            <Copy size={13} /> Copy text
          </button>
          {onInspect && (
            <button className="btn ghost sm" onClick={() => onInspect(doc)}>
              <ScanEye size={13} /> Inspect
            </button>
          )}
        </div>
        {onDelete && (
          <button className="icon-btn" title="Delete document" onClick={() => onDelete(doc)}>
            <Trash2 size={15} />
          </button>
        )}
      </div>
    </div>
  );
}
