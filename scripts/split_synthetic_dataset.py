#!/usr/bin/env python3
"""Split synthetic JSONL records into deterministic train and validation sets."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import random
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "finetune" / "synthetic_train.jsonl"
DEFAULT_TRAIN = ROOT / "data" / "finetune" / "synthetic_train_split.jsonl"
DEFAULT_VALID = ROOT / "data" / "finetune" / "synthetic_valid_split.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--train-output", type=Path, default=DEFAULT_TRAIN)
    parser.add_argument("--valid-output", type=Path, default=DEFAULT_VALID)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=20260601)
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    args = parse_args()
    if not 0 < args.train_ratio < 1:
        raise ValueError("--train-ratio must be between 0 and 1")

    rows = load_jsonl(args.input)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        grouped[key].append(row)

    groups = list(grouped.values())
    random.Random(args.seed).shuffle(groups)
    target_train_size = round(len(rows) * args.train_ratio)
    train: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    for group in groups:
        if len(train) + len(group) <= target_train_size:
            train.extend(group)
        else:
            valid.extend(group)

    write_jsonl(args.train_output, train)
    write_jsonl(args.valid_output, valid)
    print(f"Input: {len(rows)} records")
    print(f"Unique record groups: {len(groups)}")
    print(f"Train: {len(train)} records -> {args.train_output}")
    print(f"Valid: {len(valid)} records -> {args.valid_output}")


if __name__ == "__main__":
    main()
