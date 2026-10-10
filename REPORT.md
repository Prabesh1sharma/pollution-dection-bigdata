# Real-Time Air Pollution Warning System for Kathmandu, Pokhara and Biratnagar

## 1. Introduction

Air quality is one of the most visible public-health problems in urban Nepal, and reliable,
timely warnings are hard to produce from a single monitoring station. This project builds an
end-to-end **big-data pipeline** that learns the relationship between common air pollutants and
the official Air Quality Index (AQI), then applies that knowledge in real time to live hourly
observations for three cities: **Kathmandu, Pokhara and Biratnagar**.

The system has two clearly separated halves:

* A **batch half** that takes a large historical pollution dataset, cleans it, and trains machine
  learning models capable of predicting both the AQI number (0–500) and its warning category
  (Good, Satisfactory, Moderate, Poor, Very Poor, Severe).
* A **streaming half** that continuously pulls fresh hourly observations from a public
  air-quality API, scores each observation with the trained models, stores the results, raises
  alerts when the air becomes poor, and displays everything on a web dashboard.

The goal is not only to store data, but to demonstrate the full modern data path: **ingest →
process → learn → serve**, across four different storage/compute systems that each solve a specific
part of the problem. The project deliberately uses realistic tools (a message bus, a distributed
file system, a distributed compute engine, and a time-series database) so that the same design
could scale from three cities to hundreds.

Everything runs inside containers on a single development laptop, which keeps the project portable
while still exercising the real cluster-style interfaces of each tool.

---

## 2. Big Data Tools Used

| Tool | Version / Mode | Role in the project |
|---|---|---|
| **Apache Kafka** | KRaft mode (no ZooKeeper) | Central ingestion bus. Live observations are published to one topic; predicted values and alerts are published to two further output topics. Provides buffering and decoupling between the producer and the analytics engine. |
| **Apache Hadoop HDFS** | Single-node NameNode + DataNode | Distributed storage layer. Holds the raw historical dataset, the cleaned columnar copy used for training, the serialised trained models, and the Parquet data lake of streamed raw readings and predictions. |
| **Apache Spark** | 3.5, master + worker cluster | The compute engine. Used twice: (a) **batch** for cleaning, feature preparation and model training with **MLlib**; (b) **Structured Streaming** for continuous, near-real-time scoring of the incoming feed. |
| **Apache Cassandra** | 4.1, single node | Scalable, write-optimised time-series store. Keeps raw readings, saved predictions, alerts and model evaluation data. Its partition-by-city model makes per-city time-range queries very fast. |
| **FastAPI (Python)** | — | REST API layer that reads from Cassandra and exposes live readings, prediction history, alerts, analysis figures and a health check. Also computes an independent reference AQI used to judge the models. |
| **Next.js (React/TypeScript)** | — | Dashboard front end with three views: *Live*, *History* and *Prediction analysis*. |
| **Docker / Docker Compose** | Desktop | Packaging and orchestration of all the above as a single reproducible stack with health checks and dependency ordering. |
| **Machine Learning (Spark MLlib)** | Random Forest | Two supervised models: a **regression** model for the AQI value and a **classification** model for the warning category. |

Supporting components: an **Ingestion service** (polls the public air-quality API and publishes to
Kafka), a **Kafka UI** for inspecting topics, and the **Spark/HDFS web UIs** for monitoring cluster
state.

---

## 3. How We Set Up the System

### 3.1 Environment

The whole stack is described declaratively and started with a single orchestration file. Each
component is an isolated container with its own dependencies, exposed ports and health check, and
named volumes preserve the state of Cassandra and Kafka between restarts.

Because the target machine has 8 GB of RAM, the resource limits were tuned conservatively:

* The container engine's virtual machine memory was raised so that the four heavy services
  (Hadoop, Spark, Cassandra, Kafka) can coexist without being killed by the operating system.
* The Spark worker runs a small number of cores with limited memory, and the batch models use a
  modest number of trees and a reduced sampling fraction.
* Memory limits were set explicitly for Cassandra, the HDFS daemons and the Spark executors to keep
  each service within a safe budget.

### 3.2 Start-up Sequence

1. **Build and launch the stack.** All services are brought up together; the streaming job is
   intentionally delayed so that the historical processing and training can use the full machine
   first.
2. **Load the historical dataset into the distributed file system.** A helper uploads the dataset
   (header plus a sampled fraction of rows, compressed) so that the data lives inside HDFS rather
   than on the local disk.
3. **Run the batch training job.** A one-shot Spark job reads the dataset from HDFS, cleans it,
   trains both models and writes the models back to HDFS together with all evaluation results.
4. **Start real-time inference.** The streaming job is then launched; it loads the trained models
   from HDFS and begins consuming the live feed.
5. **Open the dashboards.** The web front end, the API documentation, and the monitoring UIs for
   Spark, HDFS and Kafka are all reachable on fixed local ports.

### 3.3 Operational Safeguards

* Health checks and dependency conditions ensure that Cassandra, Kafka and HDFS are actually ready
  before dependent services start, avoiding race conditions on cold boot.
* The system was validated step by step: confirming Cassandra was healthy, that HDFS had left safe
  mode and stored the data, that training produced the expected model files, and that the streaming
  job had loaded the models before trusting the dashboard figures.

---

## 4. Methodology

### 4.1 Historical Dataset and Cleaning

The training data is a large public dataset of hourly pollutant measurements from ground stations
roughly 2.5 million rows. The cleaning step:

* removes physically impossible values (negative concentrations, sensor spikes),
* keeps only rows that carry at least one particulate matter reading (the pollutants most strongly
  tied to AQI),
* normalises units so that the live feed and the historical data share the same measurement scale
  (in particular, carbon monoxide is converted between the units used by the API and the units used
  in training),
* stores the cleaned, compressed, columnar copy back into HDFS so that training reads efficiently.

### 4.2 Feature Engineering

Each observation is represented by eight features:

* the five key pollutants: **PM2.5, PM10, NO₂, SO₂, CO and O₃**, and
* two temporal features: **hour of day** and **month**.

The temporal features matter because pollution has a strong daily and seasonal rhythm (traffic peaks,
winter inversions). Missing pollutant values are filled in with a median imputation step so that
every row is complete before it reaches the model.

### 4.3 Models

Two complementary models are trained on the same features:

1. **A regression model** that outputs the **AQI value** on the 0–500 scale.
2. **A classification model** that outputs the **warning category** — Good, Satisfactory, Moderate,
   Poor, Very Poor or Severe.

Using two models lets the dashboard show both a precise number (from the regressor) and a stable,
human-readable warning level (from the classifier). The evaluation uses:

* regression: **RMSE, MAE and R²**,
* classification: **accuracy, F1 score and a full confusion matrix**,
* **feature importance** for both models, to show which pollutants drive the predictions.

### 4.4 Evaluation Strategy

The train/test split is **time-based** rather than random: the oldest 80 % of the data is used for
training and the newest 20 % for testing. This mirrors the real forecasting situation, where a
model is always asked about *future* observations, and prevents accidentally leaking information
from later periods into training.

### 4.5 Streaming Inference Methodology

In the streaming half, the design principle is **score once, store everything, alert when needed**.
For every new observation the system:

1. reads the observation from the ingestion topic,
2. converts units to match the training scale,
3. scores it with both trained models,
4. stores the raw reading, the prediction and (when the level is Poor or worse) an alert,
5. archives the raw readings and predictions into the distributed data lake, and
6. republishes the predictions and alerts to output topics for any downstream consumer.

An important methodological detail is that the API also supplies its own AQI value. Rather than
trust it blindly, the system additionally computes an **independent national-standard AQI** directly
from the pollutant concentrations and uses it as an unbiased reference when comparing model
performance on live data. This keeps the evaluation honest and highlights any distribution shift
between the historical training data and the live source.

### 4.6 Storage Design

The time-series store is organised around the query pattern "give me the latest data for one city".
Each table is partitioned by city and clustered by time in descending order, so the newest rows are
cheapest to read. Separate tables hold raw readings, saved predictions, alerts, model metrics,
the confusion matrix and feature importance.

---

## 5. Working of the System

### 5.1 End-to-End Flow

```
Historical dataset ─► HDFS ─► Batch processing: clean → train ─► HDFS (models)
                                                              └─► Cassandra (metrics, confusion matrix)

Live API ─► Ingestion service ─► Kafka ─► Streaming engine (inference)
                                            ├─► Cassandra: readings / predictions / alerts
                                            ├─► HDFS: Parquet data lake
                                            └─► Kafka: prediction & alert topics
                                                        │
                                          API ◄── Cassandra
                                            ▲
                                    Dashboards
```

### 5.2 Batch Pipeline (Learning)

The batch job reads the historical dataset from HDFS, applies the cleaning rules, builds the feature
set, fills missing values and trains both Random Forest models. When training finishes it:

* writes the **trained models to HDFS**, from where the streaming job later loads them,
* writes the **evaluation results** (RMSE, MAE, R², accuracy, F1), the **confusion matrix** and the
  **feature importance** into Cassandra so the analysis dashboard can display them.

In our run the models trained successfully and were saved to the distributed file system. The
regression model reached an **R² of about 0.62** with an **MAE of about 40 AQI points**, and the
feature-importance report confirmed the expected physics: **PM2.5 and PM10 dominate** the
predictions, followed by carbon monoxide, which is exactly the behaviour a sensible air-quality
model should show.

### 5.3 Real-Time Pipeline (Inference)

When the streaming job starts it **loads the trained models from HDFS** and connects to Kafka. On
start-up the ingestion service back-fills several days of hourly history so the dashboard is
populated immediately, and afterwards it polls the API every few minutes and publishes only
genuinely new observations.

The streaming job consumes the feed in small micro-batches. For each batch it parses the
observations, converts units, drops duplicates, scores everything with the two models, and writes
the results to all three destinations at once: the time-series database (for the API and dashboard),
the distributed data lake (for long-term archive and future re-training), and the Kafka output
topics (for any real-time downstream consumer). Records whose predicted warning level is Poor or
worse are additionally written as alerts.

In our verified run the first scoring batch completed successfully and produced **534 scored
observations and 16 alerts**, matching the stored prediction count in the database exactly — a
strong confirmation that the message bus, the compute engine and the database are all correctly
wired together.

### 5.4 API Layer

The API reads from the time-series database and exposes:

* the **latest reading and prediction per city**, together with the current warning level and a
  short piece of health advice,
* **historical series** for charts, at hourly or daily resolution,
* the list of **alerts**,
* an **analysis** endpoint that returns the model metrics, the confusion matrix, feature importance
  and distribution statistics, and
* a **health** endpoint that reports whether the database connection is alive.

Each live row also carries the independently computed standard AQI, so the dashboard can compare the
model's number against the formula's number side by side.

### 5.5 Dashboards

The front end presents three views:

* **Live** — the current warning level, the advice, the pollutant concentrations and a rolling chart
  for each city, plus the alert list.
* **History** — pollutant and AQI trends over time and a daily summary.
* **Prediction analysis** — the distribution of warning levels, a "typical day" profile, the
  predicted-versus-formula AQI comparison, the error and agreement per city, the model metrics, the
  confusion matrix, the feature importance and the saved predictions with a CSV export.

### 5.6 Observed Behaviour and Known Characteristics

At the end of our run every service was healthy: the database was up, HDFS had stored the data, the
models had been written and loaded, streaming was scoring batches, the API was returning fresh
predictions for all three cities, and the dashboard was responding normally.

Two characteristics are worth stating honestly, because they are inherent to the design rather than
faults:

* **The live source and the training source differ.** The live feed provides model-based
  estimates for a coordinate, whereas the models were trained on ground-station measurements from a
  different region. Some distribution shift is therefore expected, which is precisely why the
  independent standard-AQI reference is shown alongside the prediction.
* **The high agreement is partly expected.** In the historical dataset the AQI is itself a formula
  of the same pollutants, so the models largely re-learn that formula. The dashboard's
  "formula AQI" column makes this effect transparent. A more challenging variant would predict a
  *future* AQI using lagged features.

### 5.7 Conclusion

The project demonstrates a complete, containerised big-data workflow: a distributed file system as
the source of truth, a message bus for ingest, a distributed compute engine for both learning and
streaming inference, a scalable time-series database for serving, and a modern API and dashboard on
top. The batch half turns raw measurements into two trained models, and the streaming half applies
those models to a live feed — storing, archiving, alerting and visualising the results in near real
time. The architecture is deliberately modular, so each stage could be scaled or replaced
independently as the number of cities and monitors grows.
