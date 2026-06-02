#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmark_results" / "benchmark_errors.xlsx"

def _discover_runs() -> dict[str, Path]:
    results: dict[str, Path] = {}
    for p in sorted((ROOT / "benchmark_results").glob("*/*_predictions.jsonl")):
        if "smoke" in p.parts:
            continue
        results[p.parent.name] = p
    return results

RUNS = _discover_runs()

FIELDS = [
    "name",
    "phone",
    "note",
    "address.province",
    "address.ward",
    "address.street",
    "address.house_number",
]

FIELD_ALIASES = {
    "name": "recipient_name",
    "phone": "phone_number",
    "address.province": "address_info.sub_region",
    "address.ward": "address_info.municipality",
    "address.street": "address_info.street",
    "address.house_number": "address_info.address_number",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def get_path(data: dict[str, Any], path: str) -> Any:
    value = _get_path(data, path)
    if value is None and path in FIELD_ALIASES:
        return _get_path(data, FIELD_ALIASES[path])
    return value


def _get_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def norm(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def flatten_prediction(data: dict[str, Any]) -> dict[str, Any]:
    return {field: get_path(data, field) for field in FIELDS}


def error_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for item in load_jsonl(path):
        expected_flat = flatten_prediction(item["expected"])
        prediction_flat = flatten_prediction(item["prediction"])
        wrong_fields = [
            field
            for field in FIELDS
            if norm(expected_flat[field]) != norm(prediction_flat[field])
        ]
        if not wrong_fields:
            continue

        for field in wrong_fields:
            rows.append(
                {
                    "id": item["id"],
                    "category": item.get("category"),
                    "field": field,
                    "expected": expected_flat[field],
                    "prediction": prediction_flat[field],
                    "latency_seconds": round(item.get("latency_seconds", 0), 4),
                    "input": item["input"],
                    "expected_all": json.dumps(
                        item["expected"], ensure_ascii=False, sort_keys=True
                    ),
                    "prediction_all": json.dumps(
                        item["prediction"], ensure_ascii=False, sort_keys=True
                    ),
                }
            )
    return rows


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
        for sheet_name, path in RUNS.items():
            rows = error_rows(path)
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            ws = writer.sheets[sheet_name]
            ws.freeze_panes = "A2"
            widths = {
                "A": 12,
                "B": 12,
                "C": 24,
                "D": 34,
                "E": 34,
                "F": 16,
                "G": 90,
                "H": 90,
                "I": 90,
            }
            for column, width in widths.items():
                ws.column_dimensions[column].width = width
            ws.auto_filter.ref = ws.dimensions

    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
