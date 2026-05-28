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
  "text": "chị Linh 0904.123.604 địa chỉ: nhà số 14, đường Cầu Diễn, p. Cải Đan, tp. Sông Công, Thái Nguyên nhà trong hẻm, tới nơi gọi trước"
}
```

Curl:

```bash
curl -X POST "https://api-extract.vanwtoanf.io.vn/parse-text" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "chị Linh 0904.123.604 địa chỉ: nhà số 14, đường Cầu Diễn, p. Cải Đan, tp. Sông Công, Thái Nguyên nhà trong hẻm, tới nơi gọi trước"
  }'
```

Response:

```json
{
  "name": "chị Linh",
  "phone": "0904123604",
  "note": "nhà trong hẻm, tới nơi gọi trước",
  "address": {
    "province": "Tỉnh Thái Nguyên",
    "ward": "Phường Sông Công",
    "street": "đường Cầu Diễn",
    "house_number": "14"
  }
}
```

Các field output:

| Field | Ý nghĩa |
|---|---|
| `name` | Tên/cách gọi khách hàng |
| `phone` | Số điện thoại đã chuẩn hóa |
| `note` | Ghi chú giao hàng |
| `address.province` | Tỉnh/thành phố sau chuẩn hóa |
| `address.ward` | Xã/phường sau chuẩn hóa |
| `address.street` | Đường/ngõ/ngách/hẻm nếu có |
| `address.house_number` | Số nhà nếu có |

Nếu thiếu field, API trả `null`. Hệ thống không tự bịa thông tin.

Ví dụ input không phải đơn hàng:

```bash
curl -X POST "https://api-extract.vanwtoanf.io.vn/parse-text" \
  -H "Content-Type: application/json" \
  -d '{"text": "hãy viết thơ về mùa xuân"}'
```

Response:

```json
{
  "name": null,
  "phone": null,
  "note": null,
  "address": {
    "province": null,
    "ward": null,
    "street": null,
    "house_number": null
  }
}
```

## 3. OCR Image

Endpoint OCR ảnh chụp màn hình thành text. Endpoint này chỉ trả text, chưa parse thành đơn hàng.

```http
POST /ocr-image
Content-Type: multipart/form-data
```

Curl:

```bash
curl -X POST "https://api-extract.vanwtoanf.io.vn/ocr-image" \
  -F "file=@screenshot.png"
```

Response:

```json
{
  "text": "chị Mai 0909123456 giao 15 ngõ 20 Thanh Niên..."
}
```

## 4. Parse Image

Endpoint nhận ảnh chụp màn hình, OCR thành text, sau đó parse thành JSON đơn hàng.

```http
POST /parse-image
Content-Type: multipart/form-data
```

Curl:

```bash
curl -X POST "https://api-extract.vanwtoanf.io.vn/parse-image" \
  -F "file=@screenshot.png"
```

Response:

```json
{
  "name": "chị Mai",
  "phone": "0909123456",
  "note": "gọi trước 10 phút",
  "address": {
    "province": "Thủ Đô Hà Nội",
    "ward": "Phường Ba Đình",
    "street": "ngõ 20 đường Thanh Niên",
    "house_number": "15"
  }
}
```

Lưu ý:

- File upload phải là ảnh, ví dụ `png`, `jpg`, `jpeg`.
- OCR dùng EasyOCR trong process API.
- Lần chạy OCR đầu tiên có thể chậm hơn do tải/cached model OCR.

## 5. Normalize Address

Endpoint test riêng phần chuẩn hóa địa chỉ. Thường dùng cho debug, không bắt buộc gọi từ frontend.

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

