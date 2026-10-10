"""Endpoint tests with Cassandra replaced by an in-memory fake.

Run:  cd backend && pip install fastapi httpx pytest && python -m pytest -q
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import db
from app.aqi import bucket_index, cpcb_aqi
from app.main import app

NOW = datetime.now(timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)


def _reading(city, i, pm25):
    return {"city": city, "ts": NOW - timedelta(hours=i), "latitude": 0.0, "longitude": 0.0,
            "pm2_5": pm25, "pm10": pm25 * 1.6, "co": 900.0, "no2": 30.0, "so2": 10.0, "o3": 25.0,
            "ref_us_aqi": 100, "ref_eu_aqi": 60, "ingested_at": NOW}


def _prediction(city, i, pm25, level, aqi):
    r = _reading(city, i, pm25)
    r["co"] = 0.9  # predictions store CO in mg/m3
    return {**{k: r[k] for k in ("city", "ts", "pm2_5", "pm10", "co", "no2", "so2", "o3", "ref_us_aqi", "ref_eu_aqi")},
            "predicted_aqi": aqi, "predicted_bucket": ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"][level],
            "warning_level": level, "warning_message": "msg", "confidence": 0.9, "predicted_at": NOW}


READINGS = [_reading(c, i, 40 + 5 * i) for c in ("Kathmandu", "Pokhara") for i in range(30)]
PREDS = [_prediction(c, i, 40 + 5 * i, 2 if i < 10 else 3, 100 + 8 * i) for c in ("Kathmandu", "Pokhara") for i in range(30)]
ALERTS = [{"city": "Kathmandu", "ts": NOW, "predicted_aqi": 250.0, "predicted_bucket": "Poor", "warning_level": 3,
           "warning_message": "msg", "confidence": 0.8, "pm2_5": 120.0, "pm10": 200.0}]


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    def fake_query(cql, params=()):
        if "system.local" in cql:
            return [{"release_version": "4.1"}]
        table = cql.split("FROM ")[1].split()[0]
        data = {"predictions_by_city": PREDS, "readings_by_city": READINGS, "alerts_by_city": ALERTS,
                "model_metrics": [{"model": "aqi_classifier", "metric": "accuracy", "value": 0.97, "trained_at": NOW}],
                "feature_importance": [{"model": "aqi_classifier", "feature": "pm2_5", "importance": 0.5}],
                "confusion_matrix": [{"actual": "Good", "predicted": "Good", "cnt": 5}]}[table]
        city = params[0] if params and isinstance(params[0], str) else None
        rows = [r for r in data if city is None or r.get("city") == city]
        rows = sorted(rows, key=lambda r: r.get("ts", NOW), reverse=True)
        if "LIMIT %s" in cql:
            rows = rows[: params[-1]]
        elif "LIMIT 1" in cql:
            rows = rows[:1]
        return rows
    monkeypatch.setattr(db, "query", fake_query)


client = TestClient(app)


def test_cpcb_reference():
    assert cpcb_aqi(pm2_5=30, pm10=50, no2=40) == 50
    assert cpcb_aqi(pm2_5=60, pm10=100, no2=10) == 100
    assert cpcb_aqi(pm2_5=500, pm10=10, no2=10) == 500
    assert cpcb_aqi(pm2_5=10, no2=10) is None  # < 3 pollutants
    assert cpcb_aqi(no2=10, so2=10, o3=10) is None  # no PM
    assert [bucket_index(x) for x in (50, 51, 200, 201, 400, 401)] == [0, 1, 2, 3, 4, 5]


def test_health_and_cities():
    assert client.get("/api/health").json()["cassandra"] is True
    assert {c["city"] for c in client.get("/api/cities").json()} == {"Kathmandu", "Pokhara", "Biratnagar"}


def test_live_handles_missing_city():
    data = {d["city"]: d for d in client.get("/api/live").json()}
    assert data["Kathmandu"]["status"] == "ok" and data["Kathmandu"]["reference_aqi"] is not None
    assert data["Biratnagar"]["status"] == "no_data"


def test_predictions_alerts_history():
    p = client.get("/api/predictions", params={"city": "Pokhara", "hours": 100, "limit": 10}).json()
    assert len(p) == 10 and p[0]["ts"] >= p[-1]["ts"] and p[0]["city"] == "Pokhara"
    assert client.get("/api/predictions", params={"city": "Nowhere"}).status_code == 404
    assert client.get("/api/alerts").json()[0]["predicted_bucket"] == "Poor"
    h = client.get("/api/history", params={"city": "Kathmandu", "days": 3}).json()
    assert h[0]["ts"] <= h[-1]["ts"] and h[0]["co"] == pytest.approx(0.9)
    d = client.get("/api/history", params={"city": "Kathmandu", "days": 3, "resolution": "daily"}).json()
    assert d and {"date", "avg_pm2_5", "max_aqi"} <= d[0].keys()


def test_analysis():
    a = client.get("/api/analysis", params={"days": 3}).json()
    km = next(c for c in a["cities"] if c["city"] == "Kathmandu")
    assert km["predictions"] == 30 and km["alerts"] == 20
    assert sum(km["bucket_counts"].values()) == 30
    assert km["vs_reference"]["n"] == 30
    assert a["model"]["metrics"]["aqi_classifier"]["accuracy"] == 0.97
    assert a["confusion_matrix"] and a["feature_importance"] and a["timeline"] and a["hourly_pattern"]
