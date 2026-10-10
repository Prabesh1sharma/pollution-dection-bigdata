"""CPCB (India NAQI) AQI computed directly from pollutant concentrations.

Used as an independent reference to evaluate the ML predictions on live data.
Units: ug/m3 for everything except CO (mg/m3).
Bands are (conc_lo, conc_hi, aqi_lo, aqi_hi); concentrations above the last band cap at 500.
"""
BANDS = {
    "pm2_5": [(0, 30, 0, 50), (30, 60, 50, 100), (60, 90, 100, 200), (90, 120, 200, 300), (120, 250, 300, 400), (250, 380, 400, 500)],
    "pm10": [(0, 50, 0, 50), (50, 100, 50, 100), (100, 250, 100, 200), (250, 350, 200, 300), (350, 430, 300, 400), (430, 510, 400, 500)],
    "no2": [(0, 40, 0, 50), (40, 80, 50, 100), (80, 180, 100, 200), (180, 280, 200, 300), (280, 400, 300, 400), (400, 520, 400, 500)],
    "so2": [(0, 40, 0, 50), (40, 80, 50, 100), (80, 380, 100, 200), (380, 800, 200, 300), (800, 1600, 300, 400), (1600, 2100, 400, 500)],
    "co": [(0, 1, 0, 50), (1, 2, 50, 100), (2, 10, 100, 200), (10, 17, 200, 300), (17, 34, 300, 400), (34, 44, 400, 500)],
    "o3": [(0, 50, 0, 50), (50, 100, 50, 100), (100, 168, 100, 200), (168, 208, 200, 300), (208, 748, 300, 400), (748, 1000, 400, 500)],
}

BUCKETS = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]


def sub_index(pollutant: str, value: float) -> float:
    for lo, hi, ilo, ihi in BANDS[pollutant]:
        if value <= hi:
            return ilo + (max(value, lo) - lo) * (ihi - ilo) / (hi - lo)
    return 500.0


def cpcb_aqi(pm2_5=None, pm10=None, no2=None, so2=None, co=None, o3=None):
    """Overall AQI = max sub-index; needs >= 3 pollutants incl. at least one PM (CPCB rule)."""
    values = {"pm2_5": pm2_5, "pm10": pm10, "no2": no2, "so2": so2, "co": co, "o3": o3}
    present = {k: v for k, v in values.items() if v is not None and v >= 0}
    if len(present) < 3 or ("pm2_5" not in present and "pm10" not in present):
        return None
    return round(max(sub_index(k, v) for k, v in present.items()))


def bucket_index(aqi: float) -> int:
    for i, limit in enumerate((50, 100, 200, 300, 400)):
        if aqi <= limit:
            return i
    return 5
