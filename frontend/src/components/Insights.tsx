import { BrainCircuit, CheckCircle2, Info, ShieldAlert, Sparkles, Zap } from 'lucide-react';
import type { HealthStatus, SubmissionListRow } from '../api/client';
import { computeMetrics, formatPct } from '../api/analytics';

export function Insights({ rows, health }: { rows: SubmissionListRow[]; health: HealthStatus | null }) {
  const m = computeMetrics(rows);

  if (m.totalSubmissions === 0) {
    return (
      <div className="insights">
        <div className="insight info">
          <Sparkles size={18} />
          <div>
            <b>Ready when you are</b>
            Upload a batch of applicant documents to start the intelligence engine. The pipeline runs OCR → classification → extraction → verification automatically.
          </div>
        </div>
        <div className="insight info">
          <BrainCircuit size={18} />
          <div>
            <b>AI-assisted verification</b>
            {health?.groq_connected ? 'Groq LLM decision support is connected and will augment every verdict.' : 'Groq is offline — rules-based verification will run, AI augmentation is disabled.'}
          </div>
        </div>
      </div>
    );
  }

  const insights: { tone: 'ok' | 'warn' | 'info'; text: string }[] = [];

  if (m.autoApproveRate === 1) insights.push({ tone: 'ok', text: `All ${m.totalSubmissions} submissions passed verification automatically.` });
  else if (m.autoApproveRate > 0) insights.push({ tone: 'warn', text: `${formatPct(m.autoApproveRate)} of submissions passed automatically — ${m.flaggedRate > 0 ? 'some documents need manual review' : 'others were rejected by the rules engine'}.` });
  else insights.push({ tone: 'warn', text: 'No submission passed automatically yet. Review the flagged/failed documents below.' });

  if (m.duplicatesDetected > 0) insights.push({ tone: 'warn', text: `${m.duplicatesDetected} possible duplicate document${m.duplicatesDetected > 1 ? 's' : ''} detected across batches.` });
  else if (m.totalSubmissions > 0) insights.push({ tone: 'ok', text: 'No duplicate documents detected. Image-hash deduplication is running on every batch.' });

  if (m.topMissingDoc !== 'None') insights.push({ tone: 'info', text: `Most commonly missing document: ${m.topMissingDoc}. Consider reminding applicants to include it.` });
  if (m.avgConfidence >= 0.75) insights.push({ tone: 'ok', text: `Average verification confidence is high (${formatPct(m.avgConfidence)}).` });
  else insights.push({ tone: 'warn', text: `Average confidence (${formatPct(m.avgConfidence)}) is low — scanned copies may be blurry or hard to read.` });

  if (health?.groq_connected) insights.push({ tone: 'info', text: `Groq AI connected (${health.ocr_provider} OCR provider). All verdicts include rule + optional LLM layers.` });

  return (
    <div className="insights">
      {insights.slice(0, 4).map((ins, i) => (
        <div className={`insight ${ins.tone}`} key={i}>
          {ins.tone === 'ok' ? <CheckCircle2 size={18} /> : ins.tone === 'warn' ? <ShieldAlert size={18} /> : <Info size={18} />}
          <div>{ins.text}</div>
        </div>
      ))}
    </div>
  );
}

export function EnginePulse({ health }: { health: HealthStatus | null }) {
  if (!health) return null;
  return (
    <div className="health-pill">
      <span className={`dot ${health.groq_connected ? 'ok' : ''}`} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Zap size={13} style={{ color: 'var(--amber)' }} />
        {health.groq_connected ? 'Groq AI online' : 'Groq offline'} · OCR {health.ocr_provider}
      </div>
      <span className="muted">v{health.version}</span>
    </div>
  );
}
