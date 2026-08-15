import type { SubmissionListRow } from '../api/client';
import {
  confidenceHistogram,
  confidenceTrend,
  docTypeAggregates,
  ocrConfidenceByType,
  scatterPoints,
  statusDistribution,
} from '../api/analytics';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';

export const C = {
  cyan: '#22d3ee',
  violet: '#a78bfa',
  pink: '#f472b6',
  emerald: '#34d399',
  amber: '#fbbf24',
  rose: '#fb7185',
  sky: '#38bdf8',
  grid: 'rgba(255,255,255,0.06)',
  tick: '#8b93a7',
};

const STATUS_COLOR: Record<string, string> = {
  PASSED: C.emerald,
  FLAGGED: C.amber,
  FAILED: C.rose,
  REJECTED: C.rose,
  PROCESSING: C.sky,
  PENDING: C.violet,
};

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'rgba(10,14,28,0.96)',
      border: '1px solid rgba(255,255,255,0.16)',
      borderRadius: 10,
      padding: '8px 12px',
      fontSize: 12,
      fontFamily: 'var(--mono)',
      boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
    }}>
      {label != null && <div style={{ color: '#8b93a7', marginBottom: 4 }}>{label}</div>}
      {payload.map((p: any, i: number) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#e6eaf2' }}>
          <span style={{ width: 9, height: 9, borderRadius: 3, background: p.color || p.fill || C.cyan, display: 'inline-block' }} />
          {p.name}: <b>{typeof p.value === 'number' ? p.value.toFixed(2) : p.value}</b>
        </div>
      ))}
    </div>
  );
}

export function StatusDonut({ rows }: { rows: SubmissionListRow[] }) {
  const data = statusDistribution(rows).map((d) => ({ ...d, color: STATUS_COLOR[d.name] ?? C.violet }));
  const total = data.reduce((a, b) => a + b.value, 0);
  return (
    <>
      <div style={{ position: 'relative', height: 160 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="86%" paddingAngle={3} stroke="rgba(255,255,255,0.08)" strokeWidth={1}>
              {data.map((d, i) => <Cell key={i} fill={d.color} />)}
            </Pie>
            <Tooltip content={<ChartTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', pointerEvents: 'none' }}>
          <div style={{ textAlign: 'center' }}>
            <div className="kpi-value" style={{ fontSize: 22 }}>{total}</div>
            <div className="muted" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1 }}>submissions</div>
          </div>
        </div>
      </div>
      <div className="chart-legend" style={{ justifyContent: 'center' }}>
        {data.map((d) => (
          <span key={d.name}><i style={{ background: d.color }} /> {d.name} · {d.value}</span>
        ))}
      </div>
    </>
  );
}

export function DocTypeBars({ rows }: { rows: SubmissionListRow[] }) {
  const data = docTypeAggregates(rows).map((a) => ({
    name: a.type,
    Passed: a.passed,
    Flagged: a.flagged,
    Failed: a.failed,
  }));
  return (
    <ResponsiveContainer width="100%" height={195}>
      <BarChart data={data} barSize={20}>
        <defs>
          <linearGradient id="gDocPass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.emerald} stopOpacity={0.95} />
            <stop offset="100%" stopColor={C.emerald} stopOpacity={0.55} />
          </linearGradient>
          <linearGradient id="gDocFlag" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.amber} stopOpacity={0.95} />
            <stop offset="100%" stopColor={C.amber} stopOpacity={0.55} />
          </linearGradient>
          <linearGradient id="gDocFail" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.rose} stopOpacity={0.95} />
            <stop offset="100%" stopColor={C.rose} stopOpacity={0.55} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
        <XAxis dataKey="name" tick={{ fill: C.tick, fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: C.tick, fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="Passed" stackId="a" fill="url(#gDocPass)" radius={[0, 0, 0, 0]} />
        <Bar dataKey="Flagged" stackId="a" fill="url(#gDocFlag)" />
        <Bar dataKey="Failed" stackId="a" fill="url(#gDocFail)" radius={[6, 6, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ConfidenceHist({ rows }: { rows: SubmissionListRow[] }) {
  const data = confidenceHistogram(rows);
  return (
    <ResponsiveContainer width="100%" height={195}>
      <BarChart data={data}>
        <defs>
          <linearGradient id="gHist" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.95} />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.45} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
        <XAxis dataKey="range" tick={{ fill: C.tick, fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: C.tick, fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Bar dataKey="count" name="Submissions" radius={[6, 6, 0, 0]} fill="url(#gHist)">
          {data.map((d, i) => <Cell key={i} fill={i === data.length - 1 ? C.emerald : undefined} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TrendChart({ rows }: { rows: SubmissionListRow[] }) {
  const data = confidenceTrend(rows);
  if (data.length === 0) return <div className="empty">No data yet.</div>;
  return (
    <ResponsiveContainer width="100%" height={195}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="gPass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.emerald} stopOpacity={0.45} />
            <stop offset="100%" stopColor={C.emerald} stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gFlag" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.amber} stopOpacity={0.4} />
            <stop offset="100%" stopColor={C.amber} stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gFail" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.rose} stopOpacity={0.4} />
            <stop offset="100%" stopColor={C.rose} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
        <XAxis dataKey="label" tick={{ fill: C.tick, fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: C.tick, fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} />
        <Area type="monotone" dataKey="passed" name="Passed" stroke={C.emerald} fill="url(#gPass)" strokeWidth={2} />
        <Area type="monotone" dataKey="flagged" name="Flagged" stroke={C.amber} fill="url(#gFlag)" strokeWidth={2} />
        <Area type="monotone" dataKey="failed" name="Failed" stroke={C.rose} fill="url(#gFail)" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function ScatterView({ rows }: { rows: SubmissionListRow[] }) {
  const data = scatterPoints(rows).map((d) => ({ ...d, fill: STATUS_COLOR[d.status] ?? C.violet }));
  return (
    <ResponsiveContainer width="100%" height={195}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
        <XAxis type="number" dataKey="completeness" name="Completeness %" domain={[0, 100]} tick={{ fill: C.tick, fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis type="number" dataKey="confidence" name="Confidence %" domain={[0, 100]} tick={{ fill: C.tick, fontSize: 11 }} axisLine={false} tickLine={false} />
        <ZAxis range={[80, 120]} />
        <Tooltip content={<ChartTooltip />} cursor={{ strokeDasharray: '3 3' }} />
        <Scatter data={data}>
          {data.map((d, i) => <Cell key={i} fill={d.fill} fillOpacity={0.85} />)}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export function OcrRadar({ rows }: { rows: SubmissionListRow[] }) {
  const data = ocrConfidenceByType(rows);
  if (data.length === 0) return <div className="empty">No data yet.</div>;
  return (
    <ResponsiveContainer width="100%" height={195}>
      <RadarChart data={data} outerRadius="70%">
        <PolarGrid stroke={C.grid} />
        <PolarAngleAxis dataKey="type" tick={{ fill: C.tick, fontSize: 10 }} />
        <PolarRadiusAxis tick={{ fill: C.tick, fontSize: 9 }} domain={[0, 100]} axisLine={false} />
        <Radar name="OCR confidence" dataKey="OCR confidence" stroke={C.cyan} fill={C.cyan} fillOpacity={0.25} strokeWidth={2} />
        <Radar name="Classification" dataKey="Classification" stroke={C.violet} fill={C.violet} fillOpacity={0.15} strokeWidth={2} />
        <Tooltip content={<ChartTooltip />} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

export function CompletionGauge({ pct, label }: { pct: number; label: string }) {
  const value = Math.max(0, Math.min(100, Math.round(pct * 100)));
  const fill = pct >= 0.75 ? C.emerald : pct >= 0.5 ? C.amber : C.rose;
  // A single-slice Pie fills the WHOLE arc no matter its value, so the filled
  // slice must be paired with a transparent "rest" slice: recharts then
  // proportions them across the arc and the gauge reflects the real value.
  const data = [
    { name: label, value, fill },
    { name: 'rest', value: 100 - value, fill: 'transparent' },
  ];
  return (
    <div style={{ position: 'relative', height: 195 }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={[{ name: 'track', value: 100 }]} dataKey="value" startAngle={210} endAngle={-30} innerRadius="66%" outerRadius="88%" cornerRadius={8} stroke="none" fill="rgba(255,255,255,0.06)" />
          <Pie data={data} dataKey="value" startAngle={210} endAngle={-30} innerRadius="66%" outerRadius="88%" cornerRadius={8} stroke="none">
            {data.map((d, i) => <Cell key={i} fill={d.fill} />)}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', pointerEvents: 'none' }}>
        <div style={{ textAlign: 'center' }}>
          <div className="kpi-value" style={{ fontSize: 24 }}>{value}%</div>
          <div className="muted" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1 }}>{label}</div>
        </div>
      </div>
    </div>
  );
}
