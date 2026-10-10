#!/usr/bin/env bash
# Copy data/station_hour.csv (mounted read-only at /local-data in the namenode) into HDFS.
set -euo pipefail
cd "$(dirname "$0")/.."
FILE="${1:-station_hour.csv}"
[ -f "data/$FILE" ] || { echo "data/$FILE not found - run scripts/download_kaggle.sh first"; exit 1; }

docker compose exec -T namenode hdfs dfs -mkdir -p /data /models /lake /checkpoints
docker compose exec -T namenode hdfs dfs -put -f "/local-data/$FILE" /data/station_hour.csv
docker compose exec -T namenode hdfs dfs -ls -h /data
