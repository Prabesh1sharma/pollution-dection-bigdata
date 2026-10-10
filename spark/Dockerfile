# Spark 3.5 + numpy/pandas (pyspark.ml imports both). Used for master, worker and the
# jobs so driver and executors run identical Python environments.
FROM apache/spark:3.5.3-python3
USER root
RUN pip install --no-cache-dir numpy==1.24.4 pandas==2.0.3
USER spark
