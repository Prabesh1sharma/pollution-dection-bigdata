"use client";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CITIES, DailyPoint, HourlyPoint } from "@/lib/aqi";
import { fmtHour, fmtTick, num } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";
import { Card, LegendRow, Select, Status, axisProps, tooltipStyle } from "@/components/ui";

function Lines({ data, series }: { data: object[]; series: { key: string; label: string; color: string }[] }) {
  return (
    <>
      <LegendRow items={series.map((s) => ({ label: s.label, color: s.color }))} />
      <div className="chart-h">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="ts" tickFormatter={fmtTick} minTickGap={56} {...axisProps} />
            <YAxis {...axisProps} width={44} />
            <Tooltip labelFormatter={(v) => fmtHour(String(v))} {...tooltipStyle} />
            {series.map((s) => (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

export default function HistoryPage() {
  const [city, setCity] = useState<string>("Kathmandu");
  const [days, setDays] = useState(7);
  const hourly = usePoll<HourlyPoint[]>(`/api/history?city=${city}&days=${days}`, 120000);
  const daily = usePoll<DailyPoint[]>(`/api/history?city=${city}&days=${days}&resolution=daily`, 120000);
  const rows = hourly.data ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Historical analysis</h1>
          <p className="muted small">Hourly observations ingested from the public API and stored in Cassandra.</p>
        </div>
        <div className="controls">
          <Select label="City" value={city} onChange={setCity} options={CITIES.map((c) => ({ value: c, label: c }))} />
          <Select label="Range" value={days} onChange={setDays} options={[1, 3, 7, 14, 30].map((d) => ({ value: d, label: `Last ${d} day${d > 1 ? "s" : ""}` }))} />
        </div>
      </div>

      <Status error={hourly.error} loading={hourly.loading && !hourly.data} empty={!hourly.loading && rows.length === 0} />

      {rows.length > 0 && (
        <>
          <div className="grid cols-2">
            <Card title="Particulate matter" sub="µg/m³">
              <Lines data={rows} series={[
                { key: "pm2_5", label: "PM2.5", color: "var(--s1)" },
                { key: "pm10", label: "PM10", color: "var(--s2)" },
              ]} />
            </Card>
            <Card title="Gases" sub="µg/m³">
              <Lines data={rows} series={[
                { key: "no2", label: "NO₂", color: "var(--s1)" },
                { key: "so2", label: "SO₂", color: "var(--s2)" },
                { key: "o3", label: "O₃", color: "var(--s3)" },
              ]} />
            </Card>
          </div>
          <Card title="AQI over time" sub="CPCB AQI computed from the pollutants vs. the API provider's US AQI (different scale – shown for context)">
            <Lines data={rows} series={[
              { key: "reference_aqi", label: "CPCB AQI (computed)", color: "var(--s1)" },
              { key: "ref_us_aqi", label: "US AQI (provider)", color: "var(--s2)" },
            ]} />
          </Card>
        </>
      )}

      <Card title="Daily summary" sub="Days are Nepal local time (UTC+5:45)">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th><th className="r">Hours</th><th className="r">Avg PM2.5</th><th className="r">Max PM2.5</th>
                <th className="r">Avg PM10</th><th className="r">Avg NO₂</th><th className="r">Avg O₃</th><th className="r">Avg CO (mg/m³)</th>
                <th className="r">Avg AQI</th><th className="r">Max AQI</th>
              </tr>
            </thead>
            <tbody>
              {[...(daily.data ?? [])].reverse().map((d) => (
                <tr key={d.date}>
                  <td>{d.date}</td><td className="r">{d.hours}</td><td className="r">{num(d.avg_pm2_5)}</td><td className="r">{num(d.max_pm2_5)}</td>
                  <td className="r">{num(d.avg_pm10)}</td><td className="r">{num(d.avg_no2)}</td><td className="r">{num(d.avg_o3)}</td>
                  <td className="r">{num(d.avg_co, 2)}</td><td className="r">{num(d.avg_aqi, 0)}</td><td className="r">{d.max_aqi ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
