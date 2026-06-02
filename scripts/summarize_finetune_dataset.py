#!/usr/bin/env python3
"""Summarize raw extraction records used for Qwen SFT."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "finetune"
OUTPUT = DATA_DIR / "dataset_summary.json"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def profile(records: list[dict[str, Any]]) -> dict[str, Any]:
    def input_count(pattern: str) -> int:
        return sum(
            bool(re.search(pattern, row["input_masked"], flags=re.IGNORECASE))
            for row in records
        )

    def null_count(field: str) -> int:
        return sum(
            row["response"]["address_info"].get(field) is None for row in records
        )

    return {
        "records": len(records),
        "unique_records": len({canonical(row) for row in records}),
        "duplicate_rows": len(records) - len({canonical(row) for row in records}),
        "masked_phone_records": sum(
            "[PHONE]" in row["input_masked"] for row in records
        ),
        "recipient_name_null": sum(
            row["response"].get("recipient_name") is None for row in records
        ),
        "note_null": sum(row["response"].get("note") is None for row in records),
        "address_raw_null": sum(
            row["response"].get("address_raw") is None for row in records
        ),
        "x_dot_or_space_inputs": input_count(r"\bx(?:\.|\s)"),
        "h_dot_or_space_inputs": input_count(r"\bh(?:\.|\s)"),
        "p_dot_or_space_inputs": input_count(r"\bp(?:\.|\s)"),
        "q_dot_or_space_inputs": input_count(r"\bq(?:\.|\s)"),
        "neighborhood_null": null_count("neighborhood"),
        "municipality_null": null_count("municipality"),
        "sub_region_null": null_count("sub_region"),
        "street_null": null_count("street"),
        "address_number_null": null_count("address_number"),
    }


def main() -> None:
    train = load_jsonl(DATA_DIR / "records_train.jsonl")
    valid = load_jsonl(DATA_DIR / "records_valid.jsonl")
    train_keys = {canonical(row) for row in train}
    valid_keys = {canonical(row) for row in valid}
    summary = {
        "source": "synthetic_train.jsonl",
        "split": {
            "train_ratio": round(len(train) / (len(train) + len(valid)), 4),
            "valid_ratio": round(len(valid) / (len(train) + len(valid)), 4),
            "cross_split_overlap": len(train_keys & valid_keys),
        },
        "schema": {
            "response_fields": [
                "recipient_name",
                "phone_number",
                "note",
                "address_raw",
                "address_info",
            ],
            "address_info_fields": [
                "address_number",
                "street",
                "neighborhood",
                "municipality",
                "sub_region",
                "country",
            ],
            "address_new_in_sft": False,
        },
        "train_profile": profile(train),
        "valid_profile": profile(valid),
    }
    OUTPUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
