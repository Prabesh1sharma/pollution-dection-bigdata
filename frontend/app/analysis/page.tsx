"use client";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Analysis, BUCKETS, BUCKET_COLORS, CITIES, CITY_COLORS, Prediction } from "@/lib/aqi";
import { fmtDateTime, fmtHour, fmtTick, num } from "@/lib/format";
import { downloadCsv } from "@/lib/series";
import { usePoll } from "@/lib/usePoll";
import { Badge, Card, Kpi, LegendRow, Select, Status, axisProps, tooltipStyle } from "@/components/ui";

const METRIC_LABELS: Record<string, string> = {
  rmse: "RMSE (AQI points)", mae: "MAE (AQI points)", r2: "R²",
  accuracy: "Accuracy", weightedPrecision: "Weighted precision", weightedRecall: "Weighted recall", f1: "F1 (weighted)",
};

export default function AnalysisPage() {
  const [days, setDays] = useState(7);
  const [city, setCity] = useState<string>("Kathmandu");
  const a = usePoll<Analysis>(`/api/analysis?days=${days}`, 60000);
  const saved = usePoll<Prediction[]>("/api/predictions?hours=2160&limit=30", 60000);
  const d = a.data;

  const bucketRows = (d?.cities ?? []).map((c) => ({ city: c.city, ...c.bucket_counts }));
  const timeline = (d?.timeline ?? []).filter((t) => t.city === city);
  const hours = Array.from({ length: 24 }, (_, h) => {
    const row: Record<string, number | null> = { hour: h };
    for (const p of d?.hourly_pattern ?? []) if (p.hour === h) row[p.city] = p.avg_predicted_aqi;
    return row;
  });
  const fi = (d?.feature_importance ?? []).filter((f) => f.model === "aqi_classifier")
    .sort((x, y) => y.importance - x.importance).map((f) => ({ feature: f.feature, importance: +(f.importance * 100).toFixed(1) }));
  const cm = d?.confusion_matrix ?? [];
  const cmMax = Math.max(1, ...cm.map((c) => c.cnt));
  const cmGet = (act: string, pred: string) => cm.find((c) => c.actual === act && c.predicted === pred)?.cnt ?? 0;
  const reg = d?.model.metrics["aqi_regressor"] ?? {};
  const cls = d?.model.metrics["aqi_classifier"] ?? {};
  const ds = d?.model.metrics["dataset"] ?? {};

  async function exportCsv() {
    const r = await fetch("/api/predictions?hours=2160&limit=5000");
    downloadCsv("predictions.csv", await r.json());
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Prediction analysis</h1>
          <p className="muted small">
            How the saved predictions behave, and how they compare with the AQI formula computed from the same pollutants.
          </p>
        </div>
        <div className="controls">
          <Select label="Window" value={days} onChange={setDays} options={[1, 3, 7, 14, 30].map((v) => ({ value: v, label: `Last ${v} day${v > 1 ? "s" : ""}` }))} />
        </div>
      </div>

      <Status error={a.error} loading={a.loading && !d} empty={!!d && d.overall.predictions === 0} />

      {d && d.overall.predictions > 0 && (
        <>
          <div className="grid cols-4">
            <Kpi label="Predictions saved" value={d.overall.predictions.toLocaleString()} hint={`last ${d.window_days} d, all cities`} />
            <Kpi label="Alerts raised" value={d.overall.alerts.toLocaleString()} hint="Poor or worse" />
            <Kpi label="Category match vs formula" value={d.overall.bucket_accuracy == null ? "-" : `${d.overall.bucket_accuracy}%`} hint="predicted level = CPCB level" />
            <Kpi label="Mean abs. error vs formula" value={d.overall.vs_reference ? `${d.overall.vs_reference.mae}` : "-"} hint={d.overall.vs_reference ? `AQI points · r = ${d.overall.vs_reference.correlation ?? "-"}` : ""} />
          </div>

          <div className="grid cols-2">
            <Card title="Warning levels by city" sub="Number of saved predictions per category">
              <LegendRow items={BUCKETS.map((b, i) => ({ label: b, color: BUCKET_COLORS[i] }))} />
              <div className="chart-h">
                <ResponsiveContainer>
                  <BarChart data={bucketRows} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
                    <CartesianGrid stroke="var(--line)" vertical={false} />
                    <XAxis dataKey="city" {...axisProps} />
                    <YAxis {...axisProps} width={44} />
                    <Tooltip cursor={{ fill: "var(--line)", opacity: 0.4 }} {...tooltipStyle} />
                    {BUCKETS.map((b, i) => (
                      <Bar key={b} dataKey={b} stackId="a" fill={BUCKET_COLORS[i]} stroke="var(--surface)" strokeWidth={2} isAnimationActive={false} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card title="Typical day" sub="Average predicted AQI by hour of day (Nepal time)">
              <LegendRow items={CITIES.map((c) => ({ label: c, color: CITY_COLORS[c] }))} />
              <div className="chart-h">
                <ResponsiveContainer>
                  <LineChart data={hours} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
                    <CartesianGrid stroke="var(--line)" vertical={false} />
                    <XAxis dataKey="hour" tickFormatter={(h) => `${h}h`} {...axisProps} />
                    <YAxis {...axisProps} width={44} />
                    <Tooltip labelFormatter={(h) => `${h}:00`} {...tooltipStyle} />
                    {CITIES.map((c) => (
                      <Line key={c} type="monotone" dataKey={c} stroke={CITY_COLORS[c]} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <Card
            title="Predicted vs. formula AQI"
            sub="Reference = CPCB AQI computed from the same pollutant values"
            right={<Select label="City" value={city} onChange={setCity} options={CITIES.map((c) => ({ value: c, label: c }))} />}
          >
            <LegendRow items={[{ label: "Model prediction", color: "var(--s1)" }, { label: "Formula (CPCB)", color: "var(--s2)" }]} />
            <div className="chart-h">
              <ResponsiveContainer>
                <LineChart data={timeline} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
                  <CartesianGrid stroke="var(--line)" vertical={false} />
                  <XAxis dataKey="ts" tickFormatter={fmtTick} minTickGap={56} {...axisProps} />
                  <YAxis {...axisProps} width={44} />
                  <Tooltip labelFormatter={(v) => fmtHour(String(v))} {...tooltipStyle} />
                  <Line type="monotone" dataKey="predicted_aqi" name="Model prediction" stroke="var(--s1)" strokeWidth={2} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="reference_aqi" name="Formula (CPCB)" stroke="var(--s2)" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Per-city agreement with the formula">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>City</th><th className="r">Predictions</th><th className="r">Alerts</th><th className="r">Avg AQI</th><th className="r">Max AQI</th><th className="r">Avg confidence</th>
                    <th className="r">MAE</th><th className="r">RMSE</th><th className="r">Bias</th><th className="r">Correlation</th><th className="r">Same category</th><th className="r">Within ±1</th></tr>
                </thead>
                <tbody>
                  {d.cities.map((c) => (
                    <tr key={c.city}>
                      <td>{c.city}</td><td className="r">{c.predictions}</td><td className="r">{c.alerts}</td>
                      <td className="r">{num(c.avg_predicted_aqi)}</td><td className="r">{num(c.max_predicted_aqi, 0)}</td>
                      <td className="r">{c.avg_confidence == null ? "-" : `${Math.round(c.avg_confidence * 100)}%`}</td>
                      <td className="r">{c.vs_reference?.mae ?? "-"}</td><td className="r">{c.vs_reference?.rmse ?? "-"}</td>
                      <td className="r">{c.vs_reference?.bias ?? "-"}</td><td className="r">{c.vs_reference?.correlation ?? "-"}</td>
                      <td className="r">{c.bucket_accuracy == null ? "-" : `${c.bucket_accuracy}%`}</td>
                      <td className="r">{c.within_one_bucket == null ? "-" : `${c.within_one_bucket}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      <div className="grid cols-2">
        <Card title="Model quality (Kaggle test split)" sub={d?.model.trained_at ? `Trained ${fmtDateTime(d.model.trained_at)} · ${Number(ds.train_rows ?? 0).toLocaleString()} train / ${Number(ds.test_rows ?? 0).toLocaleString()} test rows, newest 20% held out` : "Run the training job to populate"}>
          {Object.keys(reg).length === 0 ? (
            <div className="notice">No metrics yet – run the Spark training job.</div>
          ) : (
            <table>
              <tbody>
                {[["Regressor (Random Forest)", reg], ["Classifier (Random Forest)", cls]].map(([title, m]) => (
                  <>
                    <tr key={String(title)}><th colSpan={2}>{String(title)}</th></tr>
                    {Object.entries(m as Record<string, number>).map(([k, v]) => (
                      <tr key={String(title) + k}><td>{METRIC_LABELS[k] ?? k}</td><td className="r">{v.toFixed(4)}</td></tr>
                    ))}
                  </>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Feature importance" sub="Classifier, % of total">
          {fi.length === 0 ? (
            <div className="notice">No data yet.</div>
          ) : (
            <div className="chart-h">
              <ResponsiveContainer>
                <BarChart data={fi} layout="vertical" margin={{ top: 4, right: 24, bottom: 0, left: 8 }}>
                  <CartesianGrid stroke="var(--line)" horizontal={false} />
                  <XAxis type="number" {...axisProps} />
                  <YAxis type="category" dataKey="feature" width={56} {...axisProps} />
                  <Tooltip cursor={{ fill: "var(--line)", opacity: 0.4 }} formatter={(v) => `${v}%`} {...tooltipStyle} />
                  <Bar dataKey="importance" fill="var(--s1)" radius={[0, 4, 4, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      {cm.length > 0 && (
        <Card title="Confusion matrix (test split)" sub="Rows: actual category · columns: predicted category · cell shade = count">
          <div className="table-wrap">
            <table className="cm">
              <thead><tr><th>Actual ↓ / Predicted →</th>{BUCKETS.map((b) => <th key={b} className="r">{b}</th>)}</tr></thead>
              <tbody>
                {BUCKETS.map((act) => (
                  <tr key={act}>
                    <th>{act}</th>
                    {BUCKETS.map((p) => {
                      const v = cmGet(act, p);
                      return (
                        <td key={p} className="cell" style={{ background: v ? `color-mix(in srgb, var(--s1) ${Math.max(8, Math.round((v / cmMax) * 70))}%, transparent)` : undefined, fontWeight: act === p ? 700 : 400 }}>
                          {v || ""}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card title="Saved predictions" sub="Latest 30 rows from Cassandra (predictions_by_city)" right={<button className="btn" onClick={exportCsv}>Download CSV</button>}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Observed (NPT)</th><th>City</th><th>Level</th><th className="r">Pred. AQI</th><th className="r">Formula AQI</th><th className="r">Confidence</th><th className="r">PM2.5</th><th className="r">PM10</th></tr></thead>
            <tbody>
              {(saved.data ?? []).map((p) => (
                <tr key={p.city + p.ts}>
                  <td>{fmtDateTime(p.ts)}</td><td>{p.city}</td><td><Badge level={p.warning_level} label={p.predicted_bucket} /></td>
                  <td className="r">{Math.round(p.predicted_aqi)}</td><td className="r">{p.reference_aqi ?? "-"}</td>
                  <td className="r">{Math.round(p.confidence * 100)}%</td><td className="r">{num(p.pm2_5)}</td><td className="r">{num(p.pm10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
