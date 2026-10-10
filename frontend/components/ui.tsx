"use client";
import { ReactNode } from "react";
import { BUCKET_COLORS, BUCKETS } from "@/lib/aqi";

export function Badge({ level, label }: { level: number; label?: string }) {
  const i = Math.max(0, Math.min(5, level));
  return (
    <span className="badge" style={{ background: BUCKET_COLORS[i], color: i === 2 || i === 1 ? "#1a1a19" : "#fff" }}>
      {label ?? BUCKETS[i]}
    </span>
  );
}

export function Card({ title, sub, children, right }: { title?: string; sub?: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="card">
      {(title || right) && (
        <div className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {sub && <p className="muted small">{sub}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Kpi({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <div className="muted small">{hint}</div>}
    </div>
  );
}

export function Select<T extends string | number>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string;
}) {
  return (
    <label className="select">
      <span className="muted small">{label}</span>
      <select
        value={value}
        onChange={(e) => {
          const raw = e.target.value;
          onChange((typeof value === "number" ? Number(raw) : raw) as T);
        }}
      >
        {options.map((o) => (
          <option key={String(o.value)} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  );
}

export function Status({ error, loading, empty }: { error: string | null; loading: boolean; empty?: boolean }) {
  if (error) return <div className="notice err">Could not load data: {error}. Is the API running?</div>;
  if (loading) return <div className="notice">Loading…</div>;
  if (empty) return <div className="notice">No data yet. Start the producer and the Spark streaming job, then check back in a minute.</div>;
  return null;
}

export const tooltipStyle = {
  contentStyle: { background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, color: "var(--ink)", fontSize: 12 },
  labelStyle: { color: "var(--ink2)" },
  itemStyle: { color: "var(--ink)" },
};
export const axisProps = { stroke: "var(--muted)", tick: { fill: "var(--ink2)", fontSize: 11 }, tickLine: false } as const;

export function LegendRow({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="legend">
      {items.map((i) => (
        <span key={i.label}>
          <i className="swatch" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}
