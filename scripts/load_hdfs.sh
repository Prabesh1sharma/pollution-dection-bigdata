#!/usr/bin/env bash
# Stream one in DATA_ROW_STRIDE data rows (plus the header), gzip, and upload to HDFS.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
FILE="${1:-station_hour.csv}"
ROW_STRIDE="${DATA_ROW_STRIDE:-10}"
[ -f "data/$FILE" ] || { echo "data/$FILE not found - run scripts/download_kaggle.sh first"; exit 1; }
[[ "$ROW_STRIDE" =~ ^[1-9][0-9]*$ ]] || { echo "DATA_ROW_STRIDE must be a positive integer"; exit 1; }

# This is a single-NameNode development cluster. A rebuilt DataNode can lose
# its ephemeral blocks while the NameNode still remembers their old metadata.
echo 'Ensuring NameNode is out of safe mode before re-upload...'
docker compose exec -T namenode hdfs dfsadmin -safemode leave

echo "Uploading about 1/$ROW_STRIDE of data/$FILE as gzip to HDFS (header preserved)..."
docker compose exec -T namenode hdfs dfs -mkdir -p /data /models /lake /checkpoints
awk -v stride="$ROW_STRIDE" 'NR == 1 || (NR - 1) % stride == 0' "data/$FILE" \
	| gzip -1 \
	| docker compose exec -T namenode hdfs dfs -put -f - /data/station_hour.csv.gz
docker compose exec -T namenode hdfs dfs -ls -h /data
