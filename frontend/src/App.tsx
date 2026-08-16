import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  ArrowDown,
  ArrowUp,
  BarChart3,
  Boxes,
  Clock,
  Database,
  Download,
  FileWarning,
  Gauge,
  LayoutDashboard,
  Menu,
  RefreshCw,
  ScanSearch,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react';
import { api, type DocumentDetail, type SubmissionDetail, type SubmissionListRow } from './api/client';
import { computeMetrics, docColor, docLabel, formatBytes, formatPct, listDocs, timeAgo } from './api/analytics';
import { UploadZone } from './components/UploadZone';
import { StatCard } from './components/StatCard';
import { StatusBadge } from './components/StatusBadge';
import { DocumentCard } from './components/DocumentCard';
import { SubmissionDrawer } from './components/SubmissionDrawer';
import { ConfirmModal } from './components/ConfirmModal';
import { DocInspector } from './components/DocInspector';
import { MissingTracker } from './components/MissingTracker';
import { CompletenessChecklist } from './components/CompletenessChecklist';
import { Insights, EnginePulse } from './components/Insights';
import { ConfidenceHist, CompletionGauge, DocTypeBars, OcrRadar, ScatterView, StatusDonut, TrendChart, C } from './components/Charts';

type View = 'overview' | 'verify' | 'submissions' | 'analytics';
type Phase = 'idle' | 'uploading' | 'done';

const STAGES = ['OCR extraction', 'Classification', 'Field extraction', 'Verification', 'Scoring'];

const NAV: { id: View; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'verify', label: 'Verify Documents', icon: UploadCloud },
  { id: 'submissions', label: 'Submissions', icon: Database },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
];

const VIEW_TITLE: Record<View, { t: string; s: string }> = {
  overview: { t: 'Command Center', s: 'Live numbers, missing-document alerts and the latest applicant activity.' },
  verify: { t: 'Verify Documents', s: 'Upload an applicant batch — OCR, classify, extract and verify in one pass.' },
  submissions: { t: 'Submission Registry', s: 'Every applicant batch, verdict and stored document in one place.' },
  analytics: { t: 'Analytics Lab', s: 'All charts and engine insights in one place: trends, distributions and quality.' },
};

interface ConfirmTarget {
  kind: 'submission' | 'document';
  id: number;
  name: string;
}

type SortKey = 'id' | 'applicant_ref' | 'created_at' | 'completeness_score' | 'overall_confidence' | 'status';

export default function App() {
  const [health, setHealth] = useState<Awaited<ReturnType<typeof api.health>> | null>(null);
  const [rows, setRows] = useState<SubmissionListRow[]>([]);
  const [loading, setLoading] = useState(true);

  const [view, setView] = useState<View>('overview');
  const [navOpen, setNavOpen] = useState(false);

  const [files, setFiles] = useState<File[]>([]);
  const [expectedTypes, setExpectedTypes] = useState<string[]>([]);
  const [ref, setRef] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [stageIdx, setStageIdx] = useState(0);
  const [error, setError] = useState('');
  const [result, setResult] = useState<SubmissionDetail | null>(null);

  const [drawer, setDrawer] = useState<SubmissionDetail | null>(null);
  const [inspector, setInspector] = useState<DocumentDetail | null>(null);
  const [confirm, setConfirm] = useState<ConfirmTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(new Date());
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'id', dir: -1 });

  const stageTimer = useRef<number | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const [h, s] = await Promise.all([api.health(), api.listSubmissions()]);
      setHealth(h);
      setRows(s);
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    const h = setInterval(() => { api.health().then(setHealth).catch(() => undefined); }, 30000);
    return () => { clearInterval(id); clearInterval(h); };
  }, []);

  useEffect(() => {
    if (phase === 'uploading') {
      setStageIdx(0);
      stageTimer.current = window.setInterval(() => setStageIdx((i) => Math.min(i + 1, STAGES.length - 1)), 7000);
    }
    return () => { if (stageTimer.current) window.clearInterval(stageTimer.current); };
  }, [phase]);

  const runUpload = async () => {
    if (files.length === 0) return;
    setError('');
    setPhase('uploading');
    try {
      const res = await api.uploadSubmission(files, expectedTypes, ref);
      setResult(res);
      setPhase('done');
      setFiles([]);
      setExpectedTypes([]);
      setRef('');
      loadAll();
      setView('submissions');
      setDrawer(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase('idle');
    }
  };

  const openDrawer = async (id: number) => {
    try {
      const detail = await api.getSubmission(id);
      setDrawer(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const runDelete = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      if (confirm.kind === 'submission') {
        await api.deleteSubmission(confirm.id);
        setDrawer(null);
      } else {
        await api.deleteDocument(confirm.id);
        if (drawer) {
          const fresh = await api.getSubmission(drawer.id);
          setDrawer(fresh);
        }
      }
      loadAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  const metrics = useMemo(() => computeMetrics(rows), [rows]);
  const allDocs = useMemo(() => listDocs(rows), [rows]);

  const sorted = useMemo(() => {
    const dir = sort.dir;
    return [...rows].sort((a, b) => {
      const k = sort.key;
      if (k === 'id' || k === 'completeness_score' || k === 'overall_confidence') {
        return (Number(a[k]) - Number(b[k])) * dir;
      }
      const av = String(a[k] ?? '').toLowerCase();
      const bv = String(b[k] ?? '').toLowerCase();
      return av < bv ? -1 * dir : av > bv ? 1 * dir : 0;
    });
  }, [rows, sort]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter(
      (s) =>
        String(s.id).includes(q) ||
        s.applicant_ref.toLowerCase().includes(q) ||
        s.status.toLowerCase().includes(q) ||
        s.documents.some((d) => d.doc_type.toLowerCase().includes(q) || d.verification_status.toLowerCase().includes(q))
    );
  }, [sorted, query]);

  const goView = (v: View) => { setView(v); setNavOpen(false); window.scrollTo({ top: 0 }); };

  const toggleSort = (key: SortKey) => {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === 'id' ? -1 : 1 }));
  };

  const SortHead = ({ k, children }: { k: SortKey; children: React.ReactNode }) => (
    <th onClick={() => toggleSort(k)} style={{ cursor: 'pointer', userSelect: 'none' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        {children}
        {sort.key === k && (sort.dir === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
      </span>
    </th>
  );

  const kpi = [
    { label: 'Total submissions', value: String(metrics.totalSubmissions), icon: Boxes, color: C.cyan, trend: metrics.lastProcessedAt ? timeAgo(metrics.lastProcessedAt) : undefined },
    { label: 'Documents processed', value: String(metrics.totalDocuments), icon: ScanSearch, color: C.violet, sub: `across ${metrics.totalSubmissions} submission${metrics.totalSubmissions === 1 ? '' : 's'}` },
    { label: 'Pass rate', value: formatPct(metrics.passRate), icon: Activity, color: C.emerald, sub: `${formatPct(metrics.flaggedRate)} flagged · ${formatPct(metrics.failRate)} failed · ${formatPct(metrics.rejectedRate)} rejected` },
    { label: 'Avg completeness', value: formatPct(metrics.avgCompleteness), icon: LayoutDashboard, color: C.sky, sub: metrics.topMissingDoc !== 'None' ? `top missing: ${metrics.topMissingDoc}` : 'no missing docs' },
    { label: 'Avg confidence', value: formatPct(metrics.avgConfidence), icon: BarChart3, color: C.pink, sub: 'across all verdicts' },
    { label: 'Duplicates caught', value: String(metrics.duplicatesDetected), icon: FileWarning, color: C.amber, sub: 'per-batch dhash dedupe' },
  ];

  return (
    <div className="app-shell">
      <aside className={`sidebar ${navOpen ? 'open' : ''}`}>
        <div className="brand">
          <div className="logo">EEF</div>
          <div>
            <h1>EZITECH</h1>
            <div className="tag">IDP Verification Engine</div>
          </div>
        </div>

        <div className="nav-label">Workspace</div>
        {NAV.map(({ id, label, icon: Icon }) => (
          <div key={id} className={`nav-item ${view === id ? 'active' : ''}`} onClick={() => goView(id)}>
            <Icon size={17} /> {label}
          </div>
        ))}

        <div className="sidebar-footer">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Clock size={12} /> {now.toLocaleTimeString()}
          </div>
          <div style={{ marginTop: 6 }}>EEF Developed by Touseef Abrar</div>
        </div>
      </aside>

      {navOpen && <div className="sidebar-backdrop" onClick={() => setNavOpen(false)} />}

      <main className="main">
        <div className="topbar">
          <div className="topbar-hero">Intelligent Document Processing and Verification System</div>
          <div className="topbar-divider" />
          <div className="topbar-row">
            <div className="topbar-title">
              <h2>{VIEW_TITLE[view].t}</h2>
              <p>{VIEW_TITLE[view].s}</p>
            </div>
            <div className="topbar-right">
              <EnginePulse health={health} />
              <button className="icon-btn view" title="Refresh" onClick={() => { setLoading(true); loadAll(); }}>
                <RefreshCw size={16} className={loading ? 'spin-slow' : ''} />
              </button>
              <button className="icon-btn menu-btn" title="Menu" onClick={() => setNavOpen(!navOpen)}>
                <Menu size={16} />
              </button>
            </div>
          </div>
        </div>

        {error && (
          <div className="error" style={{ marginBottom: 18 }}>
            <span style={{ flex: 1 }}>{error}</span>
            <button className="icon-btn" style={{ width: 26, height: 26, border: 'none', background: 'transparent' }} onClick={() => setError('')}>
              <X size={15} />
            </button>
          </div>
        )}

        {view === 'overview' && (
          <div className="view">
            <div className="section-head"><span className="section-title"><Gauge size={13} /> Key metrics</span></div>
            <div className="kpi-grid">
              {kpi.map((k) => <StatCard key={k.label} {...k} />)}
            </div>

            {rows.length > 0 && (
              <>
                <div className="section-head section-head-top"><span className="section-title"><FileWarning size={13} /> Document coverage</span></div>
                <div className="panel">
                  <div className="panel-header">
                    <div>
                      <h3 className="panel-title"><FileWarning size={16} /> Missing documents</h3>
                      <div className="panel-sub">Which required documents are missing from applicant batches</div>
                    </div>
                  </div>
                  <MissingTracker rows={rows} />
                </div>

                <div className="section-head section-head-top"><span className="section-title"><Clock size={13} /> Latest activity</span></div>
                <div className="panel">
                  <div className="panel-header">
                    <div>
                      <h3 className="panel-title"><Clock size={16} /> Recent submissions</h3>
                      <div className="panel-sub">Latest applicant batches</div>
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                      <a className="btn ghost sm" href={api.exportCsvUrl()} target="_blank" rel="noreferrer">
                        <Download size={14} /> CSV
                      </a>
                      <button className="btn ghost sm" onClick={() => goView('submissions')}>View all</button>
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table className="data">
                      <thead>
                        <tr><th>#</th><th>Applicant</th><th>Docs</th><th>Completeness</th><th>Confidence</th><th>Missing</th><th>Status</th><th>When</th></tr>
                      </thead>
                      <tbody>
                        {rows.slice(0, 5).map((s) => (
                          <tr key={s.id} onClick={() => openDrawer(s.id)}>
                            <td className="mono">#{s.id}</td>
                            <td>{s.applicant_ref || <span className="muted">—</span>}</td>
                            <td>{s.documents.length}</td>
                            <td>{formatPct(s.completeness_score)}</td>
                            <td>{formatPct(s.overall_confidence)}</td>
                            <td>{s.missing_documents.length > 0 ? <span className="badge FAILED">{s.missing_documents.length}</span> : <span className="muted">—</span>}</td>
                            <td><StatusBadge status={s.status} /></td>
                            <td className="muted mono">{timeAgo(s.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {view === 'verify' && (
          <div className="view">
            <div className="panel">
              <h3 className="panel-title"><UploadCloud size={16} /> New applicant batch</h3>
              <div className="panel-sub">Multiple documents per applicant are processed as one submission</div>
              <div className="section-gap" />
              <UploadZone
                onSelect={(f) => { setFiles(f); setExpectedTypes(f.map(() => '')); }}
                files={files}
                expectedTypes={expectedTypes}
                onTypeChange={(i, t) => setExpectedTypes((prev) => prev.map((x, j) => (j === i ? t : x)))}
                onClear={() => { setFiles([]); setExpectedTypes([]); }}
                disabled={phase === 'uploading'}
              />
              <div className="row" style={{ marginTop: 16 }}>
                <input type="text" placeholder="Applicant reference (optional)" value={ref} onChange={(e) => setRef(e.target.value)} disabled={phase === 'uploading'} />
                <button className="btn" onClick={runUpload} disabled={files.length === 0 || phase === 'uploading'}>
                  {phase === 'uploading' ? 'Processing…' : <><UploadCloud size={16} /> Verify Submission</>}
                </button>
              </div>
              {phase === 'uploading' && (
                <div className="progress-note">
                  <div className="spinner" />
                  <span>Intelligence pipeline running</span>
                  <div className="stages">
                    {STAGES.map((s, i) => (
                      <span key={s} className={`stage ${i < stageIdx ? 'done' : i === stageIdx ? 'on' : ''}`}>{s}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {result && phase === 'done' && (
              <>
                <div className="section-gap" />
                <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px,1fr))' }}>
                  <StatCard label="Verdict" value={result.status} icon={Activity} color={result.status === 'PASSED' ? C.emerald : result.status === 'FAILED' ? C.rose : C.amber} />
                  <StatCard label="Completeness" value={formatPct(result.completeness_score)} icon={LayoutDashboard} color={C.sky} sub={`${result.documents.length} docs checked`} />
                  <StatCard label="Confidence" value={formatPct(result.overall_confidence)} icon={BarChart3} color={C.pink} />
                  <StatCard label="Missing" value={String(result.missing_documents.length)} icon={FileWarning} color={C.rose} sub={result.missing_documents.join(', ') || 'none'} />
                </div>

                <div className="chart-grid" style={{ marginTop: 16 }}>
                  <div className="panel">
                    <div className="panel-header">
                      <div>
                        <h3 className="panel-title"><FileWarning size={16} /> Verification summary</h3>
                        <div className="panel-sub">Engine comment + recommended action</div>
                      </div>
                    </div>
                    <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>{String((result.summary as Record<string, unknown>).overall_comment ?? 'Report generated.')}</div>
                    {result.duplicate_documents.length > 0 && (
                      <div className="badge critical" style={{ marginBottom: 10 }}><FileWarning size={12} /> Duplicates: {result.duplicate_documents.join(', ')}</div>
                    )}
                    <div className="row" style={{ gap: 8 }}>
                      <a className="btn sm" href={api.reportUrl(result.id, 'html')} target="_blank" rel="noreferrer"><Download size={14} /> HTML Report</a>
                      <a className="btn ghost sm" href={api.reportUrl(result.id, 'pdf')} target="_blank" rel="noreferrer"><Download size={14} /> PDF</a>
                      <button className="btn ghost sm" onClick={() => openDrawer(result.id)}><ScanSearch size={14} /> Full analysis</button>
                    </div>
                  </div>
                  <div className="panel">
                    <div className="panel-header">
                      <div>
                        <h3 className="panel-title"><FileWarning size={16} /> Document checklist</h3>
                        <div className="panel-sub">Required set for a complete application</div>
                      </div>
                    </div>
                    <CompletenessChecklist submission={result} />
                  </div>
                </div>

                <div className="panel" style={{ marginTop: 16 }}>
                  <h3 className="panel-title"><ScanSearch size={16} /> Document-level analysis</h3>
                  <div className="doc-grid" style={{ marginTop: 12 }}>
                    {result.documents.map((d) => <DocumentCard key={d.id} doc={d} onInspect={setInspector} />)}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {view === 'submissions' && (
          <div className="view">
            <div className="row" style={{ marginBottom: 16 }}>
              <div className="search-box" style={{ flex: 1, minWidth: 240 }}>
                <BarChart3 size={15} />
                <input
                  type="text"
                  placeholder="Search by id, applicant, status or document type…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <span className="muted mono">{filtered.length} of {rows.length} submissions</span>
              <a className="btn ghost sm" href={api.exportCsvUrl()} target="_blank" rel="noreferrer"><Download size={14} /> Export CSV</a>
            </div>

            <div className="panel">
              {filtered.length === 0 ? (
                <div className="empty">No submissions match. Upload a batch from the Verify view.</div>
              ) : (
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <SortHead k="id">ID</SortHead>
                        <SortHead k="applicant_ref">Applicant</SortHead>
                        <SortHead k="created_at">Date</SortHead>
                        <th>Documents</th>
                        <SortHead k="completeness_score">Complete</SortHead>
                        <SortHead k="overall_confidence">Confidence</SortHead>
                        <th>Missing</th>
                        <SortHead k="status">Status</SortHead>
                        <th style={{ textAlign: 'right' }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((s) => (
                        <tr key={s.id} onClick={() => openDrawer(s.id)}>
                          <td className="mono">#{s.id}</td>
                          <td>{s.applicant_ref || <span className="muted">—</span>}</td>
                          <td className="muted mono" style={{ whiteSpace: 'nowrap' }}>
                            {new Date(s.created_at).toLocaleDateString()} {new Date(s.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </td>
                          <td>
                            <div className="row" style={{ gap: 4 }}>
                              {s.documents.map((d) => (
                                <span key={d.id} className="mini-chip" style={{ ['--chip' as string]: `${docColor(d.doc_type)}2e`, ['--chip-b' as string]: `${docColor(d.doc_type)}55`, color: docColor(d.doc_type) }} title={`${d.verification_status}`}>
                                  {docLabel(d.doc_type)}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td>
                            <div style={{ minWidth: 70 }}>
                              <div className="m-label" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--muted)', marginBottom: 3 }}>
                                <b className="mono">{formatPct(s.completeness_score)}</b>
                              </div>
                              <div className="bar"><div style={{ width: `${s.completeness_score * 100}%` }} /></div>
                            </div>
                          </td>
                          <td>{formatPct(s.overall_confidence)}</td>
                          <td>
                            {s.missing_documents.length > 0 ? (
                              <div className="row" style={{ gap: 4 }}>
                                {s.missing_documents.map((m) => (
                                  <span key={m} className="mini-chip miss" title={`${m} missing`}>{docLabel(m)}</span>
                                ))}
                              </div>
                            ) : (
                              <span className="muted">—</span>
                            )}
                          </td>
                          <td><StatusBadge status={s.status} /></td>
                          <td>
                            <div className="actions" onClick={(e) => e.stopPropagation()}>
                              <button className="icon-btn view" title="View analysis" onClick={() => openDrawer(s.id)}><ScanSearch size={15} /></button>
                              <button className="icon-btn" title="Delete submission" onClick={() => setConfirm({ kind: 'submission', id: s.id, name: s.applicant_ref || `#${s.id}` })}><Trash2 size={15} /></button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {allDocs.length > 0 && (
              <div className="panel" style={{ marginTop: 16 }}>
                <div className="panel-header">
                  <div>
                    <h3 className="panel-title"><Database size={16} /> All processed documents</h3>
                    <div className="panel-sub">{allDocs.length} documents across every submission</div>
                  </div>
                </div>
                <div className="doc-grid">
                  {allDocs.slice(0, 6).map((d) => (
                    <div className="doc-card" key={d.id} style={{ cursor: 'pointer' }} onClick={() => openDrawer(d.submission_id)}>
                      <div className="doc-head">
                        <div style={{ minWidth: 0 }}>
                          <div className="doc-name">{d.file_name}</div>
                          <div className="doc-meta">
                            <span className="doc-type-chip" style={{ ['--chip' as string]: `${docColor(d.doc_type)}2e`, ['--chip-b' as string]: `${docColor(d.doc_type)}55`, color: docColor(d.doc_type) }}>
                              {docLabel(d.doc_type)}
                            </span> · {formatBytes(d.file_size)}
                          </div>
                        </div>
                        <StatusBadge status={d.verification_status} />
                      </div>
                      <div className="metric-row">
                        <div className="metric">
                          <div className="m-label"><span>OCR</span><b>{Math.round(d.ocr_confidence * 100)}%</b></div>
                          <div className="bar good"><div style={{ width: `${d.ocr_confidence * 100}%` }} /></div>
                        </div>
                        <div className="metric">
                          <div className="m-label"><span>Class</span><b>{Math.round(d.classification_confidence * 100)}%</b></div>
                          <div className="bar good"><div style={{ width: `${d.classification_confidence * 100}%` }} /></div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {view === 'analytics' && (
          <div className="view">
            <div className="section-head"><span className="section-title"><Sparkles size={13} /> Engine insights</span></div>
            <Insights rows={rows} health={health} />

            <div className="section-head section-head-top"><span className="section-title"><BarChart3 size={13} /> Charts &amp; distributions</span></div>
            <div className="chart-grid cols-2">
              <div className="panel chart-card">
                <h3 className="panel-title"><span className="chart-title-icon"><Activity size={15} /></span> Status distribution</h3>
                <div className="panel-sub">Verdicts across all batches</div>
                <StatusDonut rows={rows} />
              </div>
              <div className="panel chart-card">
                <h3 className="panel-title"><span className="chart-title-icon"><BarChart3 size={15} /></span> Auto-approval gauge</h3>
                <div className="panel-sub">Documents auto-verified by the engine without manual review</div>
                <CompletionGauge pct={metrics.passRate} display={metrics.autoVerifiedDocs} label="docs auto-verified" />
              </div>
            </div>

            <div className="chart-grid cols-3">
              <div className="panel chart-card">
                <h3 className="panel-title"><span className="chart-title-icon"><Activity size={15} /></span> Verification trend</h3>
                <div className="panel-sub">Batch outcomes over time</div>
                <TrendChart rows={rows} />
              </div>
              <div className="panel chart-card">
                <h3 className="panel-title"><span className="chart-title-icon"><BarChart3 size={15} /></span> Confidence histogram</h3>
                <div className="panel-sub">Spread of overall verification confidence</div>
                <ConfidenceHist rows={rows} />
              </div>
              <div className="panel chart-card">
                <h3 className="panel-title"><span className="chart-title-icon"><Boxes size={15} /></span> Completeness × confidence</h3>
                <div className="panel-sub">Quadrant: strong candidates cluster top-right</div>
                <ScatterView rows={rows} />
              </div>
            </div>

            <div className="chart-grid cols-2">
              <div className="panel chart-card">
                <h3 className="panel-title"><span className="chart-title-icon"><Database size={15} /></span> Documents by type</h3>
                <div className="panel-sub">Verification result per document category</div>
                <DocTypeBars rows={rows} />
              </div>
              <div className="panel chart-card">
                <h3 className="panel-title"><span className="chart-title-icon"><ScanSearch size={15} /></span> OCR vs classification</h3>
                <div className="panel-sub">Average confidence by document type</div>
                <OcrRadar rows={rows} />
              </div>
            </div>
          </div>
        )}

        <footer>EEF · Intelligent Document Processing &amp; Verification System · Developed by Touseef Abrar</footer>
      </main>

      {drawer && (
        <SubmissionDrawer
          submission={drawer}
          onClose={() => setDrawer(null)}
          onDeleteDocument={(d) => setConfirm({ kind: 'document', id: d.id, name: d.file_name })}
          onDeleteSubmission={() => setConfirm({ kind: 'submission', id: drawer.id, name: drawer.applicant_ref || `#${drawer.id}` })}
          onInspect={setInspector}
        />
      )}

      {inspector && <DocInspector doc={inspector} onClose={() => setInspector(null)} />}

      <ConfirmModal
        open={confirm !== null}
        title={`Delete ${confirm?.kind === 'document' ? 'document' : 'submission'}?`}
        message={
          confirm?.kind === 'document'
            ? `This permanently deletes "${confirm.name}" and its stored file from the registry. This cannot be undone.`
            : `Submission ${confirm?.name} and all of its documents will be permanently deleted. This cannot be undone.`
        }
        confirmLabel={confirm?.kind === 'document' ? 'Delete document' : 'Delete submission'}
        busy={busy}
        onCancel={() => !busy && setConfirm(null)}
        onConfirm={runDelete}
      />
    </div>
  );
}
