import type { DocumentSummary, SubmissionDetail, SubmissionListRow } from './client';

export interface DocAgg {
  type: string;
  total: number;
  passed: number;
  flagged: number;
  failed: number;
  avgClassConf: number;
  avgOcrConf: number;
}

export interface TrendPoint {
  label: string;
  passed: number;
  flagged: number;
  failed: number;
  total: number;
}

export interface HistBin {
  range: string;
  count: number;
}

export interface ScatterPoint {
  completeness: number;
  confidence: number;
  status: string;
}

export interface Metrics {
  totalSubmissions: number;
  totalDocuments: number;
  rejectedDocs: number;
  passRate: number;
  flaggedRate: number;
  failRate: number;
  rejectedRate: number;
  autoApproveRate: number;
  autoVerifiedDocs: number;
  avgCompleteness: number;
  avgConfidence: number;
  duplicatesDetected: number;
  missingFields: string[];
  topMissingDoc: string;
  lastProcessedAt: string | null;
  languages: Record<string, number>;
}

const DOC_LABELS: Record<string, string> = {
  resume: 'Resume',
  cnic: 'CNIC',
  offer_letter: 'Offer Letter',
  degree: 'Degree',
  transcript: 'Transcript',
  internship_letter: 'Internship Letter',
  recommendation_letter: 'Recommendation Letter',
  certificate: 'Certificate',
  other: 'Other',
};

export const REQUIRED_DOCS = ['resume', 'cnic', 'offer_letter', 'degree', 'transcript'];

export const REJECTED_STATUSES = [
  'INVALID FILE TYPE',
  'DUPLICATE',
  'BLURRY',
  'WRONG DOCUMENT TYPE',
  'FORGERY DETECTED',
];

export const isRejected = (status: string) => REJECTED_STATUSES.includes(status);

export const DOC_COLORS: Record<string, string> = {
  resume: '#22d3ee',
  cnic: '#fbbf24',
  offer_letter: '#a3e635',
  degree: '#a78bfa',
  transcript: '#f472b6',
  internship_letter: '#34d399',
  recommendation_letter: '#38bdf8',
  certificate: '#fb7185',
  other: '#8b93a7',
};

const DOC_ALIASES: Record<string, string[]> = {
  resume: ['resume', 'cv', 'curriculum vitae'],
  cnic: ['cnic', 'id card', 'identity card', 'national id card', 'national identity card'],
  offer_letter: ['offer letter', 'letter of offer', 'job offer', 'employment offer', 'offerletter', 'internship offer', 'internship letter', 'internship_letter', 'internship offer letter'],
  degree: ['degree', 'degree certificate', 'graduation certificate', 'diploma'],
  transcript: ['transcript', 'transcript of records', 'grade sheet', 'gradesheet', 'marksheet', 'marks sheet'],
  recommendation_letter: ['recommendation letter', 'reference letter'],
  certificate: ['certificate', 'participation certificate'],
};

const ALIAS_TO_CANONICAL: Record<string, string> = Object.entries(DOC_ALIASES).reduce(
  (acc, [canonical, aliases]) => {
    for (const a of aliases) acc[a] = canonical;
    return acc;
  },
  {} as Record<string, string>,
);

export function normalizeDocType(raw: string): string {
  if (!raw) return 'other';
  const key = raw.trim().toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
  return ALIAS_TO_CANONICAL[key] ?? 'other';
}

export const docColor = (t: string) => DOC_COLORS[normalizeDocType(t)] ?? '#8b93a7';

export const docLabel = (t: string) => DOC_LABELS[normalizeDocType(t)] ?? t.replace(/_/g, ' ');

export interface RequiredDocStatus {
  type: string;
  label: string;
  presentCount: number;
  missingCount: number;
  rate: number;
  color: string;
}

export function requiredDocsTracker(rows: SubmissionListRow[]): RequiredDocStatus[] {
  return REQUIRED_DOCS.map((type) => {
    let presentCount = 0;
    for (const s of rows) {
      const hasValid = s.documents.some(
        (d) => normalizeDocType(d.doc_type) === type && !isRejected(d.verification_status),
      );
      if (hasValid) presentCount += 1;
    }
    const total = rows.length;
    return {
      type,
      label: docLabel(type),
      presentCount,
      missingCount: total - presentCount,
      rate: total ? presentCount / total : 0,
      color: docColor(type),
    };
  });
}

export function completenessChecklist(sub: SubmissionDetail): { type: string; label: string; present: boolean; doc?: DocumentSummary }[] {
  return REQUIRED_DOCS.map((type) => {
    // A rejected upload (invalid/blurry/duplicate/…) does not satisfy the
    // required-document slot — matches the backend coverage computation.
    const doc = sub.documents.find(
      (d) => normalizeDocType(d.doc_type) === type && !isRejected(d.verification_status),
    );
    return { type, label: docLabel(type), present: Boolean(doc), doc };
  });
}

export function computeMetrics(rows: SubmissionListRow[]): Metrics {
  const totalSubmissions = rows.length;
  let totalDocuments = 0;
  let passedDocs = 0;
  let flaggedDocs = 0;
  let failedDocs = 0;
  let rejectedDocs = 0;
  let passedSubs = 0;
  let sumCompleteness = 0;
  let sumConfidence = 0;
  let duplicatesDetected = 0;
  const missingMap: Record<string, number> = {};
  const languages: Record<string, number> = {};
  let lastProcessedAt: string | null = null;

  for (const s of rows) {
    for (const d of s.documents) {
      totalDocuments += 1;
      const st = d.verification_status;
      if (isRejected(st)) rejectedDocs += 1;
      else if (st === 'PASSED') passedDocs += 1;
      else if (st === 'FLAGGED') flaggedDocs += 1;
      else if (st === 'FAILED') failedDocs += 1;
    }
    if (s.status === 'PASSED') passedSubs += 1;
    sumCompleteness += s.completeness_score;
    sumConfidence += s.overall_confidence;
    duplicatesDetected += s.duplicate_documents.length;
    for (const m of s.missing_documents) missingMap[m] = (missingMap[m] ?? 0) + 1;
    if (s.created_at && s.created_at > (lastProcessedAt ?? '')) lastProcessedAt = s.created_at;
    for (const d of s.documents) {
      if (d.language) languages[d.language] = (languages[d.language] ?? 0) + 1;
    }
  }

  // Rates are computed over the documents that actually reached the
  // verification engine. Rejected uploads (invalid type / duplicate / blurry /
  // wrong document) were short-circuited before verification and are reported
  // separately so they never inflate the pass rate.
  const processed = totalDocuments - rejectedDocs;
  const topMissing = Object.entries(missingMap).sort((a, b) => b[1] - a[1])[0];
  return {
    totalSubmissions,
    totalDocuments,
    rejectedDocs,
    passRate: processed ? passedDocs / processed : 0,
    flaggedRate: processed ? flaggedDocs / processed : 0,
    failRate: processed ? failedDocs / processed : 0,
    rejectedRate: totalDocuments ? rejectedDocs / totalDocuments : 0,
    autoApproveRate: totalSubmissions ? passedSubs / totalSubmissions : 0,
    autoVerifiedDocs: passedDocs,
    avgCompleteness: totalSubmissions ? sumCompleteness / totalSubmissions : 0,
    avgConfidence: totalSubmissions ? sumConfidence / totalSubmissions : 0,
    duplicatesDetected,
    missingFields: Object.keys(missingMap),
    topMissingDoc: topMissing ? docLabel(topMissing[0]) : 'None',
    lastProcessedAt,
    languages,
  };
}

export function docTypeAggregates(rows: SubmissionListRow[]): DocAgg[] {
  const map = new Map<string, DocAgg>();
  for (const s of rows) {
    for (const d of s.documents) {
      const type = normalizeDocType(d.doc_type);
      let agg = map.get(type);
      if (!agg) {
        agg = { type, total: 0, passed: 0, flagged: 0, failed: 0, avgClassConf: 0, avgOcrConf: 0 };
        map.set(type, agg);
      }
      agg.total += 1;
      if (d.verification_status === 'PASSED') agg.passed += 1;
      else if (d.verification_status === 'FLAGGED') agg.flagged += 1;
      else if (d.verification_status === 'FAILED' || isRejected(d.verification_status)) agg.failed += 1;
      agg.avgClassConf += d.classification_confidence;
      agg.avgOcrConf += d.ocr_confidence;
    }
  }
  return [...map.values()]
    .map((a) => ({
      ...a,
      avgClassConf: a.total ? Math.round((a.avgClassConf / a.total) * 100) / 100 : 0,
      avgOcrConf: a.total ? Math.round((a.avgOcrConf / a.total) * 100) / 100 : 0,
    }))
    .sort((a, b) => b.total - a.total);
}

export function statusDistribution(rows: SubmissionListRow[]) {
  const map: Record<string, number> = {};
  for (const s of rows) map[s.status] = (map[s.status] ?? 0) + 1;
  return Object.entries(map).map(([name, value]) => ({ name, value }));
}

export function confidenceTrend(rows: SubmissionListRow[]): TrendPoint[] {
  const byDay = new Map<string, TrendPoint>();
  for (const s of rows) {
    const day = (s.created_at ?? '').slice(0, 10);
    if (!day) continue;
    let p = byDay.get(day);
    if (!p) {
      p = { label: day, passed: 0, flagged: 0, failed: 0, total: 0 };
      byDay.set(day, p);
    }
    p.total += 1;
    if (s.status === 'PASSED') p.passed += 1;
    else if (s.status === 'FLAGGED') p.flagged += 1;
    else if (s.status === 'FAILED') p.failed += 1;
  }
  return [...byDay.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([, v]) => v);
}

export function confidenceHistogram(rows: SubmissionListRow[], buckets = 5): HistBin[] {
  const binSize = 1 / buckets;
  const bins: HistBin[] = Array.from({ length: buckets }, (_, i) => ({
    range: `${Math.round((i * binSize) * 100)}–${Math.round(((i + 1) * binSize) * 100)}%`,
    count: 0,
  }));
  for (const s of rows) {
    const idx = Math.min(buckets - 1, Math.floor(s.overall_confidence / binSize));
    bins[idx].count += 1;
  }
  return bins;
}

export function scatterPoints(rows: SubmissionListRow[]): ScatterPoint[] {
  return rows.map((s) => ({
    completeness: Math.round(s.completeness_score * 100),
    confidence: Math.round(s.overall_confidence * 100),
    status: s.status,
  }));
}

export function ocrConfidenceByType(rows: SubmissionListRow[]) {
  const agg = docTypeAggregates(rows);
  return agg.map((a) => ({
    type: docLabel(a.type),
    'OCR confidence': Math.round(a.avgOcrConf * 100),
    'Classification': Math.round(a.avgClassConf * 100),
  }));
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

export function formatPct(v: number, digits = 0): string {
  return `${(v * 100).toFixed(digits)}%`;
}

export function timeAgo(iso: string): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function listDocs(rows: SubmissionListRow[]): (DocumentSummary & { submission_id: number })[] {
  return rows.flatMap((s) => s.documents.map((d) => ({ ...d, submission_id: s.id })));
}
