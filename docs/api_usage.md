# Hướng Dẫn Sử Dụng API

Base URL production:

```text
https://api-extract.vanwtoanf.io.vn
```



## 1. Health Check

Kiểm tra API có đang chạy không.

```bash
curl https://api-extract.vanwtoanf.io.vn/health
```

Response:

```json
{
  "status": "ok"
}
```

## 2. Parse Text

Endpoint chính để bóc tách đơn hàng từ tin nhắn text.

```http
POST /parse-text
Content-Type: application/json
```

Request body:

```json
{
  "text": "giao cho chị Loan, phone 0939128599, lấy hàng ở 12 Lý Thái Tổ, giao tới 88 Nguyễn Du, Hà Nội nhé"
}
```

Curl:

```bash
curl -X 'POST' \
  'https://api-extract.vanwtoanf.io.vn/parse-text' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "text": "giao cho chị Loan, phone 0939128599, lấy hàng ở 12 Lý Thái Tổ, giao tới 88 Nguyễn Du, Hà Nội nhé"
}'
```

Response:

```json
{
  "recipient_name": "Loan",
  "phone_number": "0939128599",
  "note": null,
  "address_raw": "88 Nguyễn Du, Hà Nội",
  "address_new": "88 Nguyễn Du, Hà Nội",
  "address_info": {
    "address_number": "88",
    "street": "Nguyễn Du",
    "municipality": null,
    "sub_region": "Hà Nội",
    "country": "VNM"
  },
  "lat": 21.02023955900006,
  "lng": 105.84303579500005
}
```

Các field output:

| Field | Ý nghĩa |
|---|---|
| `recipient_name` | Tên người nhận, đã bỏ cách gọi như `anh`, `chị` |
| `phone_number` | Số điện thoại đã chuẩn hóa |
| `note` | Ghi chú giao hàng |
| `address_raw` | Phần địa chỉ trích nguyên văn từ input |
| `address_new` | Chuỗi địa chỉ cuối sau chuẩn hóa |
| `address_info.address_number` | Số nhà, căn hộ hoặc POI nếu có |
| `address_info.street` | Đường/ngõ/ngách/hẻm nếu có |
| `address_info.municipality` | Xã/phường mới sau chuẩn hóa |
| `address_info.sub_region` | Tỉnh/thành phố mới sau chuẩn hóa |
| `address_info.country` | `VNM` |
| `lat` | Kinh độ |
| `lng` | Vĩ độ |

### Error Codes

| HTTP | detail | Nguyên nhân |
|---|---|---|
| 400 | `input_too_long` | Text > 5000 ký tự |
| 422 | `address_not_found` | Không tìm ra địa chỉ |
| 422 | `geocode_failed` | Goong không resolve được |
| 429 | `Server busy...` | Semaphore queue timeout |
| 503 | `LLM service unavailable` | Circuit breaker OPEN |

---

Ví dụ input không phải đơn hàng:

```bash
curl -X POST "https://api-extract.vanwtoanf.io.vn/parse-text" \
  -H "Content-Type: application/json" \
  -d '{"text": "hãy viết thơ về mùa xuân"}'
```

Response:

Error: response status is 422
```json
{
  "detail": "address_not_found"
}
```

## 3. Normalize Address

Endpoint test riêng phần chuẩn hóa địa chỉ. 

```http
POST /normalize-address
Content-Type: application/json
```

Request:

```json
{
  "province": "Phú Thọ",
  "district_hint": "Thị xã Phú Thọ",
  "ward": "Phường Âu Cơ",
  "street": "ngõ 15 đường Lũy Bán Bích",
  "house_number": "25/3"
}
```

Curl:

```bash
curl -X POST "https://api-extract.vanwtoanf.io.vn/normalize-address" \
  -H "Content-Type: application/json" \
  -d '{
    "province": "Phú Thọ",
    "district_hint": "Thị xã Phú Thọ",
    "ward": "Phường Âu Cơ",
    "street": "ngõ 15 đường Lũy Bán Bích",
    "house_number": "25/3"
  }'
```

Response:

```json
{
  "province": "Tỉnh Phú Thọ",
  "ward": "Phường Âu Cơ",
  "street": "ngõ 15 đường Lũy Bán Bích",
  "house_number": "25/3",
  "is_normalized": true,
  "confidence": 1.0,
  "matched_by": "old_address_mapping",
  "candidates": [
    {
      "province_name": "Tỉnh Phú Thọ",
      "ward_name": "Phường Âu Cơ",
      "province_code": "25",
      "ward_code": "07948",
      "score": 100.0,
      "matched_by": "old_address_mapping",
      "old_province_name": "Tỉnh Phú Thọ",
      "old_district_name": "Thị xã Phú Thọ",
      "old_ward_name": "Phường Âu Cơ"
    }
  ],
  "warnings": []
}
```
