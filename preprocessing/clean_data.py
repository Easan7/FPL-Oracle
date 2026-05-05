#!/usr/bin/env python3
"""Initial preprocessing for FPL Oracle CSV files (stdlib-only)."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ALMOST_EMPTY_COL_THRESHOLD = 0.995  # 99.5% missing


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null", "na"}


def _required_columns_for_file(filename: str, columns: list[str]) -> list[str]:
    required = ["season", "gameweek"]
    lower = filename.lower()

    if "player" in lower:
        if "player_id" in columns:
            required.append("player_id")
        elif "id" in columns:
            required.append("id")

    if "team" in lower:
        for col in ["match_id", "team", "side"]:
            if col in columns:
                required.append(col)

    return required


def _row_all_missing(row: dict[str, str], columns: list[str]) -> bool:
    return all(_is_missing(row.get(c)) for c in columns)


def _compute_missing_ratio(rows: list[dict[str, str]], columns: list[str]) -> dict[str, float]:
    if not rows:
        return {c: 1.0 for c in columns}
    ratios: dict[str, float] = {}
    total = len(rows)
    for c in columns:
        miss = sum(1 for r in rows if _is_missing(r.get(c)))
        ratios[c] = miss / total
    return ratios


def _load_player_lookup(path: Path) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    if not path.exists():
        return lookup
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = str(row.get("player_id", "")).strip()
            if not pid:
                continue
            lookup[pid] = {
                "first_name": str(row.get("first_name", "") or "").strip(),
                "second_name": str(row.get("second_name", "") or "").strip(),
                "position": str(row.get("position", "") or "").strip(),
            }
    return lookup


def _load_mapping_lookup(path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    lookup: dict[str, dict[str, str]] = {}
    columns: list[str] = []
    if not path.exists():
        return lookup, columns

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = list(reader.fieldnames or [])
        for row in reader:
            pid = str(row.get("player_id", "")).strip()
            if not pid:
                continue
            lookup[pid] = {k: str(v or "").strip() for k, v in row.items()}
    return lookup, columns


def _pick_player_lookup_for_file(
    filename: str,
    lookup_2425: dict[str, dict[str, str]],
    lookup_2526: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    lower = filename.lower()
    if "2024-2025" in lower:
        return lookup_2425
    if "2025-2026" in lower:
        return lookup_2526
    return {}


def _pick_mapping_for_file(
    filename: str,
    mapping_2425: dict[str, dict[str, str]],
    mapping_cols_2425: list[str],
    mapping_2526: dict[str, dict[str, str]],
    mapping_cols_2526: list[str],
) -> tuple[dict[str, dict[str, str]], list[str]]:
    lower = filename.lower()
    if "2024-2025" in lower:
        return mapping_2425, mapping_cols_2425
    if "2025-2026" in lower:
        return mapping_2526, mapping_cols_2526
    return {}, []


def _enrich_player_rows(
    rows: list[dict[str, str]],
    columns: list[str],
    filename: str,
    lookup_2425: dict[str, dict[str, str]],
    lookup_2526: dict[str, dict[str, str]],
    mapping_2425: dict[str, dict[str, str]],
    mapping_cols_2425: list[str],
    mapping_2526: dict[str, dict[str, str]],
    mapping_cols_2526: list[str],
) -> tuple[list[dict[str, str]], list[str], int, int]:
    lower = filename.lower()
    if "player" not in lower:
        return rows, columns, 0, 0

    id_col = "player_id" if "player_id" in columns else ("id" if "id" in columns else None)
    if not id_col:
        return rows, columns, 0, 0

    lookup = _pick_player_lookup_for_file(filename, lookup_2425, lookup_2526)
    mapping_lookup, mapping_columns = _pick_mapping_for_file(
        filename=filename,
        mapping_2425=mapping_2425,
        mapping_cols_2425=mapping_cols_2425,
        mapping_2526=mapping_2526,
        mapping_cols_2526=mapping_cols_2526,
    )

    for c in ["first_name", "second_name", "position"]:
        if c not in columns:
            columns.append(c)
    for c in mapping_columns:
        if c not in columns:
            columns.append(c)

    mapped_rows = 0
    mapping_rows = 0
    for r in rows:
        pid = str(r.get(id_col, "")).strip()
        info = lookup.get(pid) if lookup else None
        if info:
            mapped_rows += 1
            for c in ["first_name", "second_name", "position"]:
                current = str(r.get(c, "") or "").strip()
                mapped = info.get(c, "")
                r[c] = mapped if mapped else current

        map_row = mapping_lookup.get(pid) if mapping_lookup else None
        if map_row:
            mapping_rows += 1
            for c in mapping_columns:
                current = str(r.get(c, "") or "").strip()
                mapped = str(map_row.get(c, "") or "").strip()
                r[c] = mapped if mapped else current

    return rows, columns, mapped_rows, mapping_rows


def clean_file(
    input_path: Path,
    output_path: Path,
    lookup_2425: dict[str, dict[str, str]],
    lookup_2526: dict[str, dict[str, str]],
    mapping_2425: dict[str, dict[str, str]],
    mapping_cols_2425: list[str],
    mapping_2526: dict[str, dict[str, str]],
    mapping_cols_2526: list[str],
) -> dict[str, Any]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]

    before_rows = len(rows)
    before_cols = len(columns)

    # Drop fully empty rows.
    rows = [r for r in rows if not _row_all_missing(r, columns)]

    # Drop fully empty columns.
    non_empty_cols = [c for c in columns if any(not _is_missing(r.get(c)) for r in rows)]
    dropped_empty_cols = [c for c in columns if c not in non_empty_cols]
    rows = [{c: r.get(c, "") for c in non_empty_cols} for r in rows]
    columns = non_empty_cols

    required_cols = _required_columns_for_file(input_path.name, columns)
    required_present = [c for c in required_cols if c in columns]

    # Drop rows missing required identifiers.
    rows = [
        r
        for r in rows
        if all(not _is_missing(r.get(c)) for c in required_present)
    ]

    # Drop almost-empty columns (except protected metadata).
    protected_cols = set(required_cols) | {"finished", "kickoff_time", "source"}
    missing_ratio = _compute_missing_ratio(rows, columns)
    sparse_drop = [
        c
        for c in columns
        if missing_ratio.get(c, 1.0) >= ALMOST_EMPTY_COL_THRESHOLD and c not in protected_cols
    ]

    kept_cols = [c for c in columns if c not in sparse_drop]
    rows = [{c: r.get(c, "") for c in kept_cols} for r in rows]
    columns = kept_cols

    # Sort to keep deterministic output.
    sort_priority = ["season", "gameweek", "match_id", "team", "id", "player_id"]
    sort_cols = [c for c in sort_priority if c in columns]

    def sort_key(row: dict[str, str]) -> tuple:
        key = []
        for c in sort_cols:
            v = row.get(c, "")
            if c == "gameweek":
                try:
                    key.append((0, int(float(v))))
                except Exception:
                    key.append((1, str(v)))
            else:
                key.append((0, str(v)))
        return tuple(key)

    if sort_cols:
        rows.sort(key=sort_key)

    rows, columns, mapped_rows, mapping_rows = _enrich_player_rows(
        rows=rows,
        columns=columns,
        filename=input_path.name,
        lookup_2425=lookup_2425,
        lookup_2526=lookup_2526,
        mapping_2425=mapping_2425,
        mapping_cols_2425=mapping_cols_2425,
        mapping_2526=mapping_2526,
        mapping_cols_2526=mapping_cols_2526,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    after_rows = len(rows)
    after_cols = len(columns)

    return {
        "file": input_path.name,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "rows_before": before_rows,
        "rows_after": after_rows,
        "rows_dropped": before_rows - after_rows,
        "cols_before": before_cols,
        "cols_after": after_cols,
        "cols_removed": max(0, before_cols - after_cols),
        "cols_added": max(0, after_cols - before_cols),
        "empty_columns_dropped": dropped_empty_cols,
        "required_columns_used": required_present,
        "sparse_columns_dropped": sparse_drop,
        "player_identity_rows_mapped": mapped_rows,
        "player_team_mapping_rows_mapped": mapping_rows,
    }


def run(input_dir: Path, output_dir: Path, report_path: Path) -> None:
    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in: {input_dir}")

    lookup_2425 = _load_player_lookup(input_dir / "players0.csv")
    lookup_2526 = _load_player_lookup(input_dir / "players.csv")
    mapping_2425, mapping_cols_2425 = _load_mapping_lookup(
        input_dir / "2024-2025_player_team_mapping.csv"
    )
    mapping_2526, mapping_cols_2526 = _load_mapping_lookup(
        input_dir / "2025-2026_player_team_mapping.csv"
    )

    results = []
    for csv_file in csv_files:
        if csv_file.name in {
            "players0.csv",
            "players.csv",
            "2024-2025_player_team_mapping.csv",
            "2025-2026_player_team_mapping.csv",
        }:
            continue
        out_file = output_dir / csv_file.name.replace(".csv", "_clean.csv")
        results.append(
            clean_file(
                input_path=csv_file,
                output_path=out_file,
                lookup_2425=lookup_2425,
                lookup_2526=lookup_2526,
                mapping_2425=mapping_2425,
                mapping_cols_2425=mapping_cols_2425,
                mapping_2526=mapping_2526,
                mapping_cols_2526=mapping_cols_2526,
            )
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"Processed {len(results)} files.")
    print(f"Cleaned CSVs written to: {output_dir}")
    print(f"Report written to: {report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean CSVs in the data folder.")
    parser.add_argument("--input-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/processed/preprocessing_report.json"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.input_dir, args.output_dir, args.report)
