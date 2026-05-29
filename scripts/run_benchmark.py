#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import math
import statistics
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests


FIELDS = [
    "name",
    "phone",
    "note",
    "address.province",
    "address.ward",
    "address.street",
    "address.house_number",
]


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = " ".join(text.split())
    return text


def get_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * pct / 100
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return values[int(rank)]
    return values[lower] * (upper - rank) + values[upper] * (rank - lower)


def token_f1(expected: Any, predicted: Any) -> float:
    exp = normalize_text(expected).split()
    pred = normalize_text(predicted).split()
    if not exp and not pred:
        return 1.0
    if not exp or not pred:
        return 0.0

    exp_counts: dict[str, int] = {}
    for token in exp:
        exp_counts[token] = exp_counts.get(token, 0) + 1

    overlap = 0
    for token in pred:
        if exp_counts.get(token, 0) > 0:
            overlap += 1
            exp_counts[token] -= 1

    if overlap == 0:
        return 0.0
    precision = overlap / len(pred)
    recall = overlap / len(exp)
    return 2 * precision * recall / (precision + recall)


def call_parse(api_url: str, row: dict[str, Any], timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = requests.post(
            api_url.rstrip("/") + "/parse-text",
            json={"text": row["input"], "use_llm": True},
            timeout=timeout,
        )
        elapsed = time.perf_counter() - started
        status_code = response.status_code
        try:
            prediction = response.json()
        except Exception:
            prediction = {"error": response.text}
        ok = response.ok
    except Exception as exc:
        elapsed = time.perf_counter() - started
        status_code = None
        prediction = {"error": f"{type(exc).__name__}: {exc}"}
        ok = False

    return {
        "id": row["id"],
        "category": row.get("category"),
        "latency_seconds": elapsed,
        "ok": ok,
        "status_code": status_code,
        "input": row["input"],
        "expected": row["expected"],
        "prediction": prediction,
    }


def score_results(results: list[dict[str, Any]], model_name: str) -> dict[str, Any]:
    successful = [row for row in results if row["ok"]]
    latencies = [row["latency_seconds"] for row in successful]

    field_summary: dict[str, Any] = {}
    for field in FIELDS:
        total = 0
        exact = 0
        tp = fp = fn = 0
        f1_scores = []

        for row in successful:
            expected = get_path(row["expected"], field)
            predicted = get_path(row["prediction"], field)
            exp_norm = normalize_text(expected)
            pred_norm = normalize_text(predicted)
            total += 1

            if exp_norm == pred_norm:
                exact += 1
                if exp_norm:
                    tp += 1
            else:
                if pred_norm:
                    fp += 1
                if exp_norm:
                    fn += 1

            f1_scores.append(token_f1(expected, predicted))

        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

        field_summary[field] = {
            "exact_accuracy": round(exact / total, 4) if total else 0.0,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "token_f1_avg": round(statistics.mean(f1_scores), 4) if f1_scores else 0.0,
            "exact_count": exact,
            "total": total,
        }

    full_exact = 0
    for row in successful:
        if all(
            normalize_text(get_path(row["expected"], field))
            == normalize_text(get_path(row["prediction"], field))
            for field in FIELDS
        ):
            full_exact += 1

    return {
        "model": model_name,
        "total": len(results),
        "successful": len(successful),
        "failed": len(results) - len(successful),
        "latency_seconds": {
            "mean": round(statistics.mean(latencies), 4) if latencies else 0.0,
            "median_p50": round(percentile(latencies, 50), 4),
            "p95": round(percentile(latencies, 95), 4),
            "p99": round(percentile(latencies, 99), 4),
            "min": round(min(latencies), 4) if latencies else 0.0,
            "max": round(max(latencies), 4) if latencies else 0.0,
        },
        "throughput_orders_per_minute": round(
            len(successful) / sum(latencies) * 60, 4
        )
        if latencies and sum(latencies) > 0
        else 0.0,
        "full_exact_match": {
            "accuracy": round(full_exact / len(successful), 4) if successful else 0.0,
            "exact_count": full_exact,
            "total": len(successful),
        },
        "field_metrics": field_summary,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--input", default="data/benchmark_orders_200.jsonl")
    parser.add_argument("--output-dir", default="benchmark_results")
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=3)
    args = parser.parse_args()

    rows = load_jsonl(Path(args.input))
    if args.limit:
        rows = rows[: args.limit]

    for row in rows[: args.warmup]:
        call_parse(args.api_url, row, args.timeout)

    started = time.perf_counter()
    if args.concurrency <= 1:
        results = [call_parse(args.api_url, row, args.timeout) for row in rows]
    else:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.concurrency
        ) as executor:
            futures = [
                executor.submit(call_parse, args.api_url, row, args.timeout)
                for row in rows
            ]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
            results.sort(key=lambda row: row["id"])
    wall_seconds = time.perf_counter() - started

    summary = score_results(results, args.model_name)
    summary["wall_seconds"] = round(wall_seconds, 4)
    summary["concurrency"] = args.concurrency
    summary["warmup"] = args.warmup

    safe_model_name = args.model_name.replace("/", "_").replace(":", "_")
    output_dir = Path(args.output_dir) / safe_model_name
    write_jsonl(output_dir / f"{safe_model_name}_predictions.jsonl", results)
    write_json(output_dir / f"{safe_model_name}_summary.json", summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
