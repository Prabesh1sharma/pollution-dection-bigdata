"""Shared feature / prediction logic used by the training and streaming jobs."""
from pyspark.ml.functions import vector_to_array
from pyspark.sql import DataFrame, functions as F

# Model inputs. Units follow the Kaggle (CPCB) dataset: ug/m3 for everything except
# CO, which is mg/m3. The streaming job converts the API's CO from ug/m3 to mg/m3.
POLLUTANTS = ["pm2_5", "pm10", "no2", "so2", "co", "o3"]
FEATURES = POLLUTANTS + ["hour", "month"]

# CPCB (India) AQI categories, index == warning level.
BUCKETS = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]
MESSAGES = [
    "Air quality is good. No precautions needed.",
    "Satisfactory. Unusually sensitive people may want to limit prolonged outdoor exertion.",
    "Moderate. People with lung or heart disease, children and older adults should reduce prolonged outdoor exertion.",
    "Poor. Avoid prolonged outdoor activity; sensitive groups should stay indoors.",
    "Very poor. Wear an N95 mask outdoors and avoid outdoor exercise.",
    "Severe. Health-emergency conditions. Stay indoors, use an air purifier and avoid all outdoor activity.",
]
ALERT_LEVEL = 3  # "Poor" and worse are stored as alerts

LOCAL_TZ = "Asia/Kathmandu"


def bucket_index(aqi_col):
    """CPCB AQI value -> category index 0..5 (same bands as the Kaggle AQI_Bucket)."""
    a = F.col(aqi_col) if isinstance(aqi_col, str) else aqi_col
    return (
        F.when(a <= 50, 0)
        .when(a <= 100, 1)
        .when(a <= 200, 2)
        .when(a <= 300, 3)
        .when(a <= 400, 4)
        .otherwise(5)
    )


def predict_frame(df: DataFrame, reg_model, cls_model) -> DataFrame:
    """Score a frame holding FEATURES with the regressor + classifier pipelines.

    Returns every input column plus: predicted_aqi, predicted_bucket,
    warning_level, warning_message, confidence.
    """
    base_cols = df.columns
    reg = reg_model.transform(df).select(*base_cols, F.col("prediction").alias("predicted_aqi"))
    cls = cls_model.transform(reg).select(
        *reg.columns,
        F.col("prediction").cast("int").alias("warning_level"),
        F.array_max(vector_to_array("probability")).alias("confidence"),
    )
    buckets = F.array(*[F.lit(b) for b in BUCKETS])
    messages = F.array(*[F.lit(m) for m in MESSAGES])
    return (
        cls.withColumn("predicted_aqi", F.round(F.least(F.greatest(F.col("predicted_aqi"), F.lit(0.0)), F.lit(500.0)), 1))
        .withColumn("predicted_bucket", F.element_at(buckets, F.col("warning_level") + 1))
        .withColumn("warning_message", F.element_at(messages, F.col("warning_level") + 1))
        .withColumn("confidence", F.round("confidence", 4))
    )
