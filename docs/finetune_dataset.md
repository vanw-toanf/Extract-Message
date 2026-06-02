# Fine-tune Dataset Cho Qwen2.5

## Mục tiêu

SLM chỉ học trích xuất địa chỉ thô. Sau inference, `AddressNormalizer` và
`vietnam_administrative.json` mới chuẩn hóa địa chỉ cũ sang địa chỉ mới.

Trước khi gửi text vào model, số điện thoại hợp lệ được thay bằng `[PHONE]`.
Số nhà hoặc mã đơn có hình thức giống số điện thoại vẫn được giữ nguyên.

Ví dụ:

```text
anh Bình sdt 0987654321 Số nhà TT08, KĐT Vinhomes Smart City, Nam Từ Liêm, Hà Nội
```

trở thành:

```text
anh Bình [PHONE] Số nhà TT08, KĐT Vinhomes Smart City, Nam Từ Liêm, Hà Nội
```

## Schema response

```json
{
  "recipient_name": "Bình",
  "phone_number": "[PHONE]",
  "note": null,
  "address_raw": "Số nhà TT08, KĐT Vinhomes Smart City, Nam Từ Liêm, Hà Nội",
  "address_info": {
    "address_number": "TT08",
    "street": "KĐT Vinhomes Smart City",
    "neighborhood": null,
    "municipality": "Nam Từ Liêm",
    "sub_region": "Hà Nội",
    "country": "VNM"
  }
}
```

Quy ước:

| Loại địa chỉ | `neighborhood` | `municipality` | `sub_region` |
|---|---|---|---|
| Địa chỉ cũ 3 cấp | xã/phường cũ | huyện/quận cũ | tỉnh/thành cũ |
| Địa chỉ mới 2 cấp | `null` | xã/phường mới | tỉnh/thành mới |

Trường thiếu hoặc không chắc chắn phải là `null`. Model không được tự suy diễn tỉnh
chỉ dựa trên quận/huyện.

## Sinh dataset

Chạy từ thư mục root của project:

```bash
/home/vantoan/anaconda3/envs/rag/bin/python scripts/generate_finetune_dataset.py
```

Mặc định script sinh:

```text
data/finetune/records_train.jsonl
data/finetune/records_valid.jsonl
data/finetune/dataset_summary.json
```

Có thể thay kích thước dataset:

```bash
/home/vantoan/anaconda3/envs/rag/bin/python scripts/generate_finetune_dataset.py \
  --train-size 4000 \
  --valid-size 500
```

## Đóng gói cho Qwen2.5 SFT

```bash
/home/vantoan/anaconda3/envs/rag/bin/python scripts/package_finetune_qwen.py
```

Output:

```text
data/finetune/qwen_sft/train.jsonl
data/finetune/qwen_sft/valid.jsonl
```

Mỗi dòng là một record chat:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "anh Bình [PHONE] ..."},
    {"role": "assistant", "content": "{\"recipient_name\":\"Bình\", ...}"}
  ]
}
```

## Nguồn dữ liệu

Generator sử dụng:

- `vietnam_admin_db/vietnam_administrative.json` cho địa chỉ cũ và mới.
- `data/benchmark_orders_200.jsonl` và `docs/test_case_plan.md` làm cơ sở thiết kế
  các curated edge cases.
- Các template nhiễu thực tế: viết tắt, xuống dòng, chung cư, KĐT, POI, thiếu field,
  mã đơn giống số điện thoại, số nhà giống số điện thoại và nội dung không phải đơn hàng.

Dataset sinh tự động cũng chủ động trộn các biến thể khó:

- Viết tắt như `x.An Thái`, `h Quỳnh Phụ`, `p. Tân Định`, `q 1`.
- Địa chỉ thiếu xã/phường, ví dụ `94 đường Hoàng Mai, Quận Hoàng Mai, Hà Nội`.
- Địa chỉ thiếu huyện/quận hoặc thiếu tỉnh.
- Địa chỉ thiếu tên đường nhưng vẫn có số nhà và đơn vị hành chính.
- Viết thường, thiếu dấu phẩy hoặc các thành phần dính liền bằng khoảng trắng.
- Thiếu dấu tiếng Việt, ví dụ `tinh Thai Binh, h. Quynh Phu, x. An Thai`.
- Thứ tự lộn ngược, ví dụ tỉnh -> huyện -> xã -> số nhà -> đường.
- Phân biệt người bán/người nhận: gọi tên shop hoặc người bán không đồng nghĩa với
  `recipient_name`; nếu có nhãn `người nhận`, `khách nhận hàng` hoặc `ship cho` thì
  ưu tiên đúng người nhận.

Không dạy SLM tự suy diễn tỉnh khi input bị thiếu tỉnh. Ví dụ `Thủ Đức` không tự
động biến thành `TP.HCM` ở tầng extraction. Nếu cần, nên bổ sung allowlist hậu xử lý
riêng cho một số địa danh đủ chắc chắn như `Thủ Đức -> TP.HCM`.

Phân bố sau mỗi lần sinh được ghi trong `data/finetune/dataset_summary.json`.
