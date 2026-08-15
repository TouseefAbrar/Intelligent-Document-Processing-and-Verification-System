import { AlertTriangle, Trash2, X } from 'lucide-react';

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}

export function ConfirmModal({ open, title, message, confirmLabel = 'Delete', onConfirm, onCancel, busy }: Props) {
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={busy ? undefined : onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ width: 46, height: 46, borderRadius: 13, display: 'grid', placeItems: 'center', background: 'rgba(251,113,133,0.14)', border: '1px solid rgba(251,113,133,0.35)', color: 'var(--rose)' }}>
          <AlertTriangle size={22} />
        </div>
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="btn-row">
          <button className="btn ghost" onClick={onCancel} disabled={busy}>
            <X size={15} /> Cancel
          </button>
          <button className="btn danger" onClick={onConfirm} disabled={busy}>
            {busy ? <span className="spinner" style={{ width: 13, height: 13 }} /> : <Trash2 size={15} />}
            {busy ? 'Deleting…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
