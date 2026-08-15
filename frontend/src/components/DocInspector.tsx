import { useState } from 'react';
import { CheckCircle2, Copy, FileText, ScanEye, ShieldAlert, X } from 'lucide-react';
import type { DocumentDetail } from '../api/client';
import { docColor, docLabel, formatBytes } from '../api/analytics';
import { StatusBadge, SeverityBadge } from './StatusBadge';

export function DocInspector({ doc, onClose }: { doc: DocumentDetail; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const extracted = Object.entries(doc.extracted ?? {});
  const q = doc.quality ?? {};
  const issues = doc.verification?.issues ?? [];
  const actions = doc.verification?.recommended_actions ?? [];

  const copyRaw = async () => {
    try {
      await navigator.clipboard.writeText(doc.raw_text_preview || '');
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* ignore */ }
  };

  const metrics: { label: string; value: string }[] = [
    { label: 'Document ID', value: `#${doc.id}` },
    { label: 'OCR provider', value: doc.ocr_provider },
    { label: 'Language', value: doc.language || '—' },
    { label: 'Size', value: formatBytes(doc.file_size) },
    { label: 'Created', value: new Date(doc.created_at).toLocaleString() },
    { label: 'Engine', value: doc.verification?.engine ?? 'rules' },
  ];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="inspector"
        onClick={(e) => e.stopPropagation()}
        style={{ ['--chip' as string]: `${docColor(doc.doc_type)}2e`, ['--chip-b' as string]: `${docColor(doc.doc_type)}55` }}
      >
        <div className="inspector-head">
          <div style={{ width: 46, height: 46, borderRadius: 13, display: 'grid', placeItems: 'center', background: 'linear-gradient(135deg,rgba(34,211,238,.18),rgba(167,139,250,.18))', border: '1px solid var(--border)' }}>
            <FileText size={21} style={{ color: 'var(--cyan)' }} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 17, fontWeight: 800, wordBreak: 'break-all' }}>{doc.file_name}</div>
            <div className="muted mono" style={{ fontSize: 12, marginTop: 2 }}>
              <span className="doc-type-chip">{docLabel(doc.doc_type)}</span> · ID #{doc.id}
            </div>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <StatusBadge status={doc.verification_status} />
            <button className="icon-btn" onClick={onClose}><X size={16} /></button>
          </div>
        </div>

        <div className="inspector-section">
          <div className="inspector-title"><ScanEye size={14} /> Confidence signals</div>
          <div className="metric-row" style={{ marginTop: 8 }}>
            <div className="metric">
              <div className="m-label"><span>OCR confidence</span><b>{Math.round(doc.ocr_confidence * 100)}%</b></div>
              <div className="bar good"><div style={{ width: `${doc.ocr_confidence * 100}%` }} /></div>
            </div>
            <div className="metric">
              <div className="m-label"><span>Classification</span><b>{Math.round(doc.classification_confidence * 100)}%</b></div>
              <div className="bar good"><div style={{ width: `${doc.classification_confidence * 100}%` }} /></div>
            </div>
          </div>
          {q.quality_score != null && (
            <div className="metric" style={{ marginTop: 12 }}>
              <div className="m-label"><span>Scan quality</span><b>{Math.round(q.quality_score * 100)}%</b></div>
              <div className="bar mid"><div style={{ width: `${q.quality_score * 100}%` }} /></div>
              <div className="muted mono" style={{ fontSize: 11, marginTop: 4 }}>
                blur {q.blur?.toFixed(2)} · brightness {q.brightness} · contrast {q.contrast?.toFixed(2)}
              </div>
            </div>
          )}
        </div>

        <div className="inspector-section">
          <div className="inspector-title"><FileText size={14} /> Metadata</div>
          <div className="meta-grid">
            {metrics.map((m) => (
              <div key={m.label}>
                <div className="muted" style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.8 }}>{m.label}</div>
                <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{m.value}</div>
              </div>
            ))}
          </div>
        </div>

        {doc.duplicate?.is_duplicate && (
          <div className="inspector-section" style={{ borderColor: 'rgba(251,113,133,0.35)' }}>
            <div className="inspector-title" style={{ color: 'var(--rose)' }}><ShieldAlert size={14} /> Duplicate detection</div>
            <div className="badge critical">
              <ShieldAlert size={12} /> {Math.round(doc.duplicate.similarity * 100)}% match via {doc.duplicate.method ?? 'image hash'}
            </div>
          </div>
        )}

        {(doc.forgery?.level ?? 'GREEN') !== 'GREEN' && (
          <div className="inspector-section" style={{ borderColor: doc.forgery?.level === 'RED' ? 'rgba(251,113,133,0.35)' : 'rgba(251,191,36,0.35)' }}>
            <div className="inspector-title" style={{ color: doc.forgery?.level === 'RED' ? 'var(--rose)' : 'var(--amber)' }}>
              <ShieldAlert size={14} /> Fake-document forensics
            </div>
            <div className={`badge ${doc.forgery?.level === 'RED' ? 'critical' : 'warning'}`} style={{ marginTop: 4 }}>
              <ShieldAlert size={12} /> {doc.forgery?.level === 'RED' ? 'FORGERY DETECTED' : 'POSSIBLE FORGERY'} · score{' '}
              {Math.round((doc.forgery?.score ?? 0) * 100)}% · confidence{' '}
              {Math.round((doc.forgery?.confidence ?? 0) * 100)}% · {doc.forgery?.engine ?? 'heuristics'}
            </div>
            {(doc.forgery?.signals ?? []).filter((s) => s.result !== 'clear').map((s) => (
              <div key={s.name} style={{ marginTop: 8, fontSize: 12.5 }}>
                <div className="row" style={{ gap: 6 }}>
                  <SeverityBadge severity={s.result === 'suspicious' ? 'critical' : 'warning'} />
                  <b>{s.label}</b>
                </div>
                <div className="muted" style={{ marginTop: 2 }}>{s.detail}</div>
              </div>
            ))}
            {doc.forgery?.llm && (
              <div style={{ marginTop: 10, fontSize: 12.5 }}>
                <div className="muted" style={{ marginBottom: 4 }}>LLM verdict: <b>{doc.forgery.llm.verdict}</b> ({Math.round((doc.forgery.llm.confidence ?? 0) * 100)}% confidence)</div>
                {(doc.forgery.llm.notes ?? []).map((n, i) => (
                  <div key={i} style={{ padding: '1px 0' }}>· {n}</div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="inspector-section">
          <div className="inspector-title"><FileText size={14} /> Extracted fields ({extracted.length})</div>
          {extracted.length > 0 ? (
            <table className="fields">
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
            <div className="muted" style={{ fontSize: 13 }}>No structured fields extracted.</div>
          )}
        </div>

        <div className="inspector-section">
          <div className="inspector-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><FileText size={14} /> Raw OCR text</span>
            <button className="btn ghost sm" onClick={copyRaw}>
              <Copy size={13} /> {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
          <pre className="raw-text">{doc.raw_text_preview || '(no raw text)'}</pre>
        </div>

        {issues.length > 0 && (
          <div className="inspector-section">
            <div className="inspector-title"><ShieldAlert size={14} /> Verification issues</div>
            <ul className="issues">
              {issues.map((iss, i) => (
                <li key={i}><SeverityBadge severity={iss.severity} /> {iss.message}</li>
              ))}
            </ul>
            {actions.length > 0 && (
              <div style={{ marginTop: 10, fontSize: 12.5 }}>
                <div className="muted" style={{ marginBottom: 4 }}>Recommended actions:</div>
                {actions.map((a, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, padding: '2px 0' }}>
                    <CheckCircle2 size={14} style={{ color: 'var(--cyan)', flexShrink: 0, marginTop: 1 }} /> {a}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
