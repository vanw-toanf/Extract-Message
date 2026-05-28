# Kế Hoạch Thực Hiện 6 Tuần

## Định Hướng Chung

Dự án đã hoàn thành MVP trong tuần 1 với các chức năng chính:

- API bóc tách đơn hàng từ text.
- OCR ảnh chụp màn hình.
- Rule-based tiền xử lý và hậu xử lý.
- SLM self-host bằng Qwen2.5 qua Ollama.
- Chuẩn hóa địa chỉ cũ sang địa chỉ mới bằng database địa giới.
- Benchmark 200 mẫu và báo cáo kết quả.

Từ tuần 2 trở đi, trọng tâm chuyển sang nghiên cứu tối ưu hệ thống theo hướng:

- Quantization model.
- Chạy SLM trên CPU.
- Giảm latency.
- Giảm chi phí cloud GPU.
- Tối ưu pipeline hybrid rule-based + SLM.

## Bảng Kế Hoạch

| Công việc tuần 1 | Công việc tuần 2 | Công việc tuần 3 | Công việc tuần 4 | Công việc tuần 5 | Công việc tuần 6 |
|---|---|---|---|---|---|
| Hoàn thành MVP hệ thống bóc tách đơn hàng | Nghiên cứu quantization và khả năng chạy SLM trên CPU | Tối ưu pipeline để giảm số lần gọi model | Benchmark các cấu hình model/quantization | Tối ưu triển khai production và chi phí vận hành | Tổng hợp kết quả, hoàn thiện báo cáo|
| Xây dựng API `/parse-text`, `/parse-image`, `/ocr-image` | Tìm hiểu các mức quantization: Q4, Q5, Q8 | Tăng cường rule-based extraction cho phone, address, note | So sánh Qwen2.5 1.5B, 3B, 7B trên GPU/CPU | Docker hóa cấu hình CPU-only và GPU fallback | Viết báo cáo kỹ thuật cuối cùng |
| Tích hợp Qwen2.5 self-host qua Ollama | Thử nghiệm Ollama quantized models trên CPU | Thiết kế cơ chế chỉ gọi SLM khi rule-based không đủ chắc | Đo latency, P50, P95, P99, throughput | Tối ưu prompt để giảm input/output token | Trình bày kiến trúc hybrid rule + SLM |
| Xây dựng rule-based tiền xử lý và hậu xử lý | Đánh giá latency CPU của Qwen2.5 1.5B/3B | Bổ sung confidence score cho từng field | Đánh giá accuracy từng field: name, phone, note, address | Thử caching kết quả theo hash input | Tổng hợp benchmark thành bảng/biểu đồ |
| Xây dựng DB chuẩn hóa địa giới Việt Nam sau sáp nhập | So sánh chất lượng giữa model nhỏ quantized và model lớn | Xây dựng fallback: 3B CPU -> 7B GPU hoặc manual review | Phân tích trade-off chi phí/độ chính xác/tốc độ | Viết hướng dẫn triển khai cloud CPU tiết kiệm | Chuẩn bị demo nghiệm thu |
| Tạo benchmark 200 mẫu và báo cáo HTML/Excel | Chọn model ứng viên phù hợp cho CPU deployment | Tối ưu các case lỗi trong benchmark thực tế | Chọn cấu hình khuyến nghị cho doanh nghiệp | Hoàn thiện tài liệu API, technical report | Chốt hạn chế và hướng phát triển |

## Chi Tiết Theo Tuần

### Tuần 1: Hoàn Thành MVP

Mục tiêu:

- Có hệ thống end-to-end hoạt động được.
- Có API nhận input text/ảnh và trả JSON đơn hàng.
- Có benchmark ban đầu để đánh giá.

Công việc:

- Xây dựng FastAPI backend.
- Tạo endpoint `/parse-text`.
- Tạo endpoint `/ocr-image` và `/parse-image`.
- Tích hợp EasyOCR cho ảnh chụp màn hình.
- Tích hợp Qwen2.5 self-host qua Ollama/OpenAI-compatible API.
- Xây dựng rule-based extraction cho số điện thoại, tên, số nhà, đường, xã/phường.
- Xây dựng database địa giới Việt Nam sau sáp nhập.
- Viết module fuzzy matching để chuẩn hóa địa chỉ cũ sang địa chỉ mới.
- Tạo benchmark 200 mẫu.
- Xuất báo cáo HTML/Excel cho benchmark.

Kết quả:

- MVP chạy được qua Docker.
- API public có thể bóc tách đơn hàng.
- Có số liệu benchmark Qwen2.5 3B và 7B.

### Tuần 2: Nghiên Cứu Quantization Và CPU Deployment

Mục tiêu:

- Xác định khả năng thay cloud GPU bằng CPU instance rẻ hơn.
- Thử các model quantized nhỏ hơn.

Công việc:

- Tìm hiểu quantization Q4, Q5, Q8 trong Ollama/llama.cpp.
- Thử nghiệm Qwen2.5 1.5B và 3B trên CPU.
- Đo latency đơn lẻ với CPU.
- So sánh chất lượng output giữa 1.5B, 3B, 7B.
- Xác định cấu hình CPU tối thiểu có thể chấp nhận.

Kết quả mong muốn:

- Có bảng latency CPU ban đầu.
- Có nhận xét model nào phù hợp nhất cho CPU.
- Có quyết định sơ bộ: dùng 1.5B hay 3B cho cấu hình tiết kiệm.

### Tuần 3: Tối Ưu Pipeline Giảm Số Lần Gọi Model

Mục tiêu:

- Không gọi SLM cho mọi request.
- Tận dụng rule-based nhiều hơn để giảm latency.

Công việc:

- Thiết kế rule gate: khi nào cần gọi SLM, khi nào không.
- Tăng cường regex/rule cho các field:
  - phone
  - house_number
  - street
  - ward
  - province
  - note đơn giản
- Thêm confidence score cho từng field.
- Nếu rule-based đủ chắc thì trả kết quả luôn.
- Nếu thiếu hoặc mơ hồ thì mới gọi SLM.

Kết quả mong muốn:

- Tỷ lệ request cần gọi SLM giảm.
- Latency trung bình giảm.
- Accuracy không giảm quá nhiều.

### Tuần 4: Benchmark Các Cấu Hình

Mục tiêu:

- Có số liệu định lượng để chọn cấu hình triển khai.

Cấu hình cần benchmark:

- Qwen2.5 1.5B CPU quantized.
- Qwen2.5 3B CPU quantized.
- Qwen2.5 3B GPU.
- Qwen2.5 7B GPU.
- Rule-only baseline.
- Hybrid rule + SLM.

Metric:

- Mean latency.
- P50 latency.
- P95 latency.
- P99 latency.
- Throughput đơn/phút.
- Full exact match.
- Field-level accuracy/F1:
  - name
  - phone
  - note
  - province
  - ward
  - street
  - house_number

Kết quả mong muốn:

- Có bảng so sánh rõ ràng giữa CPU và GPU.
- Có phân tích trade-off giữa chi phí, latency và accuracy.

### Tuần 5: Tối Ưu Triển Khai Và Chi Phí

Mục tiêu:

- Chọn phương án triển khai thực tế phù hợp doanh nghiệp.

Công việc:

- Tối ưu prompt để giảm token.
- Thử output ngắn hơn, ví dụ chỉ để model trả `name`, `note`, `address_raw`.
- Thêm cache kết quả theo hash input.
- Viết Docker Compose cho cấu hình CPU-only.
- Viết Docker Compose cho cấu hình GPU/fallback.
- Đề xuất kiến trúc:
  - CPU model nhỏ cho request thường.
  - GPU/model lớn cho fallback.
  - Manual review khi confidence thấp.

Kết quả mong muốn:

- Có cấu hình deployment tiết kiệm.
- Có tài liệu hướng dẫn triển khai.
- Có khuyến nghị chi phí vận hành.

### Tuần 6: Hoàn Thiện Báo Cáo Và Bảo Vệ

Mục tiêu:

- Tổng hợp toàn bộ kết quả thành báo cáo thuyết phục.

Công việc:

- Cập nhật API usage.
- Tổng hợp benchmark thành bảng và biểu đồ.
- Viết phần nhận xét:
  - Vì sao dùng hybrid pipeline.
  - Vì sao cần quantization.
  - Khi nào dùng CPU.
  - Khi nào dùng GPU/model lớn.

Kết quả mong muốn:
- Có demo API.
- Có số liệu chứng minh hiệu quả.

