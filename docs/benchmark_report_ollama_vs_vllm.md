# Benchmark Report: Ollama vs vLLM — qwen2.5 finetune (vin-extractor)

**Ngày:** 2026-06-06  
**Model:** qwen2.5 finetune (vin-extractor), hai kích thước 7B và 3B  
**Dataset:** 300 đơn hàng (`data/benchmark_orders_200.jsonl`)  
**Task:** Trích xuất name, phone, note, address (province/ward/street/house_number) từ text thô

---

## 1. Môi trường

| | qwen2.5-7b-q8 (Ollama) | qwen2.5-7b-int4 (vLLM) | qwen2.5-3b-int4 (vLLM) |
|---|---|---|---|
| **Model format** | GGUF q8 (8-bit) | AWQ int4 (4-bit) | AWQ int4 (4-bit) |
| **Hardware** | Local machine | Tesla T4, 16 GB VRAM | Tesla T4, 16 GB VRAM |
| **GPU compute cap** | — | SM 7.5 (không có FlashAttention 2) | SM 7.5 (không có FlashAttention 2) |
| **Backend** | Ollama + llama.cpp | vLLM 0.8.5, Triton attention | vLLM 0.8.5, Triton attention |
| **Serving** | Ollama HTTP | FastAPI (Docker) → vLLM :8001 | FastAPI (Docker) → vLLM :8001 |
| **max_num_seqs** | 1 | 20 | 20 |
| **max_model_len** | 1024 | 1024 | 1024 |
| **max_tokens** | 256 | 256 | 256 |
| **VRAM used** | — | ~14 GB | ~12.7 GB |

---

## 2. Latency per Request

### 2.1 Single Request (Concurrency = 1)

| Metric | qwen2.5-7b-q8 (Ollama) | qwen2.5-7b-int4 (vLLM) | **qwen2.5-3b-int4 (vLLM)** |
|---|---|---|---|
| **Mean** | 5.21 s | 4.74 s | **2.34 s** |
| **p50 (median)** | 5.31 s | 6.05 s | **2.38 s** |
| **p95** | 6.25 s | 7.71 s | **2.95 s** |
| **p99** | 6.60 s | 8.46 s | **3.29 s** |
| **Min** | 3.32 s | 3.09 s | **1.14 s** |
| **Max** | 6.82 s | 30.09 s | **3.39 s** |
| **Wall time (300 req)** | 1564 s | 1421 s | **702 s** |

> xformers làm p95/p99 tệ hơn đáng kể → **không dùng xformers trên T4**.

3B đạt target 2–3s: mean **2.34s**, p95 **2.95s**, không còn outlier 30s như 7B.

### 2.2 Concurrent Requests (Concurrency = 15)

| Metric | qwen2.5-7b-int4 (vLLM) c=15 | **qwen2.5-3b-int4 (vLLM) c=15** |
|---|---|---|
| **Mean latency/req** | 14.49 s | **7.01 s** |
| **p50 latency/req** | 14.49 s | **6.97 s** |
| **p95 latency/req** | 18.14 s | **9.38 s** |
| **p99 latency/req** | 21.32 s | **10.23 s** |
| **Min latency/req** | 5.18 s | **2.94 s** |
| **Max latency/req** | 24.24 s | **11.53 s** |
| **Wall time (300 req)** | 292 s | **141 s** |

---

## 3. Throughput Thực Tế

> `throughput_orders_per_minute` Throughput thực tế tính theo `wall_seconds`.

| Setup | Wall time (300 req) | **Throughput thực (wall)** | So với baseline |
|---|---|---|---|
| qwen2.5-7b-q8 (Ollama) c=1 | 1564 s (26.1 phút) | 11.5 req/min | baseline |
| qwen2.5-7b-int4 (vLLM) c=1 | 1421 s (23.7 phút) | 12.7 req/min | +10% |
| qwen2.5-7b-int4 (vLLM) c=10 | 373 s (6.2 phút) | 48.3 req/min | +320% |
| qwen2.5-7b-int4 (vLLM) c=15 | 292 s (4.9 phút) | 61.7 req/min | +436% |
| qwen2.5-3b-int4 (vLLM) c=1 | 702 s (11.7 phút) | 25.6 req/min | +122% |
| **qwen2.5-3b-int4 (vLLM) c=15** | **141 s (2.3 phút)** | **128.0 req/min** | **+1013%** |

3B c=15 xử lý 300 đơn trong **2.3 phút** thay vì **26.1 phút** của Ollama — **nhanh hơn 11×**.

---

## 4. Accuracy

| Field | qwen2.5-7b-q8 (Ollama) | qwen2.5-7b-int4 (vLLM) | **qwen2.5-3b-int4 (vLLM)** | Δ (3B vs 7B vLLM) |
|---|---|---|---|---|
| **Full exact match** | **57.0%** | 50.7% | 49.0% | −1.7 pp |
| name | **99.0%** | 97.7% | 98.0% | +0.3 pp |
| phone | **99.3%** | 99.3% | 99.0% | −0.3 pp |
| note | **86.7%** | 82.0% | **84.7%** | **+2.7 pp** |
| address.province | **81.0%** | 77.3% | 74.7% | −2.6 pp |
| address.ward | 70.3% | 68.3% | 68.7% | +0.4 pp |
| address.street | 82.0% | **84.0%** | 80.7% | −3.3 pp |
| address.house_number | **90.0%** | 89.0% | 85.0% | −4.0 pp |

**Kết luận accuracy:**
- 3B chỉ kém 7B **1.7 pp full exact** — trade-off rất tốt đổi lại 2× tốc độ
- 3B **tốt hơn** 7B ở `note` (+2.7 pp) và `ward` (+0.4 pp)
- Field bị giảm nhiều nhất: `house_number` (−4 pp) và `street` (−3.3 pp)
- `phone` gần như bằng nhau giữa tất cả các setup (99–99.3%)
- Accuracy không thay đổi giữa c=1 và c=15 → concurrency không ảnh hưởng quality

---

## 5. Phân tích: Tại Sao vLLM Single Request 7B Chậm Hơn Ollama (p95/p99)?

### 5.1 Phân rã thời gian (ước tính)

Một request điển hình gồm hai giai đoạn:

```
Total latency = TTFT + Decode time

TTFT    = prefill(system_prompt ~300 tok + user_input ~50 tok) / prefill_speed
Decode  = output_tokens ~60-80 tok / decode_speed
```

| | qwen2.5-7b-int4 (vLLM, T4) | qwen2.5-3b-int4 (vLLM, T4) |
|---|---|---|
| Prefill speed | ~400 tok/s | ~800 tok/s |
| Decode speed (batch=1) | ~35 tok/s | ~70 tok/s |
| **TTFT** (350 tok) | **~0.9 s** | **~0.4 s** |
| **Decode** (70 tok) | **~2.0 s** | **~1.0 s** |
| Overhead (scheduler, HTTP) | **~1.8 s** | **~0.9 s** |
| **Tổng thực đo** | **4.74 s** | **2.34 s** |

### 5.2 Lý do tail latency của vLLM 7B cao hơn Ollama

| Nguyên nhân | Giải thích |
|---|---|
| **Continuous batching scheduler** | vLLM quản lý KV-cache pool phức tạp. Với 1 request đơn lẻ, overhead này không được bù đắp |
| **T4 không có FlashAttention 2** | T4 là SM 7.5, FlashAttention 2 cần SM ≥ 8.0. vLLM fallback sang Triton attention, chậm hơn 20–40% mỗi token |
| **Outlier 30s max (7B)** | GPU memory pressure: 7B chiếm ~14 GB / 15.36 GB VRAM. Đôi khi vLLM phải page KV-cache → spike latency. 3B chỉ dùng ~12.7 GB, ít bị vấn đề này hơn |
| **AWQ dequantization** | T4 không có INT4 tensor cores (cần SM ≥ 8.9). AWQ int4 dequantize sang FP16 → chỉ tiết kiệm memory bandwidth, không tiết kiệm compute |
| **Docker HTTP hop** | FastAPI → `host.docker.internal:8001` → vLLM adds ~5–50 ms overhead |

---

## 6. Tóm Tắt So Sánh Toàn Bộ

| Tiêu chí | qwen2.5-7b-q8 (Ollama) | qwen2.5-7b-int4 (vLLM) | **qwen2.5-3b-int4 (vLLM)** |
|---|---|---|---|
| Single req latency (mean) | 5.21 s | 4.74 s | **2.34 s** ✅ |
| Single req latency (p95) | 6.25 s | 7.71 s | **2.95 s** ✅ |
| Max latency (outlier) | 6.82 s | 30.09 s ❌ | **3.39 s** ✅ |
| Throughput c=15 | 11.5 req/min ❌ | 61.7 req/min | **128.0 req/min** ✅ |
| Full exact match | **57.0%** | 50.7% | 49.0% |
| note accuracy | **86.7%** | 82.0% | 84.7% |
| phone accuracy | **99.3%** | 99.3% | 99.0% |
| VRAM footprint | — | ~14 GB | **~12.7 GB** ✅ |
| Production scale | ❌ | ✅ | ✅ |

**Lựa chọn:**
- **qwen2.5-3b-int4 (vLLM)** là lựa chọn tốt nhất cho production: đạt target latency 2–3s, throughput 11× Ollama, accuracy chỉ kém 7B 1.7 pp full exact, max latency ổn định (3.4s vs 30s của 7B).
- **qwen2.5-7b-int4 (vLLM)** phù hợp nếu accuracy là ưu tiên tuyệt đối và latency ≤5s được chấp nhận.
- **qwen2.5-7b-q8 (Ollama)** chỉ phù hợp cho môi trường không có GPU hoặc traffic cực thấp (1 request tại một thời điểm).
