CREATE KEYSPACE IF NOT EXISTS airquality
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE airquality;

-- Raw observations exactly as received from the public air-quality API.
CREATE TABLE IF NOT EXISTS readings_by_city (
  city          text,
  ts            timestamp,   -- observation time (UTC)
  latitude      double,
  longitude     double,
  pm2_5         double,      -- ug/m3
  pm10          double,      -- ug/m3
  co            double,      -- ug/m3 (as delivered by the API)
  no2           double,      -- ug/m3
  so2           double,      -- ug/m3
  o3            double,      -- ug/m3
  ref_us_aqi    int,         -- US AQI computed by the API provider (reference only)
  ref_eu_aqi    int,         -- European AQI computed by the API provider (reference only)
  ingested_at   timestamp,
  PRIMARY KEY ((city), ts)
) WITH CLUSTERING ORDER BY (ts DESC);

-- Saved model output: one row per (city, observation time).
CREATE TABLE IF NOT EXISTS predictions_by_city (
  city              text,
  ts                timestamp,
  pm2_5             double,
  pm10              double,
  co                double,    -- mg/m3 (converted from the API's ug/m3 for the model)
  no2               double,
  so2               double,
  o3                double,
  predicted_aqi     double,   -- regression model, CPCB scale 0-500
  predicted_bucket  text,     -- classification model (Good ... Severe)
  warning_level     int,      -- 0 (Good) .. 5 (Severe)
  warning_message   text,
  confidence        double,   -- max class probability of the classifier
  ref_us_aqi        int,
  ref_eu_aqi        int,
  predicted_at      timestamp,
  PRIMARY KEY ((city), ts)
) WITH CLUSTERING ORDER BY (ts DESC);

-- Subset of predictions with warning_level >= 3 (Poor or worse).
CREATE TABLE IF NOT EXISTS alerts_by_city (
  city              text,
  ts                timestamp,
  predicted_aqi     double,
  predicted_bucket  text,
  warning_level     int,
  warning_message   text,
  confidence        double,
  pm2_5             double,
  pm10              double,
  PRIMARY KEY ((city), ts)
) WITH CLUSTERING ORDER BY (ts DESC);

-- Evaluation of the latest trained models.
CREATE TABLE IF NOT EXISTS model_metrics (
  model       text,
  metric      text,
  value       double,
  trained_at  timestamp,
  PRIMARY KEY ((model), metric)
);

CREATE TABLE IF NOT EXISTS confusion_matrix (
  actual     text,
  predicted  text,
  cnt        bigint,
  PRIMARY KEY ((actual), predicted)
);

CREATE TABLE IF NOT EXISTS feature_importance (
  model       text,
  feature     text,
  importance  double,
  PRIMARY KEY ((model), feature)
);
