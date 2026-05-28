# Test Case Plan

## Ghi Chú Về Geocoding

Geocoding/Maps API **không bắt buộc** cho lõi hệ thống hiện tại.

Nên tách thành 2 tầng:

```text
Tầng bắt buộc:
Text/Image -> OCR nếu có -> Parsing -> Address normalization -> JSON

Tầng tùy chọn:
Normalized address -> Geocoding/Maps -> lat/lng/is_verified
```

Khi nào cần geocoding:

- Cần tính phí ship theo tọa độ.
- Cần xác minh địa chỉ có tồn tại trên bản đồ.
- Cần định tuyến giao hàng.

Khi nào chưa cần geocoding:

- Chỉ cần autofill form tạo đơn.
- Chỉ cần chuẩn hóa tỉnh/phường sau sáp nhập.
- Muốn tránh chi phí API Maps trong MVP.

Khuyến nghị hiện tại:

- Giữ `/parse-text` trả JSON đơn hàng chuẩn hóa.
- Sau này thêm endpoint riêng `/verify-address` hoặc field optional `is_verified`, `lat`, `lng`.
- Không để geocoding block toàn bộ parsing. Nếu geocode fail, vẫn trả parse result và gắn warning.

## TC-P: Trích Xuất Thông Tin

| ID | Input raw text | Expected output | Note |
|---|---|---|---|
| P-01 | Nguyễn Văn A, 0912345678, 45 Lê Lợi Q1 HCM, giao buổi sáng | name: Nguyễn Văn A; phone: 0912345678; address: 45 Lê Lợi Q1 HCM; note: giao buổi sáng | Happy path |
| P-02 | sdt: 0987654321 - địa chỉ: 12 Trần Hưng Đạo, Đống Đa, Hà Nội | name: null; phone: 0987654321; address: 12 Trần Hưng Đạo, Đống Đa, Hà Nội; note: null | Không có tên |
| P-03 | chị Mai ơi giao cho mình nha, đang ở 88 Nguyễn Du | name: null; phone: null; address: 88 Nguyễn Du; note: null | Tên trong câu gọi không phải người nhận |
| P-04 | Tên: Trần Bích Ngọc \| ĐT: 0901 234 567 \| Địa chỉ: Căn hộ 12B, Chung cư Sunrise, 90 Võ Văn Ngân, Thủ Đức \| Ghi chú: gọi trước 30p | name: Trần Bích Ngọc; phone: 0901234567; address đầy đủ; note: gọi trước 30p | Có nhãn rõ |
| P-05 | order mới nè: 5 áo size M màu đen, ship cho Hùng, 0911222333, 22 Hai Bà Trưng | name: Hùng; phone: 0911222333; address: 22 Hai Bà Trưng; note: null | Bỏ qua thông tin sản phẩm |
| P-06 | không có địa chỉ, tên: Lan, sdt: 0999888777 | error: address_not_found | Fail gracefully |
| P-07 | empty string | HTTP 400 + invalid_input | Input rỗng |
| P-08 | +84 912 345 678 | error: address_not_found | Chỉ có số điện thoại |
| P-09 | Lê Văn Đức, 0812456789, 50 Đinh Tiên Hoàng Q.Bình Thạnh - nhớ ghi "hàng dễ vỡ" lên kiện | note: hàng dễ vỡ; address: 50 Đinh Tiên Hoàng Q.Bình Thạnh | Note trong ngoặc kép |
| P-10 | Nguyễn Thị Hoa\n0934567890\n15 Lý Thường Kiệt, P.14, Q.10 | Parse bình thường | Line break không ảnh hưởng |

## TC-PH: Phone Normalize & Validate

| ID | Input phone/text | Expected phone | Note |
|---|---|---|---|
| PH-01 | 0912 345 678 | 0912345678 | Strip dấu cách |
| PH-02 | 0912-345-678 | 0912345678 | Strip gạch ngang |
| PH-03 | +84912345678 | 0912345678 | +84 -> 0 |
| PH-04 | 84912345678 | 0912345678 | 84xxx -> 0xxx |
| PH-05 | (0912) 345.678 | 0912345678 | Strip ký tự không phải số |
| PH-06 | 091234567 | null | Không đủ 10 số |
| PH-07 | 09123456789 | null | 11 số không hợp lệ |
| PH-09 | 0123456789 | null hoặc map đầu số mới | Tùy có bảng convert đầu số cũ |
| PH-10 | nhà số 0987654321, giao buổi chiều | null | Sau “nhà số” thì không lấy làm phone |
| PH-11 | mã đơn: 0912345678 | null | Sau “mã đơn” thì không lấy làm phone |
| PH-12 | Lan 0901234567, liên hệ shop 0987654321 | phone: 0901234567; phone_count: 2 | Ưu tiên số người nhận |
| PH-13 | 0901234567 hoặc 0987654321 đều được | phone: 0901234567; phone_count: 2 | Fallback lấy số đầu tiên |
| PH-14 | Không có số nào trong text | phone: null | Không block nếu có address |

## TC-A: Autocorrect/Normalize Địa Chỉ

| ID | Raw address | Expected | Kịch bản |
|---|---|---|---|
| A-01 | 45 Le Loi, Q1, TP.HCM | 45 Lê Lợi, Quận 1, TP. Hồ Chí Minh | Viết tắt + thiếu dấu |
| A-02 | Nguyen Hue, Ha Noi | Nguyễn Huệ, Hà Nội | Thiếu dấu |
| A-03 | 45 Lê Lợi, Q1 | 45 Lê Lợi, Quận 1, TP. Hồ Chí Minh | Infer từ Q1 |
| A-04 | HN, Đống Đa, Hàng Bông 18 | 18 Hàng Bông, Đống Đa, Hà Nội | Thứ tự lộn xộn |
| A-05 | 123 đường số 5, P. bình hưng hòa, Bình Tân | 123 Đường số 5, Phường Bình Hưng Hòa, Quận Bình Tân, TP. Hồ Chí Minh | Expand P/Q |
| A-06 | Hàng Bông 18, Đống Đa | 18 Hàng Bông, Đống Đa, Hà Nội | Infer Hà Nội |
| A-07 | địa chỉ không tồn tại @#$% | invalid_address | Không gửi Maps |
| A-08 | Quận 3, HCM | invalid_address | Thiếu số nhà + đường |

## TC-R: API Contract & Response Format

| ID | Scenario | Expected response |
|---|---|---|
| R-01 | Happy path parse + normalize thành công | HTTP 200 + `{name, phone, note, address}` |
| R-02 | Thành công nhưng thiếu name/phone/note | Field thiếu là `null`, không trả chuỗi rỗng |
| R-03 | Phone invalid | `phone: null`, field khác vẫn trả bình thường |
| R-04 | Không tìm thấy address | Target behavior: HTTP 422 + `address_not_found` |
| R-05 | Geocode thất bại | Optional future: HTTP 422 hoặc warning `geocode_failed` |
| R-06 | Tổng thời gian happy path | Target P95 <= 2000ms sau CPU optimization/rule skip |
| R-07 | Raw text > 5000 ký tự | HTTP 400 + `input_too_long` |
| R-08 | Emoji/HTML/ký tự đặc biệt | Sanitize rồi parse hoặc trả `address_not_found` |
| R-09 | Privacy | Không lưu raw text trong DB/log |

## TC-E: Edge Cases & Tiếng Việt

| ID | Input | Expected | Điểm cần chú ý |
|---|---|---|---|
| E-01 | giao cho mình trước 10h sáng nhé, 45 Lê Lợi Q1 | note: giao trước 10h sáng; address: 45 Lê Lợi Q1 | Time constraint |
| E-02 | Text Facebook có `:v :3 😭` | Strip icon/sticker | Nguồn dữ liệu đa dạng |
| E-03 | Số nhà TT08, KĐT Vinhomes Smart City, Nam Từ Liêm, Hà Nội | Address hợp lệ | Khu đô thị |
| E-04 | Trường THPT Chu Văn An, Tây Hồ, Hà Nội | POI/landmark | Cần geocoding nếu muốn tọa độ |
| E-05 | lấy hàng ở 12 Lý Thái Tổ, giao tới 88 Nguyễn Du | Theo rule hiện tại: ưu tiên địa chỉ đầu tiên hoặc cần rule rõ hơn | Có 2 địa chỉ |
| E-06 | Lan ơi ship cho mình 1 cái váy size S nha, mình ở 22 Ngô Quyền, phone mình 0901234567 | name: null; address: 22 Ngô Quyền; phone: 0901234567 | Phân biệt người bán/người nhận |

