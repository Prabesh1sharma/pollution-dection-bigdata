const TZ = "Asia/Kathmandu";

export const fmtDateTime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("en-GB", { timeZone: TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }) : "-";

export const fmtHour = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { timeZone: TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });

export const fmtTick = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { timeZone: TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).replace(",", "");

export const num = (v: number | null | undefined, d = 1) => (v == null ? "-" : v.toFixed(d));

export const age = (min?: number) => {
  if (min == null) return "";
  if (min < 60) return `${min} min ago`;
  if (min < 48 * 60) return `${Math.round(min / 60)} h ago`;
  return `${Math.round(min / 1440)} d ago`;
};
