# Clipboard Parsing & Smart Order API

MVP hiện tại tập trung vào text input, SLM extraction và chuẩn hóa địa giới sau sáp nhập.
Geocoding và OCR đang được để sau.

## Chạy API

```bash
/home/vantoan/anaconda3/envs/rag/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoint chính

### `POST /parse-text`

Input:

```json
{
  "text": "chị Lan 0909123456 giao 15 Lũy Bán Bích, Tân Quý, Tân Phú, HCM gọi trước",
  "use_llm": true
}
```

Output trả về đơn hàng đã chuẩn hóa:

```json
{
  "name": "chị Lan",
  "phone": "0909123456",
  "note": "gọi trước",
  "address": {
    "province": "Thành Phố Hồ Chí Minh",
    "ward": "Phường Phú Thọ Hòa",
    "street": "đường Lũy Bán Bích",
    "house_number": "15"
  }
}
```

### `POST /normalize-address`

Dùng để test riêng DB địa giới khi chưa bật Qwen:

```json
{
  "province": "Hồ Chí Minh",
  "district_hint": "Tân Phú",
  "ward": "Tân Quý",
  "street": "Lũy Bán Bích",
  "house_number": "15"
}
```

## Cấu hình Colab/Qwen

Nếu Colab expose Ollama qua ngrok/cloudflared:

```env
LLM_PROVIDER=ollama
LLM_BASE_URL=https://your-colab-url
LLM_MODEL=qwen2.5:7b
```

Nếu Colab chạy vLLM/OpenAI-compatible server:

```env
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://your-colab-url
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
```

## Ghi chú chuẩn hóa

Matcher ưu tiên theo thứ tự:

1. Tỉnh/thành phố cũ hoặc mới.
2. Quận/huyện cũ nếu có trong input.
3. Xã/phường cũ hoặc mới.

Nếu một xã/phường cũ bị tách sang nhiều phường/xã mới, API trả `ambiguous_admin_match`
và giữ danh sách `candidates` để giao diện cho người dùng chọn.

## Benchmark 3B vs 7B

Dataset benchmark:

```bash
data/benchmark_orders_200.jsonl
```

Chạy API:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Chạy benchmark tuần tự để đo latency khách quan:

```bash
python scripts/run_benchmark.py \
  --api-url http://127.0.0.1:8000 \
  --input data/benchmark_orders_200.jsonl \
  --output-dir benchmark_results/qwen25_3b \
  --model-name qwen2.5:3b \
  --warmup 5 \
  --concurrency 1
```

Sau khi đổi `.env` sang `qwen2.5:7b` và restart API, chạy:

```bash
python scripts/run_benchmark.py \
  --api-url http://127.0.0.1:8000 \
  --input data/benchmark_orders_200.jsonl \
  --output-dir benchmark_results/qwen25_7b \
  --model-name qwen2.5:7b \
  --warmup 5 \
  --concurrency 1
```

Script sẽ lưu:

- `*_summary.json`: latency mean/P50/P95/P99, throughput, exact match, accuracy từng field.
- `*_predictions.jsonl`: input, expected, prediction, latency từng mẫu.
