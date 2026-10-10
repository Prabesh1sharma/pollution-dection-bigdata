"""FastAPI backend for the air-quality dashboards. Reads everything from Cassandra."""
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .aqi import BUCKETS, bucket_index, cpcb_aqi
from .stats import agreement_metrics, mean

CITIES = {
    "Kathmandu": {"latitude": 27.7172, "longitude": 85.3240},
    "Pokhara": {"latitude": 28.2096, "longitude": 83.9856},
    "Biratnagar": {"latitude": 26.4525, "longitude": 87.2718},
}
NEPAL_OFFSET = timedelta(hours=5, minutes=45)

app = FastAPI(title="Nepal Air Quality – Big Data API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------- helpers
def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)  # Cassandra datetimes are naive UTC


def _cities(city: str | None) -> list[str]:
    if city is None:
        return list(CITIES)
    if city not in CITIES:
        raise HTTPException(404, f"Unknown city '{city}'. Choose from {list(CITIES)}")
    return [city]


def _safe_query(cql, params=()):
    try:
        return db.query(cql, params)
    except HTTPException:
        raise
    except Exception as exc:
        db.reset_session()
        raise HTTPException(503, f"Database unavailable: {type(exc).__name__}") from exc


def _reference(row: dict):
    return cpcb_aqi(row.get("pm2_5"), row.get("pm10"), row.get("no2"), row.get("so2"), row.get("co"), row.get("o3"))


def _prediction_out(row: dict) -> dict:
    out = {k: v for k, v in row.items() if k not in ("ts", "predicted_at")}
    out["ts"] = db.iso(row["ts"])
    out["predicted_at"] = db.iso(row.get("predicted_at"))
    out["reference_aqi"] = _reference(row)
    return out


def _predictions(city: str, since: datetime, limit: int) -> list[dict]:
    return _safe_query(
        "SELECT * FROM predictions_by_city WHERE city=%s AND ts>=%s LIMIT %s", (city, since, limit)
    )


# --------------------------------------------------------------- endpoints
@app.get("/api/health")
def health():
    try:
        db.query("SELECT release_version FROM system.local")
        return {"status": "ok", "cassandra": True}
    except Exception as exc:
        db.reset_session()
        return {"status": "degraded", "cassandra": False, "error": type(exc).__name__}


@app.get("/api/cities")
def cities():
    return [{"city": c, **v} for c, v in CITIES.items()]


@app.get("/api/live")
def live():
    """Latest saved prediction per city."""
    out = []
    for city in CITIES:
        rows = _safe_query("SELECT * FROM predictions_by_city WHERE city=%s LIMIT 1", (city,))
        if not rows:
            out.append({"city": city, "status": "no_data", **CITIES[city]})
            continue
        item = _prediction_out(rows[0])
        item.update({"status": "ok", **CITIES[city]})
        item["age_minutes"] = round((_now() - rows[0]["ts"]).total_seconds() / 60)
        out.append(item)
    return out


@app.get("/api/predictions")
def predictions(
    city: str | None = None,
    hours: int = Query(72, ge=1, le=24 * 90),
    limit: int = Query(500, ge=1, le=5000),
):
    """Saved predictions, newest first."""
    since = _now() - timedelta(hours=hours)
    rows = []
    for c in _cities(city):
        rows += [_prediction_out(r) | {"city": c} for r in _predictions(c, since, limit)]
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return rows[:limit]


@app.get("/api/alerts")
def alerts(city: str | None = None, limit: int = Query(50, ge=1, le=500)):
    rows = []
    for c in _cities(city):
        for r in _safe_query("SELECT * FROM alerts_by_city WHERE city=%s LIMIT %s", (c, limit)):
            rows.append({**r, "ts": db.iso(r["ts"])})
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return rows[:limit]


@app.get("/api/history")
def history(
    city: str,
    days: int = Query(7, ge=1, le=90),
    resolution: str = Query("hourly", pattern="^(hourly|daily)$"),
):
    """Historical observations (as ingested from the public API) with the CPCB reference AQI."""
    _cities(city)
    since = _now() - timedelta(days=days)
    rows = _safe_query(
        "SELECT * FROM readings_by_city WHERE city=%s AND ts>=%s LIMIT 5000", (city, since)
    )
    rows.sort(key=lambda r: r["ts"])
    hourly = []
    for r in rows:
        co_mg = None if r["co"] is None else r["co"] / 1000.0
        hourly.append({
            "ts": db.iso(r["ts"]), "_dt": r["ts"],
            "pm2_5": r["pm2_5"], "pm10": r["pm10"], "no2": r["no2"], "so2": r["so2"], "o3": r["o3"],
            "co": co_mg,  # mg/m3
            "ref_us_aqi": r["ref_us_aqi"],
            "reference_aqi": cpcb_aqi(r["pm2_5"], r["pm10"], r["no2"], r["so2"], co_mg, r["o3"]),
        })
    if resolution == "hourly":
        return [{k: v for k, v in h.items() if k != "_dt"} for h in hourly]

    by_day = defaultdict(list)
    for h in hourly:
        by_day[(h["_dt"] + NEPAL_OFFSET).date().isoformat()].append(h)
    daily = []
    for day, items in sorted(by_day.items()):
        aqis = [i["reference_aqi"] for i in items if i["reference_aqi"] is not None]
        daily.append({
            "date": day, "hours": len(items),
            **{f"avg_{k}": _r(mean(i[k] for i in items)) for k in ("pm2_5", "pm10", "no2", "so2", "o3", "co")},
            "max_pm2_5": max((i["pm2_5"] for i in items if i["pm2_5"] is not None), default=None),
            "avg_aqi": _r(mean(aqis), 0), "max_aqi": max(aqis, default=None),
        })
    return daily


def _r(x, n=1):
    return None if x is None else round(x, n)


@app.get("/api/analysis")
def analysis(days: int = Query(7, ge=1, le=90), timeline_points: int = Query(200, ge=10, le=2000)):
    """Everything the prediction-analysis dashboard needs."""
    since = _now() - timedelta(days=days)
    per_city, timeline, by_hour = [], [], defaultdict(lambda: defaultdict(list))
    all_pred, all_ref, all_pl, all_rl = [], [], [], []

    for city in CITIES:
        rows = _predictions(city, since, 5000)
        rows.sort(key=lambda r: r["ts"])
        refs = [_reference(r) for r in rows]
        preds = [r["predicted_aqi"] for r in rows]
        levels = [r["warning_level"] for r in rows]
        ref_levels = [None if x is None else bucket_index(x) for x in refs]
        pairs = [(a, b) for a, b in zip(levels, ref_levels) if a is not None and b is not None]
        counts = Counter(r["predicted_bucket"] for r in rows)
        per_city.append({
            "city": city,
            "predictions": len(rows),
            "alerts": sum(1 for lv in levels if lv is not None and lv >= 3),
            "avg_predicted_aqi": _r(mean(preds)),
            "max_predicted_aqi": max((p for p in preds if p is not None), default=None),
            "avg_confidence": _r(mean(r["confidence"] for r in rows), 3),
            "bucket_counts": {b: counts.get(b, 0) for b in BUCKETS},
            "vs_reference": agreement_metrics(preds, refs),
            "bucket_accuracy": _r(100 * sum(a == b for a, b in pairs) / len(pairs)) if pairs else None,
            "within_one_bucket": _r(100 * sum(abs(a - b) <= 1 for a, b in pairs) / len(pairs)) if pairs else None,
        })
        all_pred += preds; all_ref += refs; all_pl += [a for a, _ in zip(levels, ref_levels)]; all_rl += ref_levels
        for r, ref in list(zip(rows, refs))[-timeline_points:]:
            timeline.append({"ts": db.iso(r["ts"]), "city": city, "predicted_aqi": r["predicted_aqi"], "reference_aqi": ref})
        for r in rows:
            local_hour = (r["ts"] + NEPAL_OFFSET).hour
            if r["predicted_aqi"] is not None:
                by_hour[city][local_hour].append(r["predicted_aqi"])

    pairs = [(a, b) for a, b in zip(all_pl, all_rl) if a is not None and b is not None]
    overall = {
        "predictions": sum(c["predictions"] for c in per_city),
        "alerts": sum(c["alerts"] for c in per_city),
        "vs_reference": agreement_metrics(all_pred, all_ref),
        "bucket_accuracy": _r(100 * sum(a == b for a, b in pairs) / len(pairs)) if pairs else None,
    }

    metrics: dict = {}
    trained_at = None
    for r in _safe_query("SELECT * FROM model_metrics"):
        metrics.setdefault(r["model"], {})[r["metric"]] = r["value"]
        trained_at = max(filter(None, [trained_at, r["trained_at"]]), default=None)
    importance = [r for r in _safe_query("SELECT * FROM feature_importance")]
    confusion = [r for r in _safe_query("SELECT * FROM confusion_matrix")]

    return {
        "window_days": days,
        "overall": overall,
        "cities": per_city,
        "timeline": sorted(timeline, key=lambda t: t["ts"]),
        "hourly_pattern": [
            {"city": c, "hour": h, "avg_predicted_aqi": _r(mean(v))}
            for c, hours in by_hour.items() for h, v in sorted(hours.items())
        ],
        "model": {"trained_at": db.iso(trained_at), "metrics": metrics},
        "confusion_matrix": confusion,
        "feature_importance": importance,
        "buckets": BUCKETS,
    }
