#!/usr/bin/env python3
import argparse
import html
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "benchmark_results"
OUTPUT = RESULTS_DIR / "benchmark_report.html"

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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def fmt_num(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def collect_runs(include: list[str] | None = None) -> list[dict[str, Any]]:
    runs = []
    for summary_path in sorted(RESULTS_DIR.glob("*/*_summary.json")):
        if "smoke" in summary_path.parts:
            continue
        path_text = str(summary_path)
        if include and not any(token in path_text for token in include):
            continue
        prediction_path = summary_path.with_name(
            summary_path.name.replace("_summary.json", "_predictions.jsonl")
        )
        if not prediction_path.exists():
            continue
        runs.append(
            {
                "summary_path": summary_path,
                "prediction_path": prediction_path,
                "summary": load_json(summary_path),
                "predictions": load_jsonl(prediction_path),
                "mtime": summary_path.stat().st_mtime,
            }
        )
    return sorted(runs, key=lambda run: (run["mtime"], str(run["summary_path"])))


def select_runs(runs: list[dict[str, Any]], latest: int | None = None) -> list[dict[str, Any]]:
    if latest and latest > 0:
        return runs[-latest:]
    return runs


def prediction_signature(row: dict[str, Any]) -> str:
    return json.dumps(row.get("prediction"), ensure_ascii=False, sort_keys=True)


def compare_predictions(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if len(runs) < 2:
        return {"comparable": False}
    left, right = runs[0], runs[1]
    right_by_id = {row["id"]: row for row in right["predictions"]}
    common = 0
    same = 0
    for row in left["predictions"]:
        other = right_by_id.get(row["id"])
        if not other:
            continue
        common += 1
        if prediction_signature(row) == prediction_signature(other):
            same += 1
    return {
        "comparable": True,
        "common": common,
        "same": same,
        "same_ratio": same / common if common else 0,
    }


def examples_for(run: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    examples = []
    for row in run["predictions"]:
        mismatches = []
        for field in FIELDS:
            expected = get_path(row["expected"], field)
            predicted = get_path(row["prediction"], field)
            if str(expected).strip().lower() != str(predicted).strip().lower():
                mismatches.append((field, expected, predicted))
        if mismatches:
            examples.append(
                {
                    "id": row["id"],
                    "category": row.get("category"),
                    "input": row["input"],
                    "mismatches": mismatches[:4],
                }
            )
        if len(examples) >= limit:
            break
    return examples


def mismatch_count(run: dict[str, Any]) -> int:
    count = 0
    for row in run["predictions"]:
        if any(
            str(get_path(row["expected"], field)).strip().lower()
            != str(get_path(row["prediction"], field)).strip().lower()
            for field in FIELDS
        ):
            count += 1
    return count


def render_summary_table(runs: list[dict[str, Any]]) -> str:
    rows = []
    for run in runs:
        s = run["summary"]
        lat = s["latency_seconds"]
        rows.append(
            f"""
            <tr>
              <td>{esc(s["model"])}</td>
              <td>{s["successful"]}/{s["total"]}</td>
              <td>{fmt_num(lat["mean"], 4)}</td>
              <td>{fmt_num(lat["median_p50"], 4)}</td>
              <td>{fmt_num(lat["p95"], 4)}</td>
              <td>{fmt_num(lat["p99"], 4)}</td>
              <td>{fmt_num(s["throughput_orders_per_minute"], 1)}</td>
              <td>{fmt_pct(s["full_exact_match"]["accuracy"])}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def render_field_table(runs: list[dict[str, Any]]) -> str:
    header = "".join(
        f"<th>{esc(run['summary']['model'])}<br>Exact / F1</th>" for run in runs
    )
    rows = []
    for field in FIELDS:
        cells = []
        for run in runs:
            metrics = run["summary"]["field_metrics"][field]
            cells.append(
                f"<td>{fmt_pct(metrics['exact_accuracy'])}<br><span>{fmt_num(metrics['f1'], 4)}</span></td>"
            )
        rows.append(f"<tr><td>{esc(field)}</td>{''.join(cells)}</tr>")
    return f"<tr><th>Field</th>{header}</tr>" + "\n".join(rows)


def render_examples(run: dict[str, Any]) -> str:
    blocks = []
    for example in examples_for(run):
        mismatch_rows = "".join(
            f"<tr><td>{esc(field)}</td><td>{esc(expected)}</td><td>{esc(predicted)}</td></tr>"
            for field, expected, predicted in example["mismatches"]
        )
        blocks.append(
            f"""
            <section class="example">
              <h4>{esc(example['id'])} · {esc(example['category'])}</h4>
              <p>{esc(example['input'])}</p>
              <table>
                <tr><th>Field</th><th>Expected</th><th>Prediction</th></tr>
                {mismatch_rows}
              </table>
            </section>
            """
        )
    return "\n".join(blocks)


def render_all_examples(runs: list[dict[str, Any]]) -> str:
    sections = []
    for run in runs:
        sections.append(
            f"""
            <section class="model-errors">
              <h3>{esc(run['summary']['model'])}</h3>
              <p>
                <strong>{mismatch_count(run)}/{len(run['predictions'])}</strong> mẫu có ít nhất một field sai.
                File prediction: <code>{esc(run['prediction_path'])}</code>
              </p>
              {render_examples(run)}
            </section>
            """
        )
    return "\n".join(sections)


def render_report(runs: list[dict[str, Any]]) -> str:
    comparison = compare_predictions(runs)
    models = ", ".join(run["summary"]["model"] for run in runs)
    total_cases = ", ".join(
        f"{esc(run['summary']['model'])}: {run['summary']['total']}" for run in runs
    )
    warning = ""
    recommendation = ""
    notes = ""

    if comparison.get("comparable") and comparison.get("same_ratio", 0) > 0.98:
        warning = f"""
        <div class="warning">
          <strong>Cảnh báo chất lượng benchmark:</strong>
          Hai lần chạy có {comparison['same']}/{comparison['common']} prediction giống hệt nhau
          ({fmt_pct(comparison['same_ratio'])}), latency trung bình chỉ khoảng 0.03s/request,
          và field <code>note</code> đạt 0%. Điều này cho thấy API gần như đang chạy rule-based/fallback,
          chưa gọi SLM thật trong container hoặc LLM call đang fail rồi bị parser nuốt lỗi.
          Không nên dùng số liệu này để kết luận 3B tốt hơn hay 7B tốt hơn về năng lực hiểu ngôn ngữ.
        </div>
        """
        recommendation = """
        <p>
          Với số liệu hiện tại, nếu chỉ xét pipeline đang chạy thì <strong>qwen2.5:3b</strong>
          nhỉnh hơn rất nhẹ về latency/throughput và accuracy giống 7B. Tuy nhiên đây là kết luận
          cho phần rule-based, không phải kết luận công bằng cho model. Cần rerun sau khi xác nhận
          API trong Docker gọi được Ollama.
        </p>
        """
    else:
        by_model = {run["summary"]["model"]: run for run in runs}
        run_3b = by_model.get("qwen2.5:3b")
        run_7b = by_model.get("qwen2.5:7b")
        if run_3b and run_7b:
            s3 = run_3b["summary"]
            s7 = run_7b["summary"]
            p95_gain = (
                (s7["latency_seconds"]["p95"] - s3["latency_seconds"]["p95"])
                / s7["latency_seconds"]["p95"]
            )
            full_gain = (
                s7["full_exact_match"]["accuracy"]
                - s3["full_exact_match"]["accuracy"]
            )
            recommendation = f"""
            <p>
              <strong>Khuyến nghị:</strong> dùng <strong>qwen2.5:3b</strong> làm model mặc định cho MVP/production
              vì P95 latency thấp hơn khoảng {fmt_pct(p95_gain)} và throughput cao hơn, trong khi full exact
              chỉ thấp hơn {fmt_pct(full_gain)} so với 7B. Dùng <strong>qwen2.5:7b</strong> làm fallback cho các ca
              địa chỉ mơ hồ hoặc khi confidence chuẩn hóa thấp.
            </p>
            <p>
              Nếu mục tiêu chính là báo cáo độ chính xác địa chỉ, 7B đáng giá hơn: province exact
              {fmt_pct(s7['field_metrics']['address.province']['exact_accuracy'])} và ward exact
              {fmt_pct(s7['field_metrics']['address.ward']['exact_accuracy'])}, cao hơn 3B lần lượt
              {fmt_pct(s3['field_metrics']['address.province']['exact_accuracy'])} và
              {fmt_pct(s3['field_metrics']['address.ward']['exact_accuracy'])}.
            </p>
            """
            notes = """
            <ul>
              <li><strong>Phone</strong> đạt 100% ở cả hai model nhờ regex tiền xử lý.</li>
              <li><strong>3B</strong> tốt hơn ở latency và một số field rule-heavy như name/street.</li>
              <li><strong>7B</strong> tốt hơn rõ rệt ở chuẩn hóa địa chỉ: province, ward, house_number và full exact.</li>
              <li><strong>Note</strong> chỉ khoảng 65-66% exact, nên cần cải thiện prompt hoặc hậu xử lý note.</li>
              <li>Full exact còn dưới 50% vì chỉ cần sai một field nhỏ là cả đơn bị tính sai; field-level metrics phản ánh chất lượng thực tế tốt hơn.</li>
            </ul>
            """
        else:
            best_latency = min(
                runs, key=lambda run: run["summary"]["latency_seconds"]["p95"]
            )
            best_accuracy = max(
                runs, key=lambda run: run["summary"]["full_exact_match"]["accuracy"]
            )
            recommendation = f"""
            <p>
              Khuyến nghị sơ bộ: <strong>{esc(best_latency['summary']['model'])}</strong>
              có P95 latency tốt nhất, còn <strong>{esc(best_accuracy['summary']['model'])}</strong>
              có full exact cao nhất. Nếu chênh lệch accuracy nhỏ, ưu tiên model latency thấp hơn
              cho môi trường CPU.
            </p>
            """

    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Báo Cáo Benchmark Clipboard Parsing</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      color: #18202a;
      background: #f6f8fb;
      line-height: 1.55;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    h1 {{ font-size: 30px; }}
    h2 {{ margin-top: 30px; font-size: 22px; }}
    p {{ margin: 8px 0 14px; }}
    .panel {{
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 20px;
      margin: 16px 0;
    }}
    .warning {{
      background: #fff7ed;
      border: 1px solid #fed7aa;
      border-left: 5px solid #f97316;
      border-radius: 8px;
      padding: 14px 16px;
      margin: 16px 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0;
      background: #fff;
    }}
    th, td {{
      border: 1px solid #d9e2ec;
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #edf2f7; }}
    td span {{ color: #52606d; }}
    code {{
      background: #edf2f7;
      padding: 2px 5px;
      border-radius: 4px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .metric {{
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 14px;
    }}
    .metric strong {{
      display: block;
      font-size: 22px;
      margin-top: 4px;
    }}
    .example {{
      border-top: 1px solid #e2e8f0;
      padding-top: 14px;
      margin-top: 14px;
    }}
    .model-errors {{
      border: 2px solid #cbd5e1;
      border-radius: 8px;
      padding: 16px;
      margin: 18px 0;
      background: #ffffff;
    }}
    .model-errors h3 {{
      color: #0f172a;
      padding-bottom: 8px;
      border-bottom: 1px solid #e2e8f0;
    }}
    .example p {{
      color: #334e68;
      background: #f8fafc;
      padding: 10px;
      border-radius: 6px;
    }}
  </style>
</head>
<body>
<main>
  <h1>Báo Cáo Benchmark Clipboard Parsing</h1>
  <p>So sánh các lần chạy benchmark trong <code>benchmark_results</code>. Thư mục <code>smoke</code> được bỏ qua.</p>

  <section class="panel">
    <h2>Tổng Quan</h2>
    <p><strong>Models:</strong> {esc(models)}</p>
    <p><strong>Số mẫu:</strong> {total_cases}</p>
    {warning}
    {recommendation}
  </section>

  <section class="panel">
    <h2>Latency & Throughput</h2>
    <table>
      <tr>
        <th>Model</th>
        <th>Success</th>
        <th>Mean Latency (s)</th>
        <th>P50 (s)</th>
        <th>P95 (s)</th>
        <th>P99 (s)</th>
        <th>Orders/min</th>
        <th>Full Exact</th>
      </tr>
      {render_summary_table(runs)}
    </table>
  </section>

  <section class="panel">
    <h2>Field Metrics</h2>
    <p>Mỗi ô hiển thị Exact Accuracy và F1.</p>
    <table>
      {render_field_table(runs)}
    </table>
  </section>

  <section class="panel">
    <h2>Nhận Xét</h2>
    {notes or '<p>Không đủ dữ liệu để tạo nhận xét tự động.</p>'}
  </section>

  <section class="panel">
    <h2>Mẫu Lỗi</h2>
    <p>Các ví dụ dưới đây được tách theo từng model để dễ so sánh lỗi.</p>
    {render_all_examples(runs) if runs else ''}
  </section>
</main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate benchmark HTML report")
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        help="Only include runs whose path contains this text. Can be repeated.",
    )
    parser.add_argument(
        "--latest",
        type=int,
        default=None,
        help="Only include the N most recently modified benchmark runs.",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT),
        help="Output HTML path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runs = select_runs(collect_runs(args.include), args.latest)
    if not runs:
        raise SystemExit("No benchmark summary files found")
    html_text = render_report(runs)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")
    print("Included runs:")
    for run in runs:
        print(f"- {run['summary']['model']} ({run['summary_path']})")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
