# Changelog — nhánh `openai`

Chuyển từ self-hosted model (vLLM / ollama / llamacpp) sang **OpenAI API** (`gpt-4o-mini`).

---

## Tổng quan kiến trúc mới

```
Request
  └─► main.py (FastAPI, asyncio.Semaphore)
        └─► parser.py (async parse)
              ├─ rule_extractor / phone_extractor  [sync, không đổi]
              └─► llm_client.py
                    ├─ Input Guardrail (> 500 ký tự → ValueError)
                    ├─ Circuit Breaker (CLOSED → OPEN → HALF_OPEN)
                    ├─ Retry + Exponential Backoff với Jitter
                    ├─ AsyncOpenAI.beta.chat.completions.parse()  ← Structured Output
                    └─ Post-process Guardrail (country, address_raw)
```

---

## Chi tiết từng file

### `.env`

| Trước | Sau |
|---|---|
| `LLM_PROVIDER=openai_compatible` | Xóa (không cần) |
| `LLM_BASE_URL=http://host.docker.internal:8001` | Xóa |
| `LLM_MODEL=vin-extractor` | `LLM_MODEL=gpt-4o-mini` |
| `LLM_API_KEY=ignored` | Xóa (dùng `OPENAI_API_KEY`) |
| `LLM_NUM_CTX=1024` | Xóa |
| `LLM_MAX_TOKENS=256` | Giữ |
| `LLM_TIMEOUT_SECONDS=30` | Giữ |

---

### `app/core_config.py`

**Xóa**: `llm_provider`, `llm_base_url`, `llm_api_key`, `llm_keep_alive`, `llm_model_path`, `llm_threads`, `llm_num_ctx`.

**Thêm**: `openai_api_key` (đọc từ env `OPENAI_API_KEY`).

**Giữ**: `llm_model`, `llm_max_tokens`, `llm_timeout_seconds`, `enable_llm`, `cpu_fast_mode`, `fuzzy_threshold`, `llm_max_concurrent`, `llm_queue_timeout`.

---

### `app/schemas/order.py`

Thêm 2 class cuối file:

```python
class LLMAddressInfoStrict(BaseModel):
    # Không có default → tất cả required trong JSON schema (OpenAI strict mode)
    address_number: str | None
    street: str | None
    neighborhood: str | None
    municipality: str | None
    sub_region: str | None
    country: str | None

class LLMOrderStrict(BaseModel):
    short_reasoning: str | None   # ← field đầu tiên, gợi CoT trước khi output
    recipient_name: str | None
    phone_number: str | None
    note: str | None
    address_raw: str | None
    address_info: LLMAddressInfoStrict
```

---

### `app/services/llm_client.py` ← thay đổi lớn nhất

#### 1. System Prompt (tĩnh, ~1144 tokens → vượt ngưỡng cache 1024)

Gồm 9 luật (`[R1]`–`[R9]`) và 4 few-shot examples bao phủ các case khó:

| Case | Rule | Expected |
|---|---|---|
| Đơn đơn giản | — | `short_reasoning: null` |
| `chị A lấy đơn giao cho anh B` | R6 | `recipient_name: B`, `short_reasoning: "A giao, B nhận"` |
| `[Tên] ơi giao cho mình nha` | R6 | `recipient_name: null` (Tên là courier) |
| Đổi địa chỉ | R7 | Chỉ giữ địa chỉ mới |

**Về prompt caching**: OpenAI tự động cache khi system prompt > 1024 tokens và không thay đổi giữa các request. Không cần thêm code đặc biệt. Lợi ích: giảm 50% chi phí input tokens + giảm latency prefill.

#### 2. Circuit Breaker

```
CLOSED ──(5 failures)──► OPEN ──(30s)──► HALF_OPEN ──(1 success)──► CLOSED
                                                     └──(1 failure)──► OPEN
```

- 5 failures liên tiếp → trip sang OPEN
- 30 giây sau → tự động probe (HALF_OPEN)
- Request bị OPEN → raise `CircuitBreakerOpenError` → HTTP 503

#### 3. Retry với Exponential Backoff + Jitter

Retry tối đa **3 lần** với các lỗi: `RateLimitError` (429), `APITimeoutError`, `APIConnectionError`, `InternalServerError` (500/503).

| Lần | Delay (giây) |
|---|---|
| 1 | `1.0 * 2^0 + uniform(0,1)` ≈ 1.3 |
| 2 | `1.0 * 2^1 + uniform(0,1)` ≈ 2.25 |
| 3 | `1.0 * 2^2 + uniform(0,1)` ≈ 4.7 |

Jitter ngẫu nhiên tránh thundering herd (nhiều client retry cùng lúc).

#### 4. Structured Output

```python
await client.beta.chat.completions.parse(
    response_format=LLMOrderStrict,   # Pydantic model → strict JSON schema
    ...
)
```

OpenAI đảm bảo 100% JSON đúng schema. Không cần parse/regex thủ công.

#### 5. Input Guardrail

`len(text) > 500` → raise `ValueError` trước khi gọi API.

#### 6. Post-process Guardrail

- `country` phải là `"VNM"` nếu có địa chỉ
- `address_raw` rỗng/null → xóa trắng toàn bộ `address_info`

---

### `app/pipeline/parser.py`

- `parse()` → `async def parse()` (vì `llm.extract_order` là async)
- `await self.llm.extract_order(llm_input)` thay vì sync call
- `CircuitBreakerOpenError` và `ValueError` được **propagate** ra ngoài thay vì bị nuốt bởi `except Exception`

---

### `main.py`

- `threading.Semaphore` → `asyncio.Semaphore` (non-blocking, phù hợp async FastAPI)
- Semaphore acquire dùng `asyncio.wait_for(..., timeout=...)` → trả 429 khi timeout
- `parse_text` endpoint: `async def` + kiểm tra độ dài input trước
- `CircuitBreakerOpenError` → HTTP 503
- `ValueError` (input quá dài) → HTTP 400 `input_too_long`

---

## Cách chạy

```bash
# Kích hoạt env
conda activate rag

# Chạy server
uvicorn main:app --reload --port 8000

# Test nhanh
curl -X POST http://localhost:8000/parse-text \
  -H "Content-Type: application/json" \
  -d '{"text": "Nguyễn Văn A, 0912345678, 45 Lê Lợi Q1 HCM, giao buổi sáng"}'

# Smoke test script
python test_llm.py
```

---

## Không thay đổi

- `app/pipeline/address_normalizer.py` — chuẩn hóa địa chỉ với DB Vietnam
- `app/pipeline/phone_extractor.py` — regex phone
- `app/pipeline/rule_extractor.py` — rule-based extraction
- `app/pipeline/text_utils.py` — compact text
- `scripts/run_benchmark.py` — benchmark script (vẫn dùng HTTP POST, không đổi)
- `Dockerfile`, `docker-compose.yml`
