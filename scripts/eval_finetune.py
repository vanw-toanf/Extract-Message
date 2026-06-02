#!/usr/bin/env python3
"""
Evaluate finetuned model on valid set.
Chạy sau khi merge LoRA xong (dùng merged HuggingFace model).

Usage:
    python eval_finetune.py --model ../../output/qwen25_7b_merged
    python eval_finetune.py --model ../../output/qwen25_7b_merged --limit 50
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
VALID_FILE = ROOT / "data" / "finetune" / "records_valid.jsonl"

SYSTEM_PROMPT = """Bạn là bộ trích xuất đơn giao hàng Việt Nam.
Chỉ trả về đúng một JSON hợp lệ theo schema đã học, không giải thích.
Số điện thoại hợp lệ đã được thay bằng [PHONE]. Không khôi phục số thật.
Không bịa dữ liệu thiếu. Trường không có hoặc không chắc chắn phải là null.
address_raw giữ nguyên phần địa chỉ trong input.
address_info chỉ mô tả các thành phần địa chỉ thô có trong input, chưa chuẩn hóa địa giới.
Với địa chỉ cũ 3 cấp: neighborhood=xã/phường cũ, municipality=huyện/quận cũ, sub_region=tỉnh/thành cũ.
Với địa chỉ mới 2 cấp: neighborhood=null, municipality=xã/phường mới, sub_region=tỉnh/thành mới.
country là VNM khi có địa chỉ, nếu không có địa chỉ thì null."""

# Flat list of fields to evaluate (dot-notation for nested)
FIELDS = [
    "recipient_name",
    "phone_number",
    "note",
    "address_raw",
    "address_info.address_number",
    "address_info.street",
    "address_info.neighborhood",
    "address_info.municipality",
    "address_info.sub_region",
    "address_info.country",
]


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def get_field(obj: dict, dotpath: str) -> Any:
    parts = dotpath.split(".")
    cur = obj
    for p in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def run_inference(model, tokenizer, user_text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    new_tokens = output_ids[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def parse_json_safe(text: str) -> dict | None:
    # Tìm JSON block trong response nếu model thêm text thừa
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def normalize(val: Any) -> str | None:
    """Chuẩn hóa để so sánh: lowercase, strip spaces."""
    if val is None:
        return None
    return str(val).strip().lower()


def evaluate(records: list[dict], model, tokenizer) -> dict:
    total = len(records)
    json_valid = 0

    field_correct: dict[str, int] = {f: 0 for f in FIELDS}
    field_total: dict[str, int] = {f: 0 for f in FIELDS}
    null_hallucinated: dict[str, int] = {f: 0 for f in FIELDS}  # pred not null, truth null
    null_missed: dict[str, int] = {f: 0 for f in FIELDS}        # pred null, truth not null

    errors: list[dict] = []

    for i, record in enumerate(records):
        user_text = record["input_masked"]
        truth = record["response"]

        raw_output = run_inference(model, tokenizer, user_text)
        pred = parse_json_safe(raw_output)

        if pred is None:
            errors.append({"i": i, "input": user_text, "output": raw_output, "error": "invalid_json"})
            print(f"[{i+1}/{total}] INVALID JSON")
            continue

        json_valid += 1

        for field in FIELDS:
            t_val = normalize(get_field(truth, field))
            p_val = normalize(get_field(pred, field))
            field_total[field] += 1

            if t_val == p_val:
                field_correct[field] += 1
            elif t_val is None and p_val is not None:
                null_hallucinated[field] += 1
            elif t_val is not None and p_val is None:
                null_missed[field] += 1

        if (i + 1) % 50 == 0:
            print(f"[{i+1}/{total}] json_valid so far: {json_valid}/{i+1}")

    results = {
        "total": total,
        "json_valid": json_valid,
        "json_valid_rate": json_valid / total,
        "fields": {},
    }

    for field in FIELDS:
        denom = field_total[field] or 1
        results["fields"][field] = {
            "exact_match": field_correct[field] / denom,
            "correct": field_correct[field],
            "hallucinated_nulls": null_hallucinated[field],
            "missed_nulls": null_missed[field],
            "total": field_total[field],
        }

    if errors:
        results["sample_errors"] = errors[:5]

    return results


def print_report(results: dict) -> None:
    print("\n" + "=" * 60)
    print(f"Total samples  : {results['total']}")
    print(f"JSON valid     : {results['json_valid']} ({results['json_valid_rate']:.1%})")
    print("-" * 60)
    print(f"{'Field':<35} {'Exact':>7}  {'Halluc':>7}  {'Missed':>7}")
    print("-" * 60)
    for field, m in results["fields"].items():
        print(
            f"{field:<35} {m['exact_match']:>7.1%}  "
            f"{m['hallucinated_nulls']:>7}  {m['missed_nulls']:>7}"
        )
    print("=" * 60)

    # Overall micro average
    total_correct = sum(m["correct"] for m in results["fields"].values())
    total_fields = sum(m["total"] for m in results["fields"].values())
    print(f"Overall field accuracy: {total_correct/total_fields:.1%} ({total_correct}/{total_fields})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Path to merged HF model dir")
    parser.add_argument("--valid", type=Path, default=VALID_FILE)
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only first N records")
    parser.add_argument("--output", type=Path, default=None, help="Save full results JSON")
    args = parser.parse_args()

    print(f"Loading model from {args.model} ...")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()
    print("Model loaded.")

    records = load_jsonl(args.valid)
    if args.limit:
        records = records[: args.limit]
    print(f"Evaluating on {len(records)} records from {args.valid.name} ...")

    results = evaluate(records, model, tokenizer)
    print_report(results)

    if args.output:
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\nFull results saved to {args.output}")


if __name__ == "__main__":
    main()
