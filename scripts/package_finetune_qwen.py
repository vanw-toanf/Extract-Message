#!/usr/bin/env python3
"""Package extraction records as Qwen-compatible chat JSONL for SFT."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = ROOT / "data" / "finetune"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "finetune" / "qwen_sft"

SYSTEM_PROMPT = """Bạn là bộ trích xuất đơn giao hàng Việt Nam.
Chỉ trả về đúng một JSON hợp lệ theo schema đã học, không giải thích.
Số điện thoại hợp lệ đã được thay bằng [PHONE]. Không khôi phục số thật.
Không bịa dữ liệu thiếu. Trường không có hoặc không chắc chắn phải là null.
address_raw giữ nguyên phần địa chỉ trong input.
address_info chỉ mô tả các thành phần địa chỉ thô có trong input, chưa chuẩn hóa địa giới.
Với địa chỉ cũ 3 cấp: neighborhood=xã/phường cũ, municipality=huyện/quận cũ, sub_region=tỉnh/thành cũ.
Với địa chỉ mới 2 cấp: neighborhood=null, municipality=xã/phường mới, sub_region=tỉnh/thành mới.
country là VNM khi có địa chỉ, nếu không có địa chỉ thì null."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def package_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": record["input_masked"]},
            {
                "role": "assistant",
                "content": json.dumps(
                    record["response"], ensure_ascii=False, separators=(",", ":")
                ),
            },
        ]
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    for split in ("train", "valid"):
        source = args.input_dir / f"records_{split}.jsonl"
        output = args.output_dir / f"{split}.jsonl"
        records = [package_record(record) for record in load_jsonl(source)]
        write_jsonl(output, records)
        print(f"Wrote {len(records)} records to {output}")


if __name__ == "__main__":
    main()
