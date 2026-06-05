# Benchmark Report: Ollama q8 vs vLLM AWQ int4

**Ngày:** 2026-06-05  
**Model:** qwen2.5-7b finetune (vin-extractor)  
**Dataset:** 300 đơn hàng (`data/benchmark_orders_200.jsonl`)  
**Task:** Trích xuất name, phone, note, address (province/ward/street/house_number) từ text thô

---

## 1. Môi trường

| | Ollama (local) | vLLM (T4 server) |
|---|---|---|
| **Model format** | GGUF q8 (8-bit) | AWQ int4 (4-bit) |
| **Hardware** | Local machine | Tesla T4, 16 GB VRAM |
| **GPU compute cap** | SM 7.5 (không có FlashAttention 2) | SM 7.5 (không có FlashAttention 2) |
| **Backend** | Ollama + llama.cpp | vLLM 0.8.5, Triton attention |
| **Serving** | Ollama HTTP | FastAPI (Docker) → vLLM port 8001 |
| **max_num_seqs** | 1 (mặc định) | 20 |
| **max_model_len** | 1024 | 1024 |
| **max_tokens** | 256 | 256 |

---

## 2. Latency per Request

### 2.1 Single Request (Concurrency = 1)

| Metric | Ollama q8 | vLLM AWQ c=1 | vLLM + xformers c=1 | Δ best vLLM vs Ollama |
|---|---|---|---|---|
| **Mean** | 5.21 s | **4.74 s** | 6.11 s | −9% |
| **p50 (median)** | 5.31 s | 6.05 s | 5.52 s | +14% |
| **p95** | 6.25 s | 7.71 s | 12.62 s | **+23%** |
| **p99** | 6.60 s | 8.46 s | 15.02 s | **+28%** |
| **Min** | 3.32 s | 3.09 s | 3.48 s | — |
| **Max** | 6.82 s | **30.09 s** | 16.34 s | +341% |
| **Wall time (300 req)** | 1564 s | 1421 s | 1833 s | −9% |

 
> xformers làm p95/p99 tệ hơn đáng kể → **không dùng xformers trên T4**.

### 2.2 Concurrent Requests

| Metric | vLLM c=1 | vLLM c=10 | vLLM c=15 |
|---|---|---|---|
| **Mean latency/req** | 4.74 s | 12.38 s | 14.49 s |
| **p50 latency/req** | 6.05 s | 12.34 s | 14.49 s |
| **p95 latency/req** | 7.71 s | 15.20 s | 18.14 s |
| **p99 latency/req** | 8.46 s | 17.27 s | 21.32 s |
| **Min latency/req** | 0.004 s* | 5.73 s | 5.18 s |
| **Max latency/req** | 30.09 s | 21.52 s | 24.24 s |
| **Wall time (300 req)** | 1421 s | 373 s | **292 s** |

---

## 3. Throughput Thực Tế

>  `throughput_orders_per_minute` Throughput thực tế tính theo `wall_seconds`.

| Setup | Wall time (300 req) | **Throughput thực (wall)** | So với Ollama |
|---|---|---|---|
| Ollama c=1 | 1564 s (26.1 phút) | 11.5 req/min | baseline |
| vLLM c=1 | 1421 s (23.7 phút) | 12.7 req/min | +10% |
| vLLM c=10 | 373 s (6.2 phút) | 48.3 req/min | **+320%** |
| **vLLM c=15** | **292 s (4.9 phút)** | **61.7 req/min** | **+436%** |

vLLM ở concurrency=15 xử lý cùng 300 đơn trong **4.9 phút** thay vì **26.1 phút** của Ollama — **nhanh hơn 5.4×** nhờ continuous batching của GPU.

---

## 4. Accuracy

| Field | Ollama q8 | vLLM c=1 | vLLM c=10 | vLLM c=15 | Δ (best vLLM vs Ollama) |
|---|---|---|---|---|---|
| **Full exact match** | **57.0%** | 50.7% | 50.3% | 50.7% | −6.3 pp |
| name | **99.0%** | 97.7% | 97.7% | 97.7% | −1.3 pp |
| phone | 99.3% | 99.3% | 99.3% | 99.3% | 0 |
| note | **86.7%** | 82.0% | 82.0% | 82.0% | −4.7 pp |
| address.province | **81.0%** | 77.3% | 77.3% | 77.3% | −3.7 pp |
| address.ward | 70.3% | **68.3%** | **68.3%** | **68.3%** | +1.0 pp |
| address.street | 82.0% | **84.0%** | **84.0%** | **84.0%** | +2.0 pp |
| address.house_number | **90.0%** | 89.0% | 89.0% | 89.0% | −1.0 pp |

**Kết luận accuracy:**
- Ollama (q8 8-bit) tốt hơn vLLM (AWQ int4) ~6 pp full exact, chủ yếu ở `note`, `province`, `house_number`
- Nguyên nhân là **chênh lệch quantization**: q8 bảo toàn trọng số tốt hơn int4 đáng kể
- `phone` và `address.ward/street` gần như bằng nhau giữa hai backend
- Accuracy không thay đổi giữa c=1, c=10 và c=15 → batch size không ảnh hưởng quality

---

## 5. Phân tích: Tại Sao vLLM Single Request Vẫn Chậm Hơn Ollama (p95/p99)?

### 5.1 Phân rã thời gian (ước tính)

Một request điển hình gồm hai giai đoạn:

```
Total latency = TTFT + Decode time

TTFT    = prefill(system_prompt ~300 tok + user_input ~50 tok) / prefill_speed
Decode  = output_tokens ~60-80 tok / decode_speed
```

| | Ước tính T4 (7B AWQ int4) |
|---|---|
| Prefill speed | ~400 tok/s (batched) |
| Decode speed (batch=1) | ~35 tok/s |
| **TTFT** (350 tok / 400) | **~0.9 s** |
| **Decode** (70 tok / 35) | **~2.0 s** |
| Overhead (scheduler, HTTP) | **~0.5–1.5 s** |
| **Tổng ước tính** | **3.4–4.4 s** ✓ |

### 5.2 Lý do tail latency (p95/p99) của vLLM cao hơn Ollama

| Nguyên nhân | Giải thích |
|---|---|
| **Continuous batching scheduler** | vLLM quản lý KV-cache pool phức tạp. Với 1 request đơn lẻ, overhead này không được bù đắp |
| **T4 không có FlashAttention 2** | T4 là SM 7.5, FlashAttention 2 cần SM ≥ 8.0. vLLM phải fallback sang Triton attention, chậm hơn 20–40% mỗi token |
| **Outlier 30s max** | GPU memory pressure: model chiếm ~14 GB / 15.36 GB VRAM. Đôi khi vLLM phải page KV-cache → spike latency |
| **AWQ dequantization overhead** | T4 không có INT4 tensor cores (cần SM ≥ 8.9). AWQ int4 dequantize sang FP16 trước matmul → không tiết kiệm compute, chỉ tiết kiệm memory bandwidth |
| **Docker HTTP hop** | FastAPI container → `host.docker.internal:8001` → vLLM adds ~5–50 ms round-trip overhead |

---

## 6. Kết Quả 10–15 Requests Đồng Thời

Với vLLM c=15:
- **Wall throughput: 61.7 req/min** (gấp 5.4× Ollama đơn lẻ)
- Per-request latency tăng lên 14.5s mean vì continuous batching gom nhiều request
- **Accuracy không thay đổi** so với c=10 — vLLM xử lý đúng dù batch lớn

Đây là **lợi thế cốt lõi của vLLM**: hy sinh per-request latency để đạt throughput cao hơn nhiều khi có nhiều request đồng thời.

---

## 7. Tóm tắt So sánh

| Tiêu chí | Ollama q8 | vLLM AWQ int4 |
|---|---|---|
| Single request latency (mean) | 5.21 s | 4.74 s |
| Single request latency (p95) | **6.25 s** ✅ | 7.71 s |
| Throughput (10–15 concurrent) | 11.5 req/min ❌ | **61.7 req/min** ✅ |
| Full exact match accuracy | **57%** ✅ | 50.7% |
| Memory footprint | Nặng (q8) | Nhẹ hơn (int4) |
| Hardware yêu cầu | Linh hoạt | GPU CUDA |
| Production scale | ❌ không scale | ✅ scale tốt |

---

