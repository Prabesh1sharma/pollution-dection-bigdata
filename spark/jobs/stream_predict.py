"""Structured Streaming job: Kafka -> MLlib inference -> Cassandra / HDFS / Kafka.

For every micro-batch of observations from topic `air-quality-raw` it
  1. stores the raw readings in Cassandra (readings_by_city) and the HDFS data lake,
  2. scores them with the saved MLlib regressor + classifier,
  3. saves predictions (predictions_by_city) and alerts (alerts_by_city, level >= Poor),
  4. republishes predictions / alerts to Kafka topics for other consumers.

The job waits (retrying) until train_model.py has produced the models.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pyspark.ml import PipelineModel
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType

from common import ALERT_LEVEL, LOCAL_TZ, predict_frame

KAFKA = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC_RAW = os.getenv("TOPIC_RAW", "air-quality-raw")
TOPIC_PRED = os.getenv("TOPIC_PREDICTIONS", "air-quality-predictions")
TOPIC_ALERT = os.getenv("TOPIC_ALERTS", "air-quality-alerts")
MODEL_DIR = os.getenv("MODEL_DIR", "hdfs://namenode:8020/models")
LAKE_DIR = os.getenv("LAKE_DIR", "hdfs://namenode:8020/lake")
CHECKPOINT = os.getenv("CHECKPOINT_DIR", "hdfs://namenode:8020/checkpoints/stream_predict")
TRIGGER = os.getenv("TRIGGER_INTERVAL", "10 seconds")

SCHEMA = StructType([
    StructField("city", StringType()),
    StructField("ts", StringType()),
    StructField("latitude", DoubleType()),
    StructField("longitude", DoubleType()),
    StructField("pm2_5", DoubleType()),
    StructField("pm10", DoubleType()),
    StructField("co", DoubleType()),   # ug/m3 as delivered by the API
    StructField("no2", DoubleType()),
    StructField("so2", DoubleType()),
    StructField("o3", DoubleType()),
    StructField("us_aqi", IntegerType()),
    StructField("eu_aqi", IntegerType()),
])


def write_cassandra(df, table):
    (df.write.format("org.apache.spark.sql.cassandra").mode("append")
       .options(keyspace="airquality", table=table).save())


def write_kafka(df, topic):
    (df.select(F.col("city").alias("key"), F.to_json(F.struct(*df.columns)).alias("value"))
       .write.format("kafka").option("kafka.bootstrap.servers", KAFKA).option("topic", topic).save())


def load_models():
    while True:
        try:
            reg = PipelineModel.load(f"{MODEL_DIR}/aqi_regressor")
            cls = PipelineModel.load(f"{MODEL_DIR}/aqi_classifier")
            print("models loaded from", MODEL_DIR, flush=True)
            return reg, cls
        except Exception as exc:  # models not trained yet
            print(f"waiting for trained models in {MODEL_DIR} ({type(exc).__name__}); retry in 20s", flush=True)
            time.sleep(20)


def main():
    spark = (SparkSession.builder.appName("aq-stream")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    reg_model, cls_model = load_models()

    raw = (spark.readStream.format("kafka")
           .option("kafka.bootstrap.servers", KAFKA)
           .option("subscribe", TOPIC_RAW)
           .option("startingOffsets", "earliest")
           .option("failOnDataLoss", "false")
           .option("maxOffsetsPerTrigger", 2000)
           .load())
    parsed = (raw.select(F.from_json(F.col("value").cast("string"), SCHEMA).alias("d")).select("d.*")
              .withColumn("ts", F.col("ts").cast("timestamp"))
              .filter(F.col("city").isNotNull() & F.col("ts").isNotNull()))

    def process_batch(batch, batch_id):
        batch = batch.dropDuplicates(["city", "ts"]).cache()
        n = batch.count()
        if n == 0:
            batch.unpersist()
            return

        # 1) raw readings -> Cassandra + data lake
        readings = batch.select(
            "city", "ts", "latitude", "longitude", "pm2_5", "pm10", "co", "no2", "so2", "o3",
            F.col("us_aqi").alias("ref_us_aqi"), F.col("eu_aqi").alias("ref_eu_aqi"),
            F.current_timestamp().alias("ingested_at"))
        write_cassandra(readings, "readings_by_city")
        readings.write.mode("append").partitionBy("city").parquet(f"{LAKE_DIR}/raw_readings")

        # 2) features: CO -> mg/m3 (training units), hour/month in local (Nepal) time
        local = F.from_utc_timestamp("ts", LOCAL_TZ)
        feats = (batch.withColumn("co", F.col("co") / 1000.0)
                 .withColumn("hour", F.hour(local)).withColumn("month", F.month(local))
                 .withColumnRenamed("us_aqi", "ref_us_aqi").withColumnRenamed("eu_aqi", "ref_eu_aqi"))
        scored = predict_frame(feats, reg_model, cls_model).withColumn("predicted_at", F.current_timestamp())

        # 3) predictions + alerts
        preds = scored.select(
            "city", "ts", "pm2_5", "pm10", "co", "no2", "so2", "o3", "predicted_aqi", "predicted_bucket",
            "warning_level", "warning_message", "confidence", "ref_us_aqi", "ref_eu_aqi", "predicted_at").cache()
        write_cassandra(preds, "predictions_by_city")
        preds.write.mode("append").partitionBy("city").parquet(f"{LAKE_DIR}/predictions")
        alerts = preds.filter(F.col("warning_level") >= ALERT_LEVEL).select(
            "city", "ts", "predicted_aqi", "predicted_bucket", "warning_level", "warning_message",
            "confidence", "pm2_5", "pm10")
        write_cassandra(alerts, "alerts_by_city")

        # 4) publish for downstream consumers
        write_kafka(preds, TOPIC_PRED)
        if alerts.count() > 0:
            write_kafka(alerts, TOPIC_ALERT)

        print(f"batch {batch_id}: scored {n} observations, {alerts.count()} alerts", flush=True)
        preds.unpersist()
        batch.unpersist()

    (parsed.writeStream.foreachBatch(process_batch)
     .option("checkpointLocation", CHECKPOINT)
     .trigger(processingTime=TRIGGER)
     .start().awaitTermination())


if __name__ == "__main__":
    main()
