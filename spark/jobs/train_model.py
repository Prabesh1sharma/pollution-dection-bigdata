"""Batch job: Kaggle CSV -> clean -> Parquet (HDFS) -> train Spark MLlib models.

Dataset: "Air Quality Data in India (2015-2020)" (rohanrao/air-quality-data-in-india),
file station_hour.csv - hourly readings from CPCB stations, ~2.5M rows.

Trains two Random Forest pipelines on the same features:
  * regressor   -> AQI value (0-500)
  * classifier  -> AQI category (Good ... Severe), used as the warning level
Evaluation uses a time-based split (oldest 80% train, newest 20% test).

Env: DATA_PATH, CLEAN_PATH, MODEL_DIR, USE_CASSANDRA (default true), NUM_TREES, MAX_DEPTH.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import BUCKETS, FEATURES, POLLUTANTS, bucket_index
from pyspark import StorageLevel
from pyspark.ml import Pipeline
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml.evaluation import MulticlassClassificationEvaluator, RegressionEvaluator
from pyspark.ml.feature import Imputer, VectorAssembler
from pyspark.ml.regression import RandomForestRegressor
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

DATA_PATH = os.getenv("DATA_PATH", "hdfs://namenode:8020/data/station_hour.csv.gz")
CLEAN_PATH = os.getenv(
    "CLEAN_PATH", "hdfs://namenode:8020/data/clean/station_hour.parquet"
)
MODEL_DIR = os.getenv("MODEL_DIR", "hdfs://namenode:8020/models")
USE_CASSANDRA = os.getenv("USE_CASSANDRA", "true").lower() == "true"
NUM_TREES = int(os.getenv("NUM_TREES", "20"))
MAX_DEPTH = int(os.getenv("MAX_DEPTH", "8"))
TRAIN_SAMPLE_FRACTION = float(os.getenv("TRAIN_SAMPLE_FRACTION", "0.2"))
TRAIN_PARTITIONS = int(os.getenv("TRAIN_PARTITIONS", "2"))

if not 0 < TRAIN_SAMPLE_FRACTION <= 1:
    raise ValueError("TRAIN_SAMPLE_FRACTION must be greater than 0 and at most 1")
if TRAIN_PARTITIONS < 1:
    raise ValueError("TRAIN_PARTITIONS must be at least 1")

# Plausible upper bounds; anything above is a sensor glitch -> null (then imputed).
UPPER = {"pm2_5": 1000, "pm10": 2000, "no2": 500, "so2": 500, "co": 100, "o3": 500}
RENAME = {
    "PM2.5": "pm2_5",
    "PM10": "pm10",
    "NO2": "no2",
    "SO2": "so2",
    "CO": "co",
    "O3": "o3",
}


def save_cassandra(df, table):
    if not USE_CASSANDRA:
        return
    (
        df.write.format("org.apache.spark.sql.cassandra")
        .mode("append")
        .options(keyspace="airquality", table=table)
        .save()
    )


def build_pipeline(estimator):
    imputer = Imputer(
        strategy="median",
        inputCols=POLLUTANTS,
        outputCols=[f"{c}_imp" for c in POLLUTANTS],
    )
    assembler = VectorAssembler(
        inputCols=[f"{c}_imp" for c in POLLUTANTS] + ["hour", "month"],
        outputCol="features",
    )
    return Pipeline(stages=[imputer, assembler, estimator])


def clean(spark):
    raw = spark.read.option("header", True).option("inferSchema", True).csv(DATA_PATH)
    df = raw
    for src, dst in RENAME.items():
        df = df.withColumnRenamed(src, dst)
    df = df.withColumn("ts", F.to_timestamp("Datetime")).withColumn(
        "AQI", F.col("AQI").cast("double")
    )
    for c in POLLUTANTS:
        df = df.withColumn(c, F.col(c).cast("double"))
        # negative values and absurd spikes are invalid readings
        df = df.withColumn(
            c, F.when((F.col(c) < 0) | (F.col(c) > UPPER[c]), None).otherwise(F.col(c))
        )
    df = (
        df.filter(F.col("ts").isNotNull() & F.col("AQI").between(0, 500))
        .filter(
            F.col("pm2_5").isNotNull() | F.col("pm10").isNotNull()
        )  # AQI needs a PM reading
        .withColumn("hour", F.hour("ts"))
        .withColumn("month", F.month("ts"))
        .withColumn("bucket_idx", bucket_index("AQI").cast("double"))
        .withColumn("epoch", F.col("ts").cast("long"))
        .select(
            "StationId",
            "ts",
            "epoch",
            *FEATURES,
            F.col("AQI").alias("aqi"),
            "bucket_idx",
        )
    )
    df.write.mode("overwrite").parquet(CLEAN_PATH)
    return spark.read.parquet(CLEAN_PATH).repartition(TRAIN_PARTITIONS)


def main():
    spark = (
        SparkSession.builder.appName("aq-train")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    df = clean(spark).persist(StorageLevel.DISK_ONLY)
    print(f"clean rows: {df.count():,}")
    print("category distribution:")
    df.groupBy("bucket_idx").count().orderBy("bucket_idx").show()

    cutoff = df.approxQuantile("epoch", [0.8], 0.001)[0]
    train, test = (
        df.filter(F.col("epoch") <= cutoff),
        df.filter(F.col("epoch") > cutoff),
    )
    train = train.sample(False, TRAIN_SAMPLE_FRACTION, seed=42).cache()
    test.cache()
    print(
        f"sampled train={train.count():,} ({TRAIN_SAMPLE_FRACTION:.0%}) "
        f"test={test.count():,}"
    )

    rf_kwargs = {
        "featuresCol": "features",
        "numTrees": NUM_TREES,
        "maxDepth": MAX_DEPTH,
        "maxBins": 32,
        "seed": 42,
    }
    reg_model = build_pipeline(RandomForestRegressor(labelCol="aqi", **rf_kwargs)).fit(
        train
    )
    cls_model = build_pipeline(
        RandomForestClassifier(labelCol="bucket_idx", **rf_kwargs)
    ).fit(train)

    reg_pred = reg_model.transform(test)
    cls_pred = cls_model.transform(test)

    metrics = []
    for m in ("rmse", "mae", "r2"):
        metrics.append(
            (
                "aqi_regressor",
                m,
                RegressionEvaluator(labelCol="aqi", metricName=m).evaluate(reg_pred),
            )
        )
    for m in ("accuracy", "weightedPrecision", "weightedRecall", "f1"):
        metrics.append(
            (
                "aqi_classifier",
                m,
                MulticlassClassificationEvaluator(
                    labelCol="bucket_idx", metricName=m
                ).evaluate(cls_pred),
            )
        )
    metrics.append(("dataset", "clean_rows", float(df.count())))
    metrics.append(("dataset", "train_rows", float(train.count())))
    metrics.append(("dataset", "test_rows", float(test.count())))
    for model, metric, value in metrics:
        print(f"{model:15s} {metric:18s} {value:,.4f}")

    # Persist models (HDFS) - the streaming job loads these.
    reg_model.write().overwrite().save(f"{MODEL_DIR}/aqi_regressor")
    cls_model.write().overwrite().save(f"{MODEL_DIR}/aqi_classifier")

    # Persist evaluation results (Cassandra) for the analysis dashboard.
    metrics_df = spark.createDataFrame(
        metrics, "model string, metric string, value double"
    ).withColumn("trained_at", F.current_timestamp())
    save_cassandra(metrics_df, "model_metrics")

    names = F.array(*[F.lit(b) for b in BUCKETS])
    cm = (
        cls_pred.groupBy("bucket_idx", "prediction")
        .count()
        .select(
            F.element_at(names, F.col("bucket_idx").cast("int") + 1).alias("actual"),
            F.element_at(names, F.col("prediction").cast("int") + 1).alias("predicted"),
            F.col("count").alias("cnt"),
        )
    )
    cm.show(50, truncate=False)
    save_cassandra(cm, "confusion_matrix")

    rows = []
    for (
        model_name,
        model,
    ) in (("aqi_regressor", reg_model), ("aqi_classifier", cls_model)):
        imps = model.stages[-1].featureImportances.toArray().tolist()
        rows += [(model_name, f, float(i)) for f, i in zip(FEATURES, imps)]
    fi = spark.createDataFrame(rows, "model string, feature string, importance double")
    fi.show(20, truncate=False)
    save_cassandra(fi, "feature_importance")

    print("training finished; models saved under", MODEL_DIR)
    spark.stop()


if __name__ == "__main__":
    main()
