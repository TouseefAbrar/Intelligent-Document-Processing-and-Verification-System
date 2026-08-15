import { AlertTriangle, CheckCircle2, Clock3, CopyX, FileX2, Images, Layers, Loader2, ShieldAlert, XCircle } from 'lucide-react';

const STATUS_ICON: Record<string, JSX.Element> = {
  PASSED: <CheckCircle2 size={12} />,
  FLAGGED: <AlertTriangle size={12} />,
  FAILED: <XCircle size={12} />,
  MISSING: <FileX2 size={12} />,
  'INVALID FILE TYPE': <FileX2 size={12} />,
  DUPLICATE: <CopyX size={12} />,
  BLURRY: <Images size={12} />,
  'WRONG DOCUMENT TYPE': <Layers size={12} />,
  'INCONSISTENCY DETECTED': <AlertTriangle size={12} />,
  PENDING: <Clock3 size={12} />,
  PROCESSING: <Loader2 size={12} className="spin-slow" />,
};

export function StatusBadge({ status }: { status: string }) {
  const cls = status.replace(/\s+/g, '-');
  return (
    <span className={`badge ${cls}`}>
      {STATUS_ICON[status] ?? <ShieldAlert size={12} />}
      {status}
    </span>
  );
}

const SEV_ICON: Record<string, JSX.Element> = {
  critical: <XCircle size={12} />,
  warning: <AlertTriangle size={12} />,
  info: <Clock3 size={12} />,
};

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={`badge ${severity}`}>
      {SEV_ICON[severity] ?? <ShieldAlert size={12} />}
      {severity.toUpperCase()}
    </span>
  );
}
