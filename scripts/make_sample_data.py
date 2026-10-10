"""Generate a synthetic station_hour.csv with the same schema as the Kaggle file.

ONLY for smoke-testing the pipeline offline. The real project should use the Kaggle
dataset (rohanrao/air-quality-data-in-india). Usage:
    python scripts/make_sample_data.py out.csv [rows_per_station] [stations]
"""
import csv
import math
import random
import sys
from datetime import datetime, timedelta

# CPCB breakpoints: (conc_lo, conc_hi, aqi_lo, aqi_hi)
BP = {
    "PM2.5": [(0, 30, 0, 50), (30, 60, 50, 100), (60, 90, 100, 200), (90, 120, 200, 300), (120, 250, 300, 400), (250, 500, 400, 500)],
    "PM10": [(0, 50, 0, 50), (50, 100, 50, 100), (100, 250, 100, 200), (250, 350, 200, 300), (350, 430, 300, 400), (430, 800, 400, 500)],
    "NO2": [(0, 40, 0, 50), (40, 80, 50, 100), (80, 180, 100, 200), (180, 280, 200, 300), (280, 400, 300, 400), (400, 800, 400, 500)],
    "SO2": [(0, 40, 0, 50), (40, 80, 50, 100), (80, 380, 100, 200), (380, 800, 200, 300), (800, 1600, 300, 400), (1600, 3000, 400, 500)],
    "CO": [(0, 1, 0, 50), (1, 2, 50, 100), (2, 10, 100, 200), (10, 17, 200, 300), (17, 34, 300, 400), (34, 60, 400, 500)],
    "O3": [(0, 50, 0, 50), (50, 100, 50, 100), (100, 168, 100, 200), (168, 208, 200, 300), (208, 748, 300, 400), (748, 1000, 400, 500)],
}


def sub_index(pol, x):
    for lo, hi, ilo, ihi in BP[pol]:
        if x <= hi:
            return ilo + (x - lo) * (ihi - ilo) / (hi - lo)
    return 500


def bucket(aqi):
    return ("Good" if aqi <= 50 else "Satisfactory" if aqi <= 100 else "Moderate" if aqi <= 200
            else "Poor" if aqi <= 300 else "Very Poor" if aqi <= 400 else "Severe")


def main():
    out = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    stations = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    random.seed(1)
    start = datetime(2018, 1, 1)
    cols = ["StationId", "Datetime", "PM2.5", "PM10", "NO", "NO2", "NOx", "NH3", "CO", "SO2", "O3",
            "Benzene", "Toluene", "Xylene", "AQI", "AQI_Bucket"]
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for s in range(stations):
            base = random.uniform(30, 120)
            for i in range(n):
                t = start + timedelta(hours=i)
                season = 1 + 0.6 * math.cos((t.timetuple().tm_yday - 15) / 365 * 2 * math.pi)
                daily = 1 + 0.3 * math.sin((t.hour - 8) / 24 * 2 * math.pi)
                pm25 = max(2, random.gauss(base * season * daily, 20))
                v = {"PM2.5": pm25, "PM10": pm25 * random.uniform(1.4, 2.2), "NO2": max(1, random.gauss(35 * daily, 12)),
                     "SO2": max(1, random.gauss(15, 6)), "CO": max(0.1, random.gauss(1.0 * daily, 0.5)),
                     "O3": max(1, random.gauss(40, 18))}
                row = {k: round(x, 2) for k, x in v.items()}
                for k in ("PM2.5", "NO2", "SO2", "CO", "O3", "PM10"):  # sprinkle missing values
                    if random.random() < 0.06:
                        row[k] = ""
                present = {k: float(x) for k, x in row.items() if x != ""}
                if ("PM2.5" in present or "PM10" in present) and len(present) >= 3:
                    aqi = round(max(sub_index(k, x) for k, x in present.items()))
                    bk = bucket(aqi)
                else:
                    aqi, bk = "", ""
                w.writerow([f"ST{s:03d}", t.strftime("%Y-%m-%d %H:%M:%S"), row["PM2.5"], row["PM10"], "", row["NO2"], "", "",
                            row["CO"], row["SO2"], row["O3"], "", "", "", aqi, bk])
    print("wrote", out)


if __name__ == "__main__":
    main()
