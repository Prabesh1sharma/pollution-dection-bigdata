# Real-time Air Pollution Warning – Kathmandu · Pokhara · Biratnagar

Big-data subject project. A Kaggle pollution dataset is cleaned and used to train **Apache Spark MLlib**
models; live air-quality observations from a public API flow through **Kafka** into a **Spark Structured
Streaming** job that scores them in real time, saves every prediction in **Cassandra**, and archives raw
data in **HDFS**. **FastAPI** serves the results to a **Next.js** dashboard.

```
                      ┌────────────── batch (once) ──────────────┐
 Kaggle CSV ──► HDFS ─► Spark: clean → Parquet → train RF models ─┬─► HDFS /models
 (station_hour.csv)                                               └─► Cassandra (metrics, confusion matrix)

 Open-Meteo API ─► producer ─► Kafka ─► Spark Structured Streaming (MLlib inference)
  (hourly, 3 cities)  (topic air-quality-raw)        │
                                                     ├─► Cassandra: readings / predictions / alerts
                                                     ├─► HDFS: Parquet data lake (/lake)
                                                     └─► Kafka topics: air-quality-predictions, air-quality-alerts
                                                                     │
                                          FastAPI ◄──── Cassandra ───┘
                                             ▲
                                   Next.js dashboards  (Live · History · Prediction analysis)
```

| Tool | Role |
|---|---|
| Apache Kafka (KRaft) | ingestion bus, plus output topics for predictions/alerts (Kafka UI included) |
| Apache Hadoop HDFS | stores the Kaggle CSV, cleaned Parquet, trained models, raw-data lake, stream checkpoints |
| Apache Spark 3.5 (master + worker) | batch cleaning/training (MLlib), Structured Streaming inference |
| Apache Cassandra 4.1 | time-series store: raw readings, saved predictions, alerts, model metrics |
| FastAPI · Next.js | API and dashboards |

## Run it

Needs Docker with ~8 GB RAM free (Cassandra, Spark and HDFS are heavy). Everything runs in containers.

```bash
cp .env.example .env            # add KAGGLE_USERNAME / KAGGLE_KEY (kaggle.com → Settings → API)

# 1. Dataset (downloaded inside a throw-away container) – ~2.5M rows
./scripts/download_kaggle.sh

# 2. Start the stack (first build downloads images + Spark connector jars; takes a while).
#    Streaming is held back until training finishes to save memory.
docker compose up -d --build

# 3. Put the dataset into HDFS, then train
./scripts/load_hdfs.sh
docker compose --profile train run --rm spark-train

# 4. Start real-time inference after the models have been saved
docker compose --profile streaming up -d
```

`./scripts/load_hdfs.sh` uploads the header and about 10% of CSV rows to HDFS as a gzip stream by default. Set
`DATA_ROW_STRIDE=1` in `.env` to upload every row, or adjust the stride (for example, `20` for about 5%). The local
CSV remains unchanged. The script also exits HDFS safe mode if needed before re-uploading, for this single-node
development cluster.

The training job samples 20% of the training split and uses 20 trees of depth 8 by default to fit an 8 GB
development machine. Override `NUM_TREES`, `MAX_DEPTH`, or `TRAIN_SAMPLE_FRACTION` in `.env` for a larger model.
Once started, `spark-streaming` scores observations from Kafka (7 days of hourly back-fill, then new observations
every 5 minutes). Open **http://localhost:3000** after a minute or two.

| URL | What |
|---|---|
| http://localhost:3000 | Dashboards: **Live**, **History**, **Prediction analysis** |
| http://localhost:8000/docs | FastAPI Swagger UI |
| http://localhost:8080 / :8081 | Spark master / worker UI |
| http://localhost:9870 | HDFS NameNode UI |
| http://localhost:8089 | Kafka UI |

Useful commands:

```bash
docker compose logs -f producer spark-streaming        # watch data flow
docker compose exec cassandra cqlsh -e "SELECT city, ts, predicted_aqi, predicted_bucket FROM airquality.predictions_by_city LIMIT 10;"
docker compose restart spark-streaming                 # reload models after re-training
docker compose down            # stop (Cassandra/Kafka data kept; HDFS contents are lost – re-run steps 3)
```

Small machine? Defaults are set conservatively (`SPARK_WORKER_MEMORY=1500m`, 2 worker cores, 20 trees). If a previous
stack already has streaming running, stop it before training with `docker compose stop spark-streaming`.
To try the pipeline without a Kaggle account: `python scripts/make_sample_data.py data/station_hour.csv 20000 10`
(synthetic data, smoke-testing only).

## What each part does

**Dataset** – Kaggle *Air Quality Data in India (2015–2020)*, `station_hour.csv` (hourly CPCB station readings,
~2.5M rows). `spark/jobs/train_model.py` drops invalid readings (negatives, sensor spikes), requires a PM reading,
writes Parquet to HDFS, then trains two Random Forest pipelines (median imputer → assembler → RF) on
`PM2.5, PM10, NO2, SO2, CO, O3, hour, month`:
a **regressor** (AQI 0–500) and a **classifier** (Good / Satisfactory / Moderate / Poor / Very Poor / Severe =
the warning level). The split is **time-based** (oldest 80 % train, newest 20 % test); RMSE/MAE/R², accuracy/F1,
confusion matrix and feature importance are stored in Cassandra for the analysis dashboard.

**Real-time source** – [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api): free, no key,
hourly PM2.5/PM10/CO/NO2/SO2/O3 for any coordinates. `producer/producer.py` polls Kathmandu, Pokhara and
Biratnagar and publishes each new hourly observation to Kafka once.

**Streaming** – `spark/jobs/stream_predict.py` converts CO µg/m³ → mg/m³ (the Kaggle unit), uses Nepal local
hour/month, scores with both models, and writes `readings_by_city`, `predictions_by_city`, `alerts_by_city`
(level ≥ Poor), the HDFS lake and the Kafka output topics.

**API** (`backend/`) – `/api/live`, `/api/predictions`, `/api/alerts`, `/api/history` (hourly or daily),
`/api/analysis`, `/api/health`. It also computes the **CPCB AQI formula** from each row's pollutants and uses it
as an independent reference when judging the predictions.

**Dashboards** (`frontend/`) – *Live*: current level, advice and pollutants per city, 48 h chart, alert list.
*History*: pollutant and AQI trends, daily summary. *Prediction analysis*: warning-level distribution, typical
day, predicted-vs-formula AQI, error/agreement per city, model metrics, confusion matrix, feature importance,
saved predictions with CSV export.

## Things to know (read before the demo / report)

- **Source vs. training data differ.** Open-Meteo values are CAMS *model estimates* for a coordinate; the model
  was trained on *station measurements in India*. Expect some distribution shift – say so in the report.
- **High accuracy is partly expected.** The dataset's AQI is itself a formula of the same pollutants, so the
  models largely learn that formula. The "formula AQI" shown on the dashboards makes this visible. For a more
  interesting variant, predict a *future* AQI (e.g. +6 h) using lagged features.
- The regressor's AQI and the classifier's category can disagree near a boundary (e.g. AQI 205 but "Moderate");
  the warning level comes from the classifier, the number from the regressor.
- The API's own `us_aqi`/`european_aqi` are stored as reference only (different scales).
- Models are loaded when the streaming job starts; restart it after re-training.

## Verification status

Checked in the development sandbox (no Docker daemon available there):
Spark training + scoring logic (PySpark 3.5 local mode, synthetic data in the Kaggle schema: ~98 % classifier
accuracy), backend endpoints (`cd backend && python -m pytest`, Cassandra faked), `docker compose config`,
frontend type-check/build and rendering against fake API data.

**Not run end-to-end:** the container stack itself (Kafka ↔ Spark ↔ Cassandra ↔ HDFS wiring, image builds,
connector jar downloads) and the live Open-Meteo call (blocked in the sandbox). If something fails on first
start, `docker compose logs <service>` will show it; the most likely spots are HDFS start-up timing and
Spark `--packages` downloads on a slow connection.
