import { useRef, useState } from 'react';
import { FilePlus2, FileText, UploadCloud, X } from 'lucide-react';
import { REQUIRED_DOCS, docLabel } from '../api/analytics';

interface Props {
  onSelect: (files: File[]) => void;
  files: File[];
  expectedTypes: string[];
  onTypeChange: (index: number, type: string) => void;
  onClear: () => void;
  disabled?: boolean;
}

const ACCEPT = '.pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp';

export function UploadZone({ onSelect, files, expectedTypes, onTypeChange, onClear, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    onSelect(Array.from(list));
  };

  return (
    <div>
      <div
        className={`dropzone ${dragging ? 'dragging' : ''}`}
        onClick={() => !disabled && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
      >
        <div className="dz-icon"><UploadCloud size={28} /></div>
        <div style={{ fontSize: 15, fontWeight: 700 }}>Drag &amp; drop documents here</div>
        <div className="muted" style={{ marginTop: 6, fontSize: 13 }}>
          or click to browse — PDF, PNG, JPG, TIFF (max 25MB each)
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        onChange={(e) => addFiles(e.target.files)}
      />

      {files.length > 0 && (
        <div className="file-list stacked">
          {files.map((f, i) => (
            <div className="file-row" key={i}>
              <span className="file-chip">
                <FileText size={13} /> {f.name}
                <span className="muted">({(f.size / 1024).toFixed(0)} KB)</span>
              </span>
              <select
                className="doc-type-select"
                value={expectedTypes[i] ?? ''}
                onChange={(e) => onTypeChange(i, e.target.value)}
                disabled={disabled}
                title="What is this document supposed to be?"
              >
                <option value="">Auto-detect type</option>
                {REQUIRED_DOCS.map((t) => (
                  <option key={t} value={t}>{docLabel(t)}</option>
                ))}
              </select>
            </div>
          ))}
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn ghost sm" onClick={onClear} disabled={disabled}>
              <X size={14} /> Clear
            </button>
            <span className="muted" style={{ fontSize: 12, marginLeft: 4 }}>
              <FilePlus2 size={13} style={{ verticalAlign: '-2px' }} /> {files.length} file{files.length > 1 ? 's' : ''} queued
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
