# Benchmark Report — gpt-4o-mini vs qwen2.5:3b

## 1. Accuracy — gpt-4o-mini vs qwen2.5-3b-int4 (vLLM, T4)

| Field | qwen2.5:3b (c=1) | gpt-4o-mini (c=1) | Δ |
|---|---:|---:|---:|
| **Full exact match** | 49.0% | **53.3%** | **+4.3 pp** |
| phone | 99.0% | **99.3%** | +0.3 pp |
| name | **98.0%** | 91.0% | −7.0 pp |
| note | 84.7% | **88.3%** | +3.6 pp |
| address.province | 74.7% | **89.3%** | **+14.6 pp** |
| address.ward | 68.7% | **77.0%** | **+8.3 pp** |
| address.street | 80.7% | **82.7%** | +2.0 pp |
| address.house_number | 85.0% | **87.0%** | +2.0 pp |

### Nhận xét accuracy

- **gpt-4o-mini tốt hơn ở hầu hết field**, đặc biệt là địa chỉ hành chính: `address.province` +14.6 pp, `address.ward` +8.3 pp — đây là hai field khó nhất do thay đổi sau sáp nhập tỉnh 2025 và đòi hỏi hiểu ngữ cảnh địa danh Việt Nam.
- **Ngoại lệ: `name` — qwen2.5:3b cao hơn rõ rệt (98% vs 91%).** Lý do: qwen2.5:3b được fine-tune trên dataset đơn hàng Việt Nam, học rất tốt pattern "Tên: ...", "giao cho ...", danh xưng anh/chị. gpt-4o-mini đôi khi include danh xưng hoặc bỏ sót tên ngắn.
- **Full exact match**: gpt-4o-mini 53.3% vs 49.0% — cải thiện nhờ địa chỉ tốt hơn bù lại lỗi name.

---

## 2. Latency

### c=1 (sequential — latency thực mỗi request)

| Metric | qwen2.5:3b vLLM (T4) | gpt-4o-mini |
|---|---:|---:|
| Mean | 2.34 s | **2.23 s** |
| P50 | 2.38 s | **2.04 s** |
| P95 | 2.95 s | **2.78 s** |
| P99 | 3.29 s | **3.75 s** |
| Max | 3.39 s | 33.20 s |
| Wall time (300 req) | 702 s | 668 s |

### c=10 / c=15 (song song — throughput hàng loạt)

| Metric | qwen2.5:3b vLLM c=15 | gpt-4o-mini c=10 |
|---|---:|---:|
| P50 | 6.97 s | 2.53 s |
| P95 | 9.38 s | 9.82 s |
| Wall time (300 req) | **141 s** | 115 s |
| Throughput thực (wall) | **128 req/min** | 156 req/min* |

\* gpt-4o-mini c=10: wall 115s → 300/115×60 = 156 req/min thực tế.

### Nhận xét latency

- **c=1**: Hai model có latency tương đương — P50 gpt-4o-mini 2.04s vs 3b 2.38s. Nhưng max của gpt-4o-mini (33s) là outlier do retry khi OpenAI throttle; max của 3b chỉ 3.39s rất ổn định.
- **c=10/15**: Cả hai đều đạt ~120-156 req/min throughput thực. Khi concurrent cao, T4 vLLM ổn định hơn về tail latency vì không phụ thuộc external API.

---

## 3. So sánh chi phí vận hành trên Google Cloud

Giả sử deploy trên GCP, khu vực asia-southeast1 (Singapore).

### Chi phí server

| Option | Instance | Chi phí/giờ | Chi phí/tháng (always-on) |
|---|---|---:|---:|
| **Self-host (T4)** | n1-standard-4 + T4 | ~$0.53/hr | ~$300/tháng |
| **Self-host (T4 Spot)** | n1-standard-4 + T4 (Spot) | ~$0.16/hr | ~$115/tháng (có thể bị preempt) |
| **API (gpt-4o-mini)** | Không cần GPU, chỉ cần app server nhỏ | ~$0.05/hr (e2-small) | ~$36/tháng |

### Chi phí OpenAI API (gpt-4o-mini)

Ước tính mỗi request: ~400 input tokens + ~100 output tokens.

| Pricing | Input | Output |
|---|---|---|
| gpt-4o-mini | $0.15 / 1M tokens | $0.60 / 1M tokens |
| Per request | $0.00006 | $0.00006 |
| **Tổng/request** | | **~$0.00012** |

| Traffic | API cost/ngày | API cost/tháng |
|---|---:|---:|
| 1,000 req/ngày | $0.12 | $3.6 |
| 10,000 req/ngày | $1.20 | $36 |
| 50,000 req/ngày | $6.00 | $180 |
| 100,000 req/ngày | $12.00 | $360 |

### Điểm hòa vốn (API cost = T4 Spot cost)

T4 Spot ~$115/tháng → hòa vốn khi API cost = $115/tháng → **~320,000 req/tháng (~11,000 req/ngày)**.

T4 On-demand ~$300/tháng → hòa vốn tại **~1,060,000 req/tháng (~35,000 req/ngày)**.

---

## 4. Khuyến nghị: Self-host T4 hay OpenAI API?

### Chọn OpenAI API nếu:

| Điều kiện | Lý do |
|---|---|
| Traffic < 35,000 req/ngày | Dưới điểm hòa vốn T4 on-demand — API rẻ hơn |
| Giai đoạn MVP / early-stage | Không cần trả $300/tháng cố định khi traffic chưa ổn định |
| Không muốn quản lý infra | Không cần maintain vLLM, Docker, GPU driver, model weights |
| Cần accuracy địa chỉ tốt hơn | gpt-4o-mini +14.6 pp province, +8.3 pp ward so với 3b |

### Chọn Self-host T4 (vLLM + qwen2.5:3b) nếu:

| Điều kiện | Lý do |
|---|---|
| Traffic > 35,000 req/ngày (on-demand) hoặc > 11,000 req/ngày (Spot) | Chi phí tuyến tính của API vượt chi phí cố định T4 |
| Cần latency tail ổn định | T4 max = 3.4s vs gpt-4o-mini max = 33s (khi retry) |
| Yêu cầu data privacy nghiêm ngặt | Dữ liệu đơn hàng không ra khỏi hạ tầng |
| Accuracy name là ưu tiên | qwen2.5:3b fine-tuned 98% vs gpt-4o-mini 91% |

### Khuyến nghị cho giai đoạn hiện tại

**Bắt đầu với OpenAI API (`gpt-4o-mini`)**, vì:

1. **Không cần trả $300/tháng cố định** ngay từ đầu khi traffic chưa ổn định.
2. **Accuracy tổng thể tốt hơn** (full exact +4.3 pp), đặc biệt địa chỉ sau sáp nhập — quan trọng cho use case giao hàng.
3. **Không cần quản lý T4 instance, vLLM, GPU driver** — tiết kiệm engineering effort.
4. **Khi traffic vượt ~35,000 req/ngày** (hoặc khi muốn tối ưu chi phí), chuyển sang self-host T4 Spot + qwen2.5:3b là bước tiếp theo tự nhiên.
5. **Nếu muốn cải thiện `name`** (field duy nhất 3b tốt hơn): fine-tune thêm gpt-4o-mini hoặc dùng rule-extractor hiện có để bù lại.

---

## 5. Tóm tắt nhanh

| Tiêu chí | qwen2.5:3b T4 (vLLM) | gpt-4o-mini API |
|---|---|---|
| Full exact match | 49.0% | **53.3%** ✅ |
| name accuracy | **98.0%** ✅ | 91.0% |
| address tổng thể | Kém hơn rõ | **Tốt hơn** ✅ |
| Latency P50 (c=1) | 2.38s | **2.04s** ✅ |
| Latency max | **3.39s** ✅ | 33s (retry) |
| Chi phí cố định/tháng | $115–$300 | **$36** (app server) ✅ |
| Hòa vốn | — | ~35,000 req/ngày |
| Quản lý infra | Cần T4, vLLM, Docker | **Không cần GPU** ✅ |
| Data privacy | **Hoàn toàn nội bộ** ✅ | Qua OpenAI |

---



