export interface HealthStatus {
  status: string;
  app: string;
  version: string;
  groq_connected: boolean;
  ocr_provider: string;
}

export interface Issue {
  field: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
}

export interface Verification {
  status: string;
  confidence: number;
  issues: Issue[];
  recommended_actions: string[];
  engine?: string;
}

export interface Quality {
  blur?: number;
  brightness?: number;
  contrast?: number;
  quality_score?: number;
  issues?: string[];
  is_blurry?: boolean;
}

export interface DuplicateInfo {
  is_duplicate: boolean;
  similarity: number;
  method?: string;
  matched_file?: string;
}

export interface ForgerySignal {
  name: string;
  label: string;
  result: 'clear' | 'warning' | 'suspicious';
  score: number;
  detail: string;
  decisive?: boolean;
}

export interface ForgeryInfo {
  detected: boolean;
  level: 'GREEN' | 'YELLOW' | 'RED';
  score: number;
  confidence: number;
  engine?: string;
  signals: ForgerySignal[];
  summary?: string[];
  note?: string;
  llm?: {
    verdict?: string;
    confidence?: number;
    notes?: string[];
    recommended_action?: string;
  } | null;
}

export interface DocumentSummary {
  id: number;
  file_name: string;
  doc_type: string;
  expected_doc_type: string;
  classification_confidence: number;
  ocr_confidence: number;
  verification_status: string;
  language: string;
  file_size: number;
}

export interface DocumentDetail extends DocumentSummary {
  extracted: Record<string, unknown>;
  quality: Quality;
  duplicate: DuplicateInfo;
  verification: Verification;
  forgery: ForgeryInfo;
  ocr_provider: string;
  raw_text_preview: string;
  created_at: string;
}

export interface SubmissionDetail {
  id: number;
  applicant_ref: string;
  status: string;
  completeness_score: number;
  overall_confidence: number;
  missing_documents: string[];
  duplicate_documents: string[];
  summary: Record<string, unknown>;
  report_url: string;
  documents: DocumentDetail[];
  created_at: string;
}

export interface SubmissionListRow {
  id: number;
  applicant_ref: string;
  status: string;
  completeness_score: number;
  overall_confidence: number;
  missing_documents: string[];
  duplicate_documents: string[];
  summary: Record<string, unknown>;
  report_url: string;
  documents: DocumentSummary[];
  created_at: string;
}

const BASE = '/api/v1';

export class ApiError extends Error {}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError('Cannot reach the backend. Is the server running?');
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* ignore */
    }
    throw new ApiError(String(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthStatus>(`${BASE}/health`),
  uploadSubmission: (files: File[], expectedTypes: string[], applicantRef: string) => {
    const form = new FormData();
    files.forEach((f) => form.append('files', f));
    expectedTypes.forEach((t) => form.append('expected_types', t));
    form.append('applicant_ref', applicantRef);
    return request<SubmissionDetail>(`${BASE}/submissions/upload`, { method: 'POST', body: form });
  },
  listSubmissions: () => request<SubmissionListRow[]>(`${BASE}/submissions`),
  getSubmission: (id: number) => request<SubmissionDetail>(`${BASE}/submissions/${id}`),
  deleteSubmission: (id: number) =>
    request<void>(`${BASE}/submissions/${id}`, { method: 'DELETE' }),
  deleteDocument: (id: number) =>
    request<void>(`${BASE}/documents/${id}`, { method: 'DELETE' }),
  reportUrl: (id: number, format: 'html' | 'pdf' = 'html') =>
    `${BASE}/submissions/${id}/report?format=${format}`,
  exportCsvUrl: () => `${BASE}/submissions/export.csv`,
};
