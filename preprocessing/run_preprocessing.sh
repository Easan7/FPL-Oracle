#!/usr/bin/env bash
set -euo pipefail

python3 preprocessing/clean_data.py \
  --input-dir data \
  --output-dir data/processed \
  --report data/processed/preprocessing_report.json
