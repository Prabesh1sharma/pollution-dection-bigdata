/** Turn [{ts, city, v}] rows into [{ts, Kathmandu: v, Pokhara: v, ...}] sorted by time (for multi-line charts). */
export function pivot<T extends { ts: string; city: string }>(rows: T[], field: keyof T) {
  const byTs = new Map<string, Record<string, string | number | null>>();
  for (const r of rows) {
    const row = byTs.get(r.ts) ?? { ts: r.ts };
    row[r.city] = (r[field] as unknown as number | null) ?? null;
    byTs.set(r.ts, row);
  }
  return [...byTs.values()].sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
}

export function downloadCsv(name: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const cols = Object.keys(rows[0]);
  const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
