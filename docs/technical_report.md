# Báo Cáo Kỹ Thuật: Clipboard Parsing & Smart Delivery Order Creation

## 1. Mục Tiêu

Dự án xây dựng hệ thống tự động bóc tách thông tin đơn giao hàng từ văn bản. Hệ thống hướng tới bối cảnh Social Commerce Việt Nam, nơi nhân viên thường nhận đơn qua Facebook, TikTok, Zalo hoặc livestream với dữ liệu không chuẩn, nhiều viết tắt, sai chính tả và địa chỉ cũ sau sáp nhập hành chính 2025.

Output cuối cùng là JSON chuẩn để tự động điền form tạo đơn:

```json
{
  "recipient_name": "Thuỷ",
  "phone_number": "0855000444",
  "note": "nhớ gọi trước",
  "address_raw": "Quán giằng, thôn hạ, xã an thái, huyện quỳnh phụ, tỉnh thái bình",
  "address_new": "Quán giằng, thôn hạ, Xã A Sào, Hưng Yên",
  "address_info": {
    "address_number": "Quán giằng, thôn hạ",
    "street": null,
    "municipality": "Xã A Sào",
    "sub_region": "Hưng Yên",
    "country": "VNM"
  },
  "lat": 20.6759951,
  "lng": 106.3800439
}
```

---

## 2. Kiến Trúc Tổng Quan

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              KIẾN TRÚC HỆ THỐNG                                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌────────────┐          ┌──────────────────────────────────────────────────┐   │
│   │ Ứng dụng   │  Request │              LỚP API — FastAPI                   │   │
│   │  /Web      │─────────▶├──────────────────────────────────────────────────┤   │
│   │            │          │  POST /parse-text    Phân tích văn bản đơn hàng  │   │
│   └────────────┘          │  POST /feedback      Ghi nhận phản hồi người dùng│   │
│                           │  GET  /health        Kiểm tra trạng thái hệ thống│   │
│                           └────────────┬──────────────────┬──────────────────┘   │
│                                        │                  │                      │
│                                        ▼                  ▼                      │
│               ┌────────────────────────────┐  ┌──────────────────────────────┐   │
│               │     XỬ LÝ ĐƠN HÀNG         │  │    GEOCODING — Goong.io      │   │
│               ├────────────────────────────┤  ├──────────────────────────────┤   │
│               │  ① Trích xuất nhanh       │  │  Thử tối đa 3 dạng địa chỉ:  │   │
│               │    SĐT · Tên · Địa chỉ     │  │    1. Địa chỉ đã chuẩn hóa   │   │
│               │            │               │  │    2. Địa chỉ gốc tin nhắn   │   │
│               │            ▼               │  │    3. Đường + Tỉnh rút gọn   │   │
│               │  ② AI  gpt-4o-mini ───────┼─▶│                              │   │
│               │    Phân tích ngữ nghĩa     │  │  Xác thực đúng tỉnh/thành    │   │
│               │            │               │  │  tránh tọa độ sai vị trí     │   │
│               │            ▼               │  └──────────────┬───────────────┘   │
│               │  ③ Chuẩn hóa địa giới     │                 ▼                   │
│               │    Tên cũ → Tên mới 2025   │           lat / lng                 │
│               └────────────────────────────┘                                     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Luồng Xử Lý Một Request

```
  ┌──────────────────────────────────────────────────┐
  │         NHẬN TIN NHẮN  —  POST /parse-text       │
  └────────────────────────┬─────────────────────────┘
                           │
                           ▼
             ┌─────────────────────────┐  Có   ┌─────────────────────────────────┐
             │   Tin nhắn quá dài?     │──────▶│  400  Tin nhắn vượt 5.000 ký tự │
             │   (giới hạn 5.000 ký tự)│       └─────────────────────────────────┘
             └────────────┬────────────┘
                          │ Không
                          ▼
             ┌─────────────────────────┐  Đầy  ┌─────────────────────────────────┐
             │   Server đang bận       │──────▶│  429  Server đang bận           │
             │   (tải đồng thời cao)   │       │       Vui lòng thử lại sau      │
             └────────────┬────────────┘       └─────────────────────────────────┘
                          │ Còn chỗ
                          ▼
             ┌─────────────────────────┐ Không ┌─────────────────────────────────┐
             │   Có phải đơn hàng?     │──────▶│  Trả về rỗng                    │
             │   (kiểm tra sơ bộ)      │       │  Không gọi AI — tiết kiệm chi phí│
             └────────────┬────────────┘       └─────────────────────────────────┘
                          │ Có
                          ▼
             ┌────────────────────────────────────────────┐
             │  Tiền xử lý                                │
             │  Chuẩn hóa văn bản · Tách số điện thoại    │
             │  Trích xuất hint tên / địa chỉ / ghi chú   │
             └────────────────────────┬───────────────────┘
                                      │
                                      ▼
             ┌────────────────────────────────────────────┐  Lỗi / ┌──────────────────────────┐
             │  AI  gpt-4o-mini                           │ quá tải│  503  Dịch vụ AI tạm thời│
             │  Phân tích tên · ghi chú · địa chỉ         │───────▶│       không khả dụng     │
             └────────────────────────┬───────────────────┘        └──────────────────────────┘
                                      │
                                      ▼
             ┌────────────────────────────────────────────┐
             │  Ghép & hoàn thiện kết quả                 │
             │  SĐT từ regex · Tên · Ghi chú giao hàng    │
             └────────────────────────┬───────────────────┘
                                      │
                                      ▼
             ┌────────────────────────────────────────────┐
             │  Chuẩn hóa địa giới                        │
             │  Map tỉnh / phường cũ  →  tên mới 2025     │
             └────────────────────────┬───────────────────┘
                                      │
                                      ▼
             ┌─────────────────────────┐ Không ┌─────────────────────────────────┐
             │   Địa chỉ hợp lệ?       │──────▶│  422  Không tìm được địa chỉ    │
             └────────────┬────────────┘       └─────────────────────────────────┘
                          │ Có
                          ▼
             ┌────────────────────────────────────────────┐  Thất  ┌──────────────────────────┐
             │  Geocoding  Goong.io                       │  bại  │  422  Không lấy được      │
             │  Thử tối đa 3 lần với 3 dạng địa chỉ       │───────▶│       tọa độ             │
             └────────────────────────┬───────────────────┘        └──────────────────────────┘
                                      │ Thành công
                                      ▼
             ┌──────────────────────────────────────────────────────────────────┐
             │   200  THÀNH CÔNG                                                │
             │   Tên người nhận  ·  Số điện thoại  ·  Ghi chú giao hàng         │
             │   Địa chỉ mới (đã chuẩn hóa)  ·  Tọa độ  lat / lng               │
             └──────────────────────────────────────────────────────────────────┘
```

---

## 4. Hybrid Pipeline — Lý Do Dùng 4 Lớp

Nếu chỉ dùng LLM, hệ thống gặp 3 vấn đề: latency cao, model tự bịa field thiếu, và các trường cấu trúc cố định (số điện thoại) không cần AI. Vì vậy hệ thống dùng pipeline lai 4 lớp:

```
                  ┌──────────────────────┐
                  │    Tin nhắn thô      │
                  │ Facebook · Zalo      │
                  │ TikTok · Livestream  │
                  └──────────┬───────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────┐
  │  LỚP 1 — XỬ LÝ NHANH (rule-based)                    │
  │  • Tách số điện thoại bằng regex (không cần AI)      │
  │  • Chuẩn hóa khoảng trắng, ký tự đặc biệt            │
  │  • Phát hiện từ khóa đơn hàng                        │
  │  • Reject input rõ ràng không phải đơn hàng          │
  └──────────────────────────┬───────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────┐
  │  LỚP 2 — AI  gpt-4o-mini                             │
  │  • Hiểu ngữ nghĩa tự nhiên, viết tắt, sai chính tả   │
  │  • Trích xuất tên người nhận                         │
  │  • Trích xuất ghi chú giao hàng                      │
  │  • Phân tách địa chỉ thành các thành phần            │
  │  • Phân biệt courier với người nhận                  │
  └──────────────────────────┬───────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────┐
  │  LỚP 3 — HẬU XỬ LÝ (rule-based)                      │
  │  • Sửa lỗi phân tách số nhà / tên đường              │
  │  • Bổ sung thông tin còn thiếu từ bước trích xuất    │
  └──────────────────────────┬───────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────┐
  │  LỚP 4 — CHUẨN HÓA ĐỊA GIỚI + GEOCODING              │
  │  • DB 63 tỉnh · hơn 10.000 xã/phường                 │
  │  • Map địa chỉ cũ → tên hành chính mới 2025          │
  │  • Lấy tọa độ lat/lng từ Goong.io                    │
  └──────────────────────────┬───────────────────────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │   JSON chuẩn         │
                  │   + lat / lng        │
                  └──────────────────────┘
```

| Lớp | Vai trò |
|---|---|
| Xử lý nhanh | Phone regex, compact text, hint tên/địa chỉ/note, reject input không hợp lệ |
| gpt-4o-mini | Hiểu ngữ nghĩa linh hoạt: tên khách, note, phân tách địa chỉ, nhận diện courier vs người nhận |
| Hậu xử lý | Sửa lỗi tách số nhà/đường, merge fallback rule → LLM |
| Chuẩn hóa + Geocoding | Chuẩn hóa tỉnh/phường sau sáp nhập, thêm tọa độ lat/lng |

---

## 5. LLM — gpt-4o-mini với Structured Output

Hệ thống gọi OpenAI API với `response_format=LLMOrderStrict` (Pydantic schema) để đảm bảo output luôn đúng cấu trúc JSON, không cần parse thủ công.

**System prompt** (~1200 tokens, static → OpenAI tự cache khi > 1024 tokens):
- 9 luật bắt buộc [R1–R9] bao gồm không bịa dữ liệu, mask phone, nhận diện người nhận, phân tách địa chỉ 2 cấp mới / 3 cấp cũ
- 4 few-shot examples: đơn đơn giản, 2 người, "[Tên] ơi" pattern, đổi địa chỉ

**Schema phân tách địa chỉ**:

```
Địa chỉ đầu vào
  │
  ├── address_number  →  Số nhà / Tên tòa nhà / POI / thôn-xóm-ấp
  ├── street          →  Tên đường / ngõ / hẻm
  ├── neighborhood    →  Xã/phường cũ (chỉ khi địa chỉ 3 cấp hành chính cũ)
  ├── municipality    →  Xã/phường mới  HOẶC  quận/huyện cũ
  ├── sub_region      →  Tỉnh/thành phố
  └── country         →  "VNM"
```

**Lưu ý quan trọng về thôn/xóm/ấp**: Đây là đơn vị dưới xã, không phải cấp hành chính. LLM đưa vào `address_number`, code `_to_internal()` cũng xử lý trường hợp LLM nhầm đặt vào `neighborhood`.

---

## 6. Độ Tin Cậy — Circuit Breaker & Retry

Mọi lời gọi ra bên ngoài (OpenAI, Goong.io) đều đi qua lớp bảo vệ tự động:

```
  ┌──────────────────────────────────────────────────────────────────┐
  │                  CƠ CHẾ BẢO VỆ — CIRCUIT BREAKER                 │
  ├──────────────────────────────────────────────────────────────────┤
  │                                                                  │
  │   ┌────────────────┐   5 lỗi liên tiếp   ┌────────────────────┐  │
  │   │                │────────────────────▶│                    │  │
  │   │  ĐÓNG          │                     │  MỞ                │  │
  │   │  Hoạt động     │◀────────────────────│  Chặn 30 giây      │  │
  │   │  bình thường   │  Thử lại thành công │  Từ chối ngay 503  │  │
  │   └────────┬───────┘                     └────────┬───────────┘  │
  │            │                                      │ Sau 30 giây  │
  │            │                                      ▼              │
  │            │                             ┌────────────────────┐  │
  │            └────────────────────────────▶│  NỬA MỞ            │  │
  │                   Xác nhận phục hồi      │  Gửi 1 request     │  │
  │                                          │  thăm dò           │  │
  │                                          └────────────────────┘  │
  └──────────────────────────────────────────────────────────────────┘

  Mỗi request đều được bảo vệ bởi cơ chế retry tự động:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Lần 1 ──▶ Lỗi ──▶ Chờ ~1s ──▶ Lần 2 ──▶ Lỗi ──▶ Chờ ~2s        │
  │  ──▶ Lần 3 ──▶ Lỗi ──▶ Tăng bộ đếm lỗi Circuit Breaker          │
  └─────────────────────────────────────────────────────────────────┘
```

- **Retry**: tối đa 3 lần (1 + 2 retry), thời gian chờ tăng dần có random jitter
- **Circuit Breaker**: 5 lỗi liên tiếp → chặn 30s → thăm dò → phục hồi
- **Semaphore**: tối đa 20 request AI song song, quá thì xếp hàng chờ, timeout → HTTP 429

---

## 7. Chuẩn Hóa Địa Giới Sau Sáp Nhập 2025

Sáp nhập hành chính 2025 làm nhiều tỉnh, huyện, xã phường đổi tên hoặc gộp vào đơn vị mới. Hệ thống dùng cơ sở dữ liệu địa giới tự crawl từ các trang web chính thống với ánh xạ địa chỉ cũ → mới.

```
  ┌─────────────────────────────────────────────────────────────────┐
  │  Địa chỉ từ đơn hàng                                            │
  │  VD: "xã An Thái, huyện Quỳnh Phụ, tỉnh Thái Bình"              │
  └─────────────────────────────┬───────────────────────────────────┘
                                │
                                ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Bước 1 — Chuẩn hóa key tìm kiếm                                │
  │  Bỏ dấu · Bỏ từ hành chính (tỉnh, huyện, xã...)                 │
  │  Để so sánh chính xác hơn, không phân biệt cách viết            │
  └─────────────────────────────┬───────────────────────────────────┘
                                │
                                ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Bước 2 — Khớp Tỉnh/Thành phố trước                             │
  │  Thu hẹp không gian tìm kiếm xuống 1 tỉnh                       │
  └─────────────────────────────┬───────────────────────────────────┘
                                │
                                ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Bước 3 — Khớp Huyện/Quận cũ (nếu có)                           │
  │  Phân biệt xã cùng tên ở các huyện/tỉnh khác nhau               │
  └─────────────────────────────┬───────────────────────────────────┘
                                │
                                ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Bước 4 — Khớp Xã/Phường trong phạm vi tỉnh đã xác định         │
  └─────────────────────────────┬───────────────────────────────────┘
                                │
                                ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Tính điểm tổng hợp                                             │
  │  Tỉnh × 42%  +  Huyện × 28%  +  Xã/Phường × 30%                 │
  └─────────────────────────────┬───────────────────────────────────┘
                                │
                    ┌───────────┴──────────────┐
               Điểm ≥ 84                   Điểm thấp /
               không trùng lặp             không đủ tin cậy
                    │                          │
                    ▼                          ▼
  ┌──────────────────────────┐  ┌──────────────────────────────────┐
  │  Trả tên MỚI (2025)      │  │  Giữ nguyên địa chỉ gốc          │
  │  Xã A Sào,  Hưng Yên     │  │  Không tự đoán để tránh sai      │
  └──────────────────────────┘  └──────────────────────────────────┘
```

**Lý do ưu tiên tỉnh → huyện → xã**: Nhiều xã/phường cũ trùng tên giữa các tỉnh/huyện. Match từ tỉnh trước thu hẹp không gian tìm kiếm, huyện cũ là hint phân biệt xã cùng tên.

Ví dụ: `xã An Thái, huyện Quỳnh Phụ, tỉnh Thái Bình` → `Xã A Sào, Hưng Yên`

---

## 8. Geocoding — Goong.io

Sau khi chuẩn hóa địa chỉ, hệ thống gọi Goong.io để lấy tọa độ lat/lng. Có cơ chế thử 3 lần với 3 dạng địa chỉ khác nhau để tăng tỷ lệ thành công.

```
  ┌─────────────────────────────────────────────────────────────────┐
  │  GEOCODING — THỬ TUẦN TỰ ĐẾN KHI CÓ KẾT QUẢ HỢP LỆ              │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  Lần thử  ①  Địa chỉ đã chuẩn hóa theo tên mới 2025            │
  │  VD: "Quán giằng, Xã A Sào, Hưng Yên"                           │
  └──────────────────────────────┬──────────────────────────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
         Tìm được &                            Không tìm được /
         đúng tỉnh                             sai tỉnh / centroid
              │                                      │
              ▼                                      ▼
    Trả lat / lng  ✓            ┌─────────────────────────────────────┐
                                │  Lần thử  ②  Địa chỉ gốc từ tin nhắn│
                                │  VD: "xã an thái, huyện quỳnh phụ,  │
                                │       tỉnh thái bình"               │
                                └──────────────────┬──────────────────┘
                                                   │
                                ┌──────────────────┴─────────────────┐
                           Tìm được &                           Không tìm được /
                           đúng tỉnh                            sai tỉnh
                                │                                     │
                                ▼                                     ▼
                      Trả lat / lng  ✓       ┌───────────────────────────────────┐
                                             │  Lần thử  ③  Rút gọn tối đa      │
                                             │  Chỉ: Số nhà + Đường + Tỉnh       │
                                             │  (bỏ phường/quận — tránh lỗi      │
                                             │   tên hành chính cũ/mới)          │
                                             └──────────────────┬────────────────┘
                                                                │
                                             ┌──────────────────┴─────────────────┐
                                        Tìm được &                           Không tìm được /
                                        đúng tỉnh                            sai tỉnh
                                             │                                     │
                                             ▼                                     ▼
                                   Trả lat / lng  ✓             422 — Không lấy được tọa độ
```

**Xác thực tỉnh/thành**: Goong trả tên tỉnh theo hệ cũ → map sang hệ mới qua DB địa giới → so sánh với tỉnh/thành đã xác định. Reject nếu không khớp để tránh trả tọa độ sai tỉnh.

---

## 9. Guardrails

| Tình huống | Xử lý |
|---|---|
| Input > 5000 ký tự | HTTP 400 `input_too_long` |
| Input không phải đơn hàng | trả tất cả `null` trước khi gọi LLM |
| Thiếu thông tin | Giữ `null`, không tự bịa (R1) |
| Phone | Regex xử lý 100%, không qua LLM |
| Địa chỉ không resolve được | HTTP 422 `geocode_failed` |
| OpenAI quá tải | Retry 3 lần → Circuit Breaker → HTTP 503 |

Ví dụ input không hợp lệ:

```text
hãy giải bài toán này cho tôi
```

Output:

```json
{
  "recipient_name": null,
  "phone_number": null,
  "note": null,
  "address_raw": null,
  "address_new": null,
  "address_info": {
    "address_number": null,
    "street": null,
    "municipality": null,
    "sub_region": null,
    "country": null
  },
  "lat": null,
  "lng": null
}
```

---

## 10. Benchmark

Dataset: 300 mẫu, chạy song song concurrency=1 và concurrency=10.

### Accuracy — gpt-4o-mini vs Qwen2.5-3B (vLLM, T4)

| Field | Qwen2.5-3B | gpt-4o-mini | Δ |
|---|---:|---:|---:|
| **Full exact match** | 49.0% | **53.3%** | +4.3 pp |
| phone | 99.0% | **99.3%** | +0.3 pp |
| name | **98.0%** | 91.0% | −7.0 pp |
| note | 84.7% | **88.3%** | +3.6 pp |
| address.province | 74.7% | **89.3%** | +14.6 pp |
| address.ward | 68.7% | **77.0%** | +8.3 pp |
| address.street | 80.7% | **82.7%** | +2.0 pp |
| address.house_number | 85.0% | **87.0%** | +2.0 pp |

### Latency (c=1, sequential)

| Metric | Qwen2.5-3B vLLM | gpt-4o-mini |
|---|---:|---:|
| Mean | 2.34s | **2.23s** |
| P50 | 2.38s | **2.04s** |
| P95 | 2.95s | **2.78s** |
| Max | 3.39s | 4.27s |

\* Max của gpt-4o-mini là outlier do retry khi OpenAI throttle.

### Nhận xét

- gpt-4o-mini vượt trội ở địa chỉ hành chính (`province` +14.6 pp, `ward` +8.3 pp) — hai field khó nhất sau sáp nhập 2025.
- Ngoại lệ duy nhất: `name` — Qwen2.5-3B fine-tuned Việt Nam đạt 98% vs 91%, nhờ học pattern danh xưng anh/chị tốt hơn.
- Phone luôn đạt ~100% ở cả hai model nhờ regex.
- Full exact match thấp hơn field-level vì chỉ cần sai một field là cả đơn bị tính sai.

---

## 11. Chi Phí Vận Hành

Chi phí ước tính trên GCP asia-southeast1. Mỗi request gpt-4o-mini tiêu thụ ~1500 input tokens (system prompt ~1200 + user message ~300) + ~100 output tokens:

| Scenario | Chi phí/request |
|---|---:|
| Không cache (cold start) | ~$0.000285 |
| Có prompt cache | ~$0.000195 |
| **Trung bình thực tế** | **~$0.00025** |

_System prompt ~1200 tokens là static → OpenAI tự cache, giảm ~30% chi phí input._

### Chi phí theo traffic (server e2-small cố định $36/tháng)

| Traffic | API cost/tháng | Server | Tổng/tháng |
|---|---:|---:|---:|
| 1,000 req/ngày | $7.5 | $36 | **~$44** |
| 5,000 req/ngày | $37.5 | $36 | **~$74** |
| 10,000 req/ngày | $75 | $36 | **~$111** |
| 35,000 req/ngày | $263 | $36 | **~$299** |

### Điểm hòa vốn so với self-host T4

| So sánh | Breakeven |
|---|---|
| T4 Spot ($115/tháng) | **~10,000 req/ngày** |
| T4 On-demand ($300/tháng) | **~35,000 req/ngày** |

Dưới ngưỡng breakeven: OpenAI API rẻ hơn và không cần quản lý GPU/vLLM. Trên ngưỡng: chuyển self-host T4 Spot để tiết kiệm.

---

## 12. Hướng Phát Triển

- Cải thiện `name` accuracy: thêm few-shot examples cho các pattern danh xưng phức tạp.
- Thêm confidence score rõ ràng cho từng field để frontend highlight field không chắc.
- Tách benchmark theo nhóm case: viết tắt, địa chỉ cũ, địa chỉ mới, thiếu field, đổi địa chỉ.
- Cache kết quả theo hash input để giảm latency cho tin nhắn lặp lại.
- Khi traffic vượt ~35,000 req/ngày: chuyển sang self-host T4 Spot + Qwen2.5-3B fine-tuned.
