"use client";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Alert, BUCKET_COLORS, CITIES, CITY_COLORS, LiveItem, Prediction } from "@/lib/aqi";
import { age, fmtDateTime, fmtHour, fmtTick, num } from "@/lib/format";
import { pivot } from "@/lib/series";
import { usePoll } from "@/lib/usePoll";
import { Badge, Card, LegendRow, Status, axisProps, tooltipStyle } from "@/components/ui";

function CityCard({ d }: { d: LiveItem }) {
  if (d.status !== "ok") {
    return (
      <Card>
        <div className="city-name">
          <i className="swatch" style={{ background: CITY_COLORS[d.city] }} />
          {d.city}
        </div>
        <p className="muted">Waiting for the first prediction…</p>
      </Card>
    );
  }
  const lvl = d.warning_level ?? 0;
  return (
    <Card>
      <div className="city-top">
        <div className="city-name">
          <i className="swatch" style={{ background: CITY_COLORS[d.city] }} />
          {d.city}
        </div>
        <Badge level={lvl} label={d.predicted_bucket} />
      </div>
      <div className="aqi-row">
        <div className="aqi-num" style={{ borderBottom: `4px solid ${BUCKET_COLORS[lvl]}`, paddingBottom: 4 }}>
          {Math.round(d.predicted_aqi ?? 0)}
        </div>
        <div className="muted small">predicted AQI (CPCB scale)</div>
      </div>
      <p className="warn">{d.warning_message}</p>
      <div className="pollutants">
        <div><b>{num(d.pm2_5)}</b>PM2.5 µg/m³</div>
        <div><b>{num(d.pm10)}</b>PM10 µg/m³</div>
        <div><b>{num(d.no2)}</b>NO₂ µg/m³</div>
        <div><b>{num(d.so2)}</b>SO₂ µg/m³</div>
        <div><b>{num(d.o3)}</b>O₃ µg/m³</div>
        <div><b>{num(d.co, 2)}</b>CO mg/m³</div>
      </div>
      <div className="meta">
        <span>Confidence {Math.round((d.confidence ?? 0) * 100)}%</span>
        <span>Formula AQI {d.reference_aqi ?? "-"}</span>
        <span>Observed {fmtDateTime(d.ts)} · {age(d.age_minutes)}</span>
      </div>
    </Card>
  );
}

export default function LivePage() {
  const live = usePoll<LiveItem[]>("/api/live", 30000);
  const preds = usePoll<Prediction[]>("/api/predictions?hours=48&limit=200", 60000);
  const alerts = usePoll<Alert[]>("/api/alerts?limit=12", 60000);

  const worst = (live.data ?? []).filter((d) => d.status === "ok" && (d.warning_level ?? 0) >= 3);
  const chart = pivot(preds.data ?? [], "predicted_aqi");

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Live air-quality warnings</h1>
          <p className="muted small">
            Kafka → Spark Structured Streaming (MLlib) → Cassandra. Refreshes every 30 s
            {live.updated ? ` · updated ${live.updated.toLocaleTimeString("en-GB")}` : ""}.
          </p>
        </div>
      </div>

      <Status error={live.error} loading={live.loading && !live.data} />

      {worst.length > 0 && (
        <div className="banner" role="alert">
          <b>Warning:</b>{" "}
          {worst.map((d) => `${d.city} – ${d.predicted_bucket} (AQI ${Math.round(d.predicted_aqi ?? 0)})`).join(" · ")}. Limit outdoor exposure.
        </div>
      )}

      <div className="grid cols-3">
        {(live.data ?? CITIES.map((c) => ({ city: c, status: "no_data" as const }))).map((d) => (
          <CityCard key={d.city} d={d} />
        ))}
      </div>

      <Card title="Predicted AQI – last 48 hours" sub="Dashed lines mark the Poor (200) and Very Poor (300) thresholds">
        <LegendRow items={CITIES.map((c) => ({ label: c, color: CITY_COLORS[c] }))} />
        {chart.length === 0 ? (
          <Status error={preds.error} loading={false} empty />
        ) : (
          <div className="chart-h">
            <ResponsiveContainer>
              <LineChart data={chart} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="ts" tickFormatter={fmtTick} minTickGap={48} {...axisProps} />
                <YAxis {...axisProps} width={44} />
                <Tooltip labelFormatter={(v) => fmtHour(String(v))} {...tooltipStyle} />
                <ReferenceLine y={200} stroke="var(--muted)" strokeDasharray="4 4" />
                <ReferenceLine y={300} stroke="var(--muted)" strokeDasharray="4 4" />
                {CITIES.map((c) => (
                  <Line key={c} type="monotone" dataKey={c} stroke={CITY_COLORS[c]} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card title="Recent alerts" sub="Predictions at Poor or worse">
        {(alerts.data ?? []).length === 0 ? (
          <div className="notice">No alerts recorded – air quality has stayed Moderate or better.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Time (NPT)</th><th>City</th><th>Level</th><th className="r">AQI</th><th className="r">PM2.5</th><th>Advice</th></tr>
              </thead>
              <tbody>
                {alerts.data!.map((a) => (
                  <tr key={a.city + a.ts}>
                    <td>{fmtDateTime(a.ts)}</td>
                    <td>{a.city}</td>
                    <td><Badge level={a.warning_level} label={a.predicted_bucket} /></td>
                    <td className="r">{Math.round(a.predicted_aqi)}</td>
                    <td className="r">{num(a.pm2_5)}</td>
                    <td style={{ whiteSpace: "normal", minWidth: 260 }}>{a.warning_message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
