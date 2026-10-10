#!/usr/bin/env bash
# Download the Kaggle dataset into ./data using a throw-away Docker container
# (nothing to install locally). Needs KAGGLE_USERNAME and KAGGLE_KEY
# (kaggle.com -> Settings -> API -> Create New Token), e.g. in .env.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
: "${KAGGLE_USERNAME:?set KAGGLE_USERNAME in .env}"
: "${KAGGLE_KEY:?set KAGGLE_KEY in .env}"

docker run --rm \
  -e KAGGLE_USERNAME -e KAGGLE_KEY \
  -v "$PWD/data:/data" python:3.11-slim \
  sh -c "pip install -q kaggle && kaggle datasets download -d rohanrao/air-quality-data-in-india -p /data --unzip"

ls -lh data/station_hour.csv
