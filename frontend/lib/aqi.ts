export const BUCKETS = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"] as const;

// CPCB category colours (semantic status colours - always shown together with the text label).
export const BUCKET_COLORS = ["#2e9e5b", "#8bc34a", "#e0b000", "#f57c00", "#e53935", "#a31515"];

export const CITIES = ["Kathmandu", "Pokhara", "Biratnagar"] as const;
export type City = (typeof CITIES)[number];

// Categorical slots 1-3 of the validated palette (see globals.css).
export const CITY_COLORS: Record<string, string> = {
  Kathmandu: "var(--s1)",
  Pokhara: "var(--s2)",
  Biratnagar: "var(--s3)",
};

export function bucketIndex(aqi: number | null | undefined): number {
  if (aqi == null) return -1;
  return aqi <= 50 ? 0 : aqi <= 100 ? 1 : aqi <= 200 ? 2 : aqi <= 300 ? 3 : aqi <= 400 ? 4 : 5;
}

export interface Prediction {
  city: string;
  ts: string;
  pm2_5: number | null;
  pm10: number | null;
  co: number | null; // mg/m3
  no2: number | null;
  so2: number | null;
  o3: number | null;
  predicted_aqi: number;
  predicted_bucket: string;
  warning_level: number;
  warning_message: string;
  confidence: number;
  ref_us_aqi: number | null;
  ref_eu_aqi: number | null;
  reference_aqi: number | null;
  predicted_at: string | null;
}

export interface LiveItem extends Partial<Prediction> {
  city: string;
  status: "ok" | "no_data";
  age_minutes?: number;
}

export interface Alert {
  city: string;
  ts: string;
  predicted_aqi: number;
  predicted_bucket: string;
  warning_level: number;
  warning_message: string;
  confidence: number;
  pm2_5: number | null;
  pm10: number | null;
}

export interface HourlyPoint {
  ts: string;
  pm2_5: number | null;
  pm10: number | null;
  no2: number | null;
  so2: number | null;
  o3: number | null;
  co: number | null;
  ref_us_aqi: number | null;
  reference_aqi: number | null;
}

export interface DailyPoint {
  date: string;
  hours: number;
  avg_pm2_5: number | null;
  avg_pm10: number | null;
  avg_no2: number | null;
  avg_so2: number | null;
  avg_o3: number | null;
  avg_co: number | null;
  max_pm2_5: number | null;
  avg_aqi: number | null;
  max_aqi: number | null;
}

export interface Agreement {
  n: number;
  mae: number;
  rmse: number;
  bias: number;
  correlation: number | null;
}

export interface CityAnalysis {
  city: string;
  predictions: number;
  alerts: number;
  avg_predicted_aqi: number | null;
  max_predicted_aqi: number | null;
  avg_confidence: number | null;
  bucket_counts: Record<string, number>;
  vs_reference: Agreement | null;
  bucket_accuracy: number | null;
  within_one_bucket: number | null;
}

export interface Analysis {
  window_days: number;
  overall: { predictions: number; alerts: number; vs_reference: Agreement | null; bucket_accuracy: number | null };
  cities: CityAnalysis[];
  timeline: { ts: string; city: string; predicted_aqi: number; reference_aqi: number | null }[];
  hourly_pattern: { city: string; hour: number; avg_predicted_aqi: number }[];
  model: { trained_at: string | null; metrics: Record<string, Record<string, number>> };
  confusion_matrix: { actual: string; predicted: string; cnt: number }[];
  feature_importance: { model: string; feature: string; importance: number }[];
  buckets: string[];
}
