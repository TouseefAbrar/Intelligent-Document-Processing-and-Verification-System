import type { LucideIcon } from 'lucide-react';

interface Props {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  icon: LucideIcon;
  color?: string;
  glow?: string;
  trend?: string;
}

export function StatCard({ label, value, unit, sub, icon: Icon, color = '#22d3ee', glow, trend }: Props) {
  return (
    <div className="kpi" style={{ ['--kpi-color' as string]: color, ['--kpi-glow' as string]: glow ?? `${color}26` }}>
      <div className="kpi-top">
        <div className="kpi-icon"><Icon size={19} /></div>
        {trend && <span className="kpi-trend">{trend}</span>}
      </div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        {value}
        {unit && <span className="unit"> {unit}</span>}
      </div>
      {sub && <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>{sub}</div>}
    </div>
  );
}
