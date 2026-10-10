"""Ingestion service: public air-quality API -> Kafka.

Source: Open-Meteo Air Quality API (https://open-meteo.com/en/docs/air-quality-api).
It is free and needs no API key. Values are CAMS atmospheric-model estimates for
the given coordinates (hourly), not readings from a ground station.

On start-up it back-fills the last BACKFILL_DAYS of hourly data (so the
dashboards have history immediately), then polls the latest value every
POLL_INTERVAL_SECONDS and publishes only observations it has not sent yet.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone

import requests
from confluent_kafka import Producer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("producer")

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
TOPIC = os.getenv("KAFKA_TOPIC", "air-quality-raw")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
BACKFILL_DAYS = max(0, min(int(os.getenv("BACKFILL_DAYS", "7")), 92))

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
VARIABLES = "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,us_aqi,european_aqi"

CITIES = {
    "Kathmandu": (27.7172, 85.3240),
    "Pokhara": (28.2096, 83.9856),
    "Biratnagar": (26.4525, 87.2718),
}


def to_message(city: str, lat: float, lon: float, time_str: str, values: dict) -> dict:
    """Map one API observation to the flat JSON message sent to Kafka."""
    ts = datetime.strptime(time_str, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    return {
        "city": city,
        "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latitude": lat,
        "longitude": lon,
        "pm2_5": values.get("pm2_5"),
        "pm10": values.get("pm10"),
        "co": values.get("carbon_monoxide"),  # ug/m3
        "no2": values.get("nitrogen_dioxide"),  # ug/m3
        "so2": values.get("sulphur_dioxide"),  # ug/m3
        "o3": values.get("ozone"),  # ug/m3
        "us_aqi": values.get("us_aqi"),
        "eu_aqi": values.get("european_aqi"),
        "source": "open-meteo",
    }


def has_pollutants(msg: dict) -> bool:
    return any(msg[k] is not None for k in ("pm2_5", "pm10", "no2", "so2", "co", "o3"))


def fetch_hourly(city: str, lat: float, lon: float, past_days: int) -> list[dict]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": VARIABLES,
        "past_days": past_days,
        "forecast_days": 1,
        "timezone": "UTC",
    }
    r = requests.get(API_URL, params=params, timeout=30)
    r.raise_for_status()
    h = r.json()["hourly"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    out = []
    for i, t in enumerate(h["time"]):
        if t > now:  # the API also returns forecast hours; skip them
            continue
        msg = to_message(city, lat, lon, t, {k: v[i] for k, v in h.items() if k != "time"})
        if has_pollutants(msg):
            out.append(msg)
    return out


def fetch_current(city: str, lat: float, lon: float) -> dict | None:
    params = {"latitude": lat, "longitude": lon, "current": VARIABLES, "timezone": "UTC"}
    r = requests.get(API_URL, params=params, timeout=30)
    r.raise_for_status()
    cur = r.json().get("current")
    if not cur:
        return None
    msg = to_message(city, lat, lon, cur["time"], cur)
    return msg if has_pollutants(msg) else None


def main() -> None:
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "client.id": "aq-producer"})
    last_sent: dict[str, str] = {}

    def send(msg: dict) -> None:
        producer.produce(TOPIC, key=msg["city"], value=json.dumps(msg).encode())
        last_sent[msg["city"]] = max(msg["ts"], last_sent.get(msg["city"], ""))

    if BACKFILL_DAYS:
        for city, (lat, lon) in CITIES.items():
            try:
                rows = fetch_hourly(city, lat, lon, BACKFILL_DAYS)
                for m in rows:
                    send(m)
                producer.flush()
                log.info("backfill %s: %d hourly rows", city, len(rows))
            except Exception as exc:  # keep going; polling will still work
                log.warning("backfill failed for %s: %s", city, exc)

    while True:
        for city, (lat, lon) in CITIES.items():
            try:
                msg = fetch_current(city, lat, lon)
                if msg and msg["ts"] > last_sent.get(city, ""):
                    send(msg)
                    log.info("sent %s ts=%s pm2.5=%s pm10=%s", city, msg["ts"], msg["pm2_5"], msg["pm10"])
                else:
                    log.info("no new observation for %s", city)
            except Exception as exc:
                log.warning("poll failed for %s: %s", city, exc)
        producer.flush(10)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
