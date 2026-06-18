# CLAUDE.md — Project Context for AI Assistants

## Tổng Quan Dự Án

**Clipboard Parsing & Smart Delivery Order Creation** — Hệ thống tự động bóc tách thông tin đơn giao hàng từ văn bản tự nhiên (tin nhắn Facebook, Zalo, TikTok, livestream) hoặc ảnh chụp màn hình. Output là JSON chuẩn để điền form tạo đơn vận chuyển.

**Bối cảnh**: Social Commerce Việt Nam, dữ liệu bất chuẩn, viết tắt, sai chính tả, địa chỉ hành chính cũ/mới sau sáp nhập 2025.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI (async) + Uvicorn |
| LLM | OpenAI API (`gpt-4o-mini`) via `openai` SDK, structured outputs |
| Geocoding | Goong.io API (`rsapi.goong.io/geocode`) |
| OCR | EasyOCR (vi + en, chạy in-process, CPU) |
| Fuzzy matching | `rapidfuzz` |
| Schemas | Pydantic v2 |
| HTTP Client | `httpx` (async) |
| Config | `python-dotenv` + Pydantic Settings |
| Frontend | Vanilla HTML/CSS/JS + Leaflet.js (bản đồ) |
| Containerization | Docker multi-stage build, docker-compose |
| Python | 3.12 |

---

## Cấu Trúc Thư Mục

```
extract_context/
├── main.py                          # FastAPI app + endpoints
├── app/
│   ├── __init__.py
│   ├── core_config.py               # Settings (pydantic, từ .env)
│   ├── schemas/
│   │   └── order.py                 # ParseResponse, LLMOrderStrict, ExtractedAddress, ...
│   ├── pipeline/
│   │   ├── parser.py                # OrderParser — orchestrator chính (async)
│   │   ├── address_normalizer.py    # Fuzzy match + AdminDB chuẩn hóa địa chỉ
│   │   ├── phone_extractor.py       # Regex phone VN + mask/normalize
│   │   ├── rule_extractor.py        # Rule-based name/address/note extraction
│   │   ├── text_utils.py            # compact_text, strip_accents, normalize_key, short_province
│   │   └── ocr.py                   # EasyOCR image → text
│   └── services/
│       ├── base_client.py           # BaseHttpClient + CircuitBreaker (OOP base)
│       ├── llm_client.py            # LLMClient(BaseHttpClient) — OpenAI structured output
│       └── goong_client.py          # GoongClient(BaseHttpClient) — geocoding
├── web/
│   ├── index.html                   # Demo UI chính
│   ├── dashboard.html               # Dashboard thống kê
│   ├── app.js                       # Frontend logic (fetch API, Leaflet map)
│   └── style.css                    # Styling
├── vietnam_admin_db/
│   ├── vietnam_administrative.json  # DB địa giới hành chính (~2.7MB)
│   ├── lookup_ward_by_name.json     # Lookup table tra ward theo tên
│   ├── lookup_ward_by_code.json     # Lookup table tra ward theo mã
│   ├── old_wards.json               # Dữ liệu phường/xã cũ
│   ├── old_districts.json           # Dữ liệu quận/huyện cũ
│   ├── old_provinces.json           # Dữ liệu tỉnh/thành cũ
│   ├── province_merger_map.json     # Bản đồ sáp nhập tỉnh
│   ├── ambiguous_wards.json         # Xã/phường trùng tên
│   ├── not_found_wards.json         # Xã/phường không tìm thấy
│   ├── crawl_vietnam_admin.py       # Script crawl dữ liệu hành chính
│   ├── fix_old_province.py          # Script fix dữ liệu tỉnh cũ
│   └── post_process_admin.py        # Post-process dữ liệu
├── data/
│   ├── benchmark_orders_200.jsonl   # Dataset benchmark 200 mẫu
│   ├── benchmark_test_100.jsonl     # Dataset test 100 mẫu
│   └── feedback.jsonl               # Feedback từ người dùng (auto-generated)
├── scripts/
│   ├── run_benchmark.py             # Benchmark qua API (HTTP POST)
│   ├── run_benchmark_local.py       # Benchmark local (không qua HTTP)
│   ├── generate_benchmark_orders.py # Sinh dữ liệu benchmark
│   ├── generate_benchmark_report.py # Tạo report từ kết quả benchmark
│   ├── generate_finetune_dataset.py # Sinh dataset finetune
│   ├── eval_finetune.py             # Đánh giá model finetune
│   ├── export_benchmark_errors_excel.py
│   ├── setup_ollama.sh              # Setup Ollama
│   ├── setup_vllm.sh                # Setup vLLM
│   └── finetune/                    # Scripts finetune
├── models/
│   └── qwen25_vin_q8.gguf          # Model Qwen2.5 quantized (~8GB)
├── benchmark_results/               # Kết quả benchmark nhiều model
├── docs/
│   ├── architecture.md              # Kiến trúc hệ thống (chi tiết, mermaid diagrams)
│   ├── technical_report.md          # Báo cáo kỹ thuật
│   ├── benchmark_report_openai.md   # Benchmark gpt-4o-mini vs qwen
│   ├── benchmark_report_ollama_vs_vllm.md
│   ├── benchmark_report_rule_vs_llm.md
│   ├── api_usage.md                 # Hướng dẫn sử dụng API
│   ├── cpu_optimization.md          # Tối ưu chạy CPU
│   ├── finetune_dataset.md          # Tài liệu dataset finetune
│   └── test_case_plan.md            # Kế hoạch test case
├── Dockerfile                       # Multi-stage: builder (torch+easyocr) → runtime
├── docker-compose.yml               # Service: api (port 8000)
├── requirements.txt                 # Dependencies
├── .env.example                     # Template cấu hình
├── CHANGES.md                       # Changelog nhánh openai
└── README.md                        # Hướng dẫn chạy + API docs
```

---

## Kiến Trúc Hệ Thống

### Luồng xử lý chính (POST /parse-text)

```
Request → Input guard (≤5000 chars)
       → Semaphore (max 20 concurrent)
       → compact_text() + extract_phone() + mask_phone()
       → extract_rule_hints() → rule_name, rule_address
       → extract_rule_note() → rule_note
       → LLMClient.extract_order() → gpt-4o-mini structured output
       → Merge: regex_phone > LLM phone, rule fallbacks
       → AddressNormalizer.normalize() → fuzzy match AdminDB
       → Build address_new
       → GoongClient.geocode() → fallback chain (address_new → address_raw → street+province)
       → Province validation (Goong old system → new AdminDB mapping)
       → ParseResponse { recipient_name, phone_number, note, address_raw, address_new, address_info, lat, lng }
```

### Hybrid Pipeline

Hệ thống dùng pipeline lai 4 lớp:
1. **Rule-based trước**: phone regex, text compact, input validation
2. **LLM (gpt-4o-mini)**: trích xuất ngữ nghĩa (tên, note, địa chỉ)
3. **Rule-based sau**: sửa lỗi tách số nhà/đường, merge fallback
4. **Mapping DB**: chuẩn hóa địa giới sau sáp nhập 2025

### OOP Inheritance — BaseHttpClient

```
BaseHttpClient (retry + circuit breaker)
├── LLMClient   (_RETRYABLE: RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
└── GoongClient (_RETRYABLE: TimeoutException, ConnectError, RemoteProtocolError)
```

- **Retry**: max 3 attempts, exponential backoff + jitter
- **Circuit Breaker**: 5 failures → OPEN (30s) → HALF_OPEN → probe

---

## API Endpoints

| Method | Path | Mô tả |
|---|---|---|
| `POST` | `/parse-text` | Nhận text, trả JSON đơn hàng đã chuẩn hóa + geocode |
| `POST` | `/parse-image` | Nhận ảnh → OCR → parse pipeline |
| `POST` | `/ocr-image` | Chỉ OCR ảnh thành text |
| `POST` | `/normalize-address` | Test riêng DB chuẩn hóa địa giới |
| `POST` | `/feedback` | Ghi nhận feedback sửa đổi từ user |
| `GET`  | `/feedback` | Lấy danh sách feedback + request count |
| `GET`  | `/health` | Health check |

### Error Codes

| HTTP | detail | Nguyên nhân |
|---|---|---|
| 400 | `input_too_long` | Text > 5000 ký tự |
| 422 | `address_not_found` | Không tìm ra địa chỉ |
| 422 | `geocode_failed` | sub_region null, hoặc Goong không resolve được |
| 429 | `Server busy...` | Semaphore queue timeout |
| 503 | `LLM service unavailable` | Circuit breaker OPEN |

---

## LLM System Prompt

System prompt (~1200 tokens, static → auto-cached bởi OpenAI) gồm:
- **Schema JSON** cho structured output
- **9 luật bắt buộc [R1–R9]**:
  - R1: Không bịa dữ liệu
  - R2: Input không phải đơn hàng → tất cả null
  - R3: Phone được mask thành `[PHONE]` token
  - R4: `address_raw` copy nguyên văn
  - R5: `address_info` phân tách địa chỉ (2 cấp mới vs 3 cấp cũ); thôn/xóm/ấp là đơn vị dưới xã → đưa vào address_number
  - R6: Nhận diện người nhận (quan trọng nhất) — phân biệt courier vs recipient
  - R7: Nhiều địa chỉ → chọn destination / địa chỉ mới
  - R8: Note giao hàng (thời gian, vị trí, hàng hóa)
  - R9: `short_reasoning` chỉ dùng cho case phức tạp
- **4 few-shot examples** cover: đơn đơn giản, 2 người, "[Tên] ơi" pattern, đổi địa chỉ

---

## Schemas Quan Trọng (Pydantic v2)

### Input/Output chính
- `ParseRequest`: `{ text: str }`
- `ParseResponse`: `{ recipient_name, phone_number, note, address_raw, address_new, address_info: FinalAddressInfo, lat, lng }`
- `FinalAddressInfo`: `{ address_number, street, municipality, sub_region, country }`

### Internal
- `ExtractedOrder`: kết quả nội bộ sau LLM
- `ExtractedAddress`: `{ province, district_hint, ward, street, house_number }`
- `NormalizedAddress`: `{ province, ward, street, house_number, is_normalized, confidence, matched_by, candidates[], warnings[] }`

### Strict (cho OpenAI structured output)
- `LLMOrderStrict`: `{ short_reasoning, recipient_name, phone_number, note, address_raw, address_info: LLMAddressInfoStrict }`
- `LLMAddressInfoStrict`: `{ address_number, street, neighborhood, municipality, sub_region, country }` — không có default values → tất cả required trong JSON schema

### Mapping LLMAddressInfoStrict → ExtractedAddress (`_to_internal`)
- `neighborhood` có giá trị và không phải thôn/xóm/ấp → `ward = neighborhood`, `district_hint = municipality`
- `neighborhood` là thôn/xóm/ấp (khớp `_HAMLET_PREFIX_RE`) → đây không phải cấp xã/phường → `ward = municipality`, `district_hint = None`
- `municipality` bắt đầu bằng quận/huyện → `district_hint = municipality`, `ward = None`
- Còn lại → `ward = municipality`

---

## Address Normalization

### Database
`vietnam_admin_db/vietnam_administrative.json` chứa:
- Tỉnh/thành phố sau sáp nhập 2025
- Xã/phường sau sáp nhập
- `merged_from[]`: tên tỉnh cũ, huyện cũ, xã/phường cũ

### Matching Strategy
1. Ưu tiên match tỉnh/thành (province) trước
2. Tiếp theo match huyện/quận cũ nếu có (district_hint)
3. Cuối cùng match xã/phường (ward)
4. Combined score = weighted sum (province_score × 0.42 + district_score × 0.28 + ward_score × 0.30)
5. Fuzzy threshold = 84 (configurable)
6. `is_normalized = True` khi score ≥ threshold AND không ambiguous

### Key Functions
- `normalize_key()`: strip accents + remove admin prefixes → fuzzy-friendly key
- `normalize_text_key()`: giữ dấu tiếng Việt + remove admin prefixes → text tiebreaker
- `short_province()` (text_utils): strip "Thủ đô / Thành phố / Tỉnh" khỏi đầu chuỗi tỉnh — áp dụng vào `sub_region` trong `parser.py` trước khi build `address_new` và `address_info`, tránh Goong fail khi nhận "Thủ đô Hà Nội"
- `_score()`: `fuzz.ratio` + `token_sort_ratio` (chỉ khi base ratio ≥ 60)
- `infer_province_from_municipality()`: tra unique map (ward/district chỉ thuộc 1 tỉnh HN/HCM)

---

## Phone Extraction

- Regex: `(?<!\d)\(?(?:\+?84|0)(?:[\s.\-()]*\d){9}\)?(?!\d)`
- Valid prefixes: 03, 05, 07, 08, 09 (mobile only)
- Normalize: `+84` → `0`, chỉ accept 10 digits
- `mask_phone()`: thay phone bằng `[PHONE]` token trước khi gửi LLM
- Context blocking: không bắt nhầm "số nhà", "mã đơn" là phone

---

## Geocoding (Goong)

### Fallback Chain
1. `address_new` (đã chuẩn hóa theo AdminDB, `sub_region` đã qua `short_province()`)
2. `address_raw` (nguyên văn từ LLM)
3. `address_number + street + province_short` (bỏ municipality — tránh lỗi tên hành chính cũ/mới)

`short_province()` strip "Thủ đô / Thành phố / Tỉnh" — áp dụng cho cả output và geocoding (tránh Goong trả kết quả sai với "Thủ đô Hà Nội").

### Province Validation
- Goong trả `compound_province` theo hệ hành chính cũ
- Map old → new province qua `AddressNormalizer` DB
- Strip accents + compare (allow partial match)
- Reject khi `compound_province = null` (ambiguous)

---

## Cấu Hình (.env)

```env
# LLM
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini          # hoặc tên model khác
LLM_MAX_TOKENS=256
LLM_TIMEOUT_SECONDS=30
ENABLE_LLM=true
CPU_FAST_MODE=false             # true = skip LLM nếu rule đủ

# Matching
FUZZY_THRESHOLD=84

# Concurrency
LLM_MAX_CONCURRENT=20
LLM_QUEUE_TIMEOUT_SECONDS=30

# Geocoding
GOONG_API=your_key
GOONG_TIMEOUT_SECONDS=5

# Database
ADMIN_DB_PATH=vietnam_admin_db/vietnam_administrative.json
```

---

## Chạy Dự Án

```bash
# Development
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Docker
docker compose up --build

# Test nhanh
curl -X POST http://localhost:8000/parse-text \
  -H "Content-Type: application/json" \
  -d '{"text": "Nguyễn Văn A, 0912345678, 45 Lê Lợi Q1 HCM, giao buổi sáng"}'

# Benchmark
python scripts/run_benchmark.py \
  --api-url http://127.0.0.1:8000 \
  --input data/benchmark_orders_200.jsonl \
  --output-dir benchmark_results/<model-name> \
  --model-name <model-name> \
  --warmup 5 --concurrency 1
```

---

## Conventions & Patterns

### Code Style
- Python 3.12 type hints (`str | None`, not `Optional[str]`)
- Async-first: FastAPI endpoints, LLM calls, geocoding đều async
- Pydantic v2 models cho validation + serialization
- `@lru_cache` cho singletons (Settings, OrderParser, GoongClient)

### Error Handling
- `CircuitBreakerOpenError` → HTTP 503
- `GoongGeocodeFailed` → HTTP 422
- `ValueError` (input guard) → HTTP 400
- `asyncio.TimeoutError` (semaphore) → HTTP 429

### Naming
- Vietnamese comments/docs where appropriate
- English code identifiers
- `_protected_call()` pattern cho external API calls

### Testing
- `test_llm.py`: smoke test cho LLM
- `test_gong.py`: test Goong client
- `scripts/run_benchmark.py`: full benchmark suite
- `data/benchmark_orders_200.jsonl`: ground truth dataset

---

## Benchmark Tham Khảo

| Model | Mean Latency | P95 | Full Exact Match | Province Acc | Ward Acc |
|---|---|---|---|---|---|
| Qwen2.5 3B (self-hosted vLLM) | 2.34s | 2.95s | 49.0% | 74.7% | 68.7% |
| Qwen2.5 7B (self-hosted) | 5.19s | 6.15s | 47.5% | 94.5% | 91.5% |
| gpt-4o-mini (OpenAI API) | 2.23s | 2.78s | 53.3% | 89.3% | 77.0% |

Phone accuracy luôn đạt ~100% nhờ regex (không qua LLM).

**Nhánh hiện tại**: `openai` — sử dụng OpenAI API gpt-4o-mini với structured outputs. Self-hosted Qwen đã được loại bỏ khỏi pipeline chính.

---

## Edge Cases Địa Chỉ Đã Xử Lý

| Input | Vấn đề | Fix |
|---|---|---|
| `thôn Hạ, xã A Sào` | LLM đặt "thôn Hạ" vào `neighborhood`, trả `municipality="thôn Hạ"` | `_HAMLET_PREFIX_RE` trong `_to_internal()`: khi neighborhood là thôn/xóm/ấp → lấy municipality làm ward |
| `Công xã Paris, Q1` | `WARD_RE` match "xã Paris" trong tên đường; `re.sub` chỉ remove "x" → "Xã ã Paris" | (1) Sắp xếp lại alternation trong `re.sub` (`xã` trước `x\.?`); (2) merge guard trong `_merge_address_hints` bỏ qua rule ward hint khi core name xuất hiện trong `street` hoặc `house_number` |
| `Nam Từ Liêm, Thủ đô Hà Nội` | `address_new` chứa "Thủ đô Hà Nội" → Goong geocode sai | `short_province()` strip prefix tỉnh/thành/thủ đô khỏi `sub_region` trước khi build `address_new` và `address_info` |

---

## Web Frontend

- **Demo page** (`web/index.html`): nhập text → parse → hiển thị kết quả + bản đồ Leaflet
- **Dashboard** (`web/dashboard.html`): thống kê request, feedback
- API URL production: `https://api-extract.vanwtoanf.io.vn`
- Auto-save feedback: sau 8s không edit, tự gửi corrections về `/feedback`
- Leaflet map zoom đến marker khi có lat/lng
