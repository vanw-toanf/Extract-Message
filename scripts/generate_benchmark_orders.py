#!/usr/bin/env python3
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_DB = ROOT / "vietnam_admin_db" / "vietnam_administrative.json"
OUTPUT = ROOT / "data" / "benchmark_orders_200.jsonl"


NAMES = [
    "chị Mai",
    "anh Nam",
    "cô Hạnh",
    "b Trâm",
    "chị Linh",
    "anh Dũng",
    "c Trang",
    "bạn Quân",
    "chú Bình",
    "chị Vy",
    "anh Khoa",
    "cô Lan",
    "b Ngọc",
    "chị Thảo",
    "anh Huy",
    "c Phương",
    "bạn Minh",
    "chị Hương",
    "anh Tuấn",
    "cô Hoa",
]

STREETS = [
    "đường Nguyễn Trãi",
    "đường Lê Lợi",
    "đường Trần Phú",
    "phố Hàng Bạc",
    "đường Cầu Diễn",
    "đường Lũy Bán Bích",
    "đường Điện Biên Phủ",
    "đường Hoàng Hoa Thám",
    "đường Nguyễn Văn Cừ",
    "phố Huế",
    "đường Quang Trung",
    "đường Phan Đình Phùng",
    "đường Võ Văn Kiệt",
    "đường Cách Mạng Tháng 8",
    "đường Nguyễn Huệ",
    "đường Lý Thường Kiệt",
]

NOTES = [
    "gọi trước 10 phút",
    "giao giờ hành chính",
    "ship sau 6h tối",
    "thu COD 450k",
    "nhà trong hẻm, tới nơi gọi trước",
    "khách cần gấp trong hôm nay",
    "để hàng ở bảo vệ nếu không nghe máy",
    "giao buổi trưa giúp em",
    "đừng gọi giờ nghỉ trưa",
    "khách chuyển khoản rồi",
    "nhà màu xanh, gần tiệm thuốc",
    "giao cuối giờ chiều",
]


def clean_name(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.split())


def phone_for(index: int) -> str:
    return f"09{index % 100:02d}{(123456 + index * 37) % 1000000:06d}"


def phone_variant(phone: str, index: int) -> str:
    if index % 4 == 0:
        return f"{phone[:4]}.{phone[4:7]}.{phone[7:]}"
    if index % 4 == 1:
        return f"{phone[:4]} {phone[4:7]} {phone[7:]}"
    if index % 4 == 2:
        return f"+84 {phone[1:4]} {phone[4:7]} {phone[7:]}"
    return phone


def house_for(index: int) -> str:
    variants = [
        str(10 + index),
        f"{20 + index}/3",
        f"{index % 9 + 1}A",
        f"{30 + index}B",
    ]
    return variants[index % len(variants)]


def make_street(index: int) -> str:
    street = STREETS[index % len(STREETS)]
    if index % 5 == 0:
        return f"ngõ {index % 80 + 10} {street}"
    if index % 5 == 1:
        return f"hẻm {index % 60 + 5} {street}"
    if index % 5 == 2:
        return f"ngách {index % 30 + 2} ngõ {index % 70 + 11} {street}"
    return street


def load_entries() -> tuple[list[dict], list[dict]]:
    data = json.loads(ADMIN_DB.read_text(encoding="utf-8"))
    old_seen: dict[tuple[str, str, str], dict] = {}
    duplicate_keys: set[tuple[str, str, str]] = set()
    new_entries = []

    for province in data:
        for ward in province.get("wards", []):
            new_entries.append(
                {
                    "input_province": province["province_name"],
                    "input_district": None,
                    "input_ward": ward["ward_name"],
                    "expected_province": province["province_name"],
                    "expected_ward": ward["ward_name"],
                    "source": "new",
                }
            )
            for old in ward.get("merged_from") or []:
                old_province = clean_name(old.get("old_province_name"))
                old_district = clean_name(old.get("old_district_name"))
                old_ward = clean_name(old.get("old_ward_name"))
                if not old_province or not old_district or not old_ward:
                    continue
                key = (old_province, old_district, old_ward)
                entry = {
                    "input_province": old_province,
                    "input_district": old_district,
                    "input_ward": old_ward,
                    "expected_province": province["province_name"],
                    "expected_ward": ward["ward_name"],
                    "source": "old",
                }
                if key in old_seen and (
                    old_seen[key]["expected_province"],
                    old_seen[key]["expected_ward"],
                ) != (entry["expected_province"], entry["expected_ward"]):
                    duplicate_keys.add(key)
                else:
                    old_seen[key] = entry

    old_entries = [v for k, v in old_seen.items() if k not in duplicate_keys]
    return old_entries, new_entries


def short_province(province: str, index: int) -> str:
    lower = province.lower()
    if "hà nội" in lower and index % 3 == 0:
        return "HN"
    if "hồ chí minh" in lower and index % 3 == 0:
        return "HCM"
    if province.startswith("Thành phố "):
        return province.replace("Thành phố ", "TP. ")
    if province.startswith("Thành Phố "):
        return province.replace("Thành Phố ", "TP. ")
    if province.startswith("Tỉnh "):
        return province.replace("Tỉnh ", "")
    if province.startswith("Thủ Đô "):
        return province.replace("Thủ Đô ", "")
    return province


def short_district(district: str | None, index: int) -> str | None:
    if not district:
        return None
    if district.startswith("Quận ") and index % 2 == 0:
        return "q. " + district.removeprefix("Quận ")
    if district.startswith("Huyện ") and index % 2 == 0:
        return "h. " + district.removeprefix("Huyện ")
    if district.startswith("Thành phố ") and index % 2 == 0:
        return "tp. " + district.removeprefix("Thành phố ")
    return district


def short_ward(ward: str, index: int) -> str:
    if ward.startswith("Phường ") and index % 2 == 0:
        return "p. " + ward.removeprefix("Phường ")
    if ward.startswith("Xã ") and index % 2 == 0:
        return "x. " + ward.removeprefix("Xã ")
    if ward.startswith("Thị trấn ") and index % 2 == 0:
        return "tt. " + ward.removeprefix("Thị trấn ")
    return ward


def render_input(entry: dict, index: int) -> tuple[str, dict]:
    name = NAMES[index % len(NAMES)]
    phone = phone_for(index)
    phone_text = phone_variant(phone, index)
    house = house_for(index)
    street = make_street(index)
    note = NOTES[index % len(NOTES)]
    note2 = NOTES[(index + 5) % len(NOTES)]
    province_in = short_province(entry["input_province"], index)
    district_in = short_district(entry["input_district"], index)
    ward_in = short_ward(entry["input_ward"], index)
    admin_tail = ", ".join(part for part in [ward_in, district_in, province_in] if part)
    admin_tail_dash = " - ".join(part for part in [ward_in, district_in, province_in] if part)

    if index % 8 == 0:
        text = (
            f"{name} chốt 1 đơn nha\n"
            f"sđt {phone_text}\n"
            f"ship sn {house} {street}, {admin_tail}\n"
            f"note: {note}"
        )
    elif index % 8 == 1:
        text = (
            f"{name} lấy 2 áo, đt {phone_text}. "
            f"Giao về số {house} {street}, {admin_tail}. "
            f"{note}, {note2}"
        )
    elif index % 8 == 2:
        text = (
            f"{name} {phone_text} đổi địa chỉ nha shop, đừng giao chỗ cũ. "
            f"ĐC mới: {house} {street}, {admin_tail}. "
            f"{note}"
        )
    elif index % 8 == 3:
        text = (
            f"khách {name}, phone {phone_text}, cần giao {house} {street}, "
            f"{admin_tail_dash}; ghi chú {note}"
        )
    elif index % 8 == 4:
        text = (
            f"{name}\n"
            f"{phone_text}\n"
            f"địa chỉ: nhà số {house}, {street}, {admin_tail}\n"
            f"{note}"
        )
    elif index % 8 == 5:
        text = (
            f"Shop ơi đơn của {name}: {phone_text}; "
            f"gửi tới {house} {street}, {admin_tail}; "
            f"ghi chú: {note}"
        )
    elif index % 8 == 6:
        text = (
            f"{name} đặt 3 món\n"
            f"tel {phone_text}\n"
            f"addr {house} {street}, {admin_tail}\n"
            f"{note}"
        )
    else:
        text = (
            f"{name} ib chốt đơn, sdt {phone_text}, "
            f"giao hàng tới {admin_tail}, "
            f"{street}, số nhà {house}; {note}"
        )

    expected = {
        "name": name,
        "phone": phone,
        "note": note if index % 8 not in {1} else f"{note}, {note2}",
        "address": {
            "province": entry["expected_province"],
            "ward": entry["expected_ward"],
            "street": street,
            "house_number": house,
        },
    }
    return text, expected


def main() -> None:
    random.seed(20260527)
    old_entries, new_entries = load_entries()
    random.shuffle(old_entries)
    random.shuffle(new_entries)

    selected = old_entries[:150] + new_entries[:50]
    random.shuffle(selected)

    with OUTPUT.open("w", encoding="utf-8") as f:
        for idx, entry in enumerate(selected, 1):
            text, expected = render_input(entry, idx)
            row = {
                "id": f"bench_{idx:03d}",
                "category": entry["source"],
                "input": text,
                "expected": expected,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(selected)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
