# Preprocessing

Initial, conservative data cleaning for CSV files in `data/`.

## What it does

- Drops fully empty rows and columns.
- Normalizes blank strings to missing values.
- Drops rows missing core identifiers:
  - always: `season`, `gameweek`
  - player files: `player_id` or `id`
  - team files: `match_id`, `team`, `side`
- Drops columns that are almost entirely missing (>= 99.5% missing), except protected metadata columns.
- Writes cleaned outputs and a JSON report.

## Run

```bash
bash preprocessing/run_preprocessing.sh
```

Or directly:

```bash
python3 preprocessing/clean_data.py --input-dir data --output-dir data/processed
```
