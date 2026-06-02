#!/usr/bin/env python3
import json
import random
import re
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


def recipient_name(value: str | None) -> str | None:
    name = clean_name(value)
    if not name:
        return None
    return re.sub(
        r"^(?:anh|chị|chi|cô|co|chú|chu|bạn|ban|bé|be|b|c|a)\s+",
        "",
        name,
        flags=re.IGNORECASE,
    ) or None


def public_expected(expected: dict) -> dict:
    address = expected["address"]
    first_line = " ".join(
        part for part in (address["house_number"], address["street"]) if part
    )
    address_new = ", ".join(
        part
        for part in (first_line or None, address["ward"], address["province"])
        if part
    ) or None
    return {
        "recipient_name": recipient_name(expected["name"]),
        "phone_number": expected["phone"],
        "note": expected["note"],
        "address_raw": expected.get("_address_raw"),
        "address_new": address_new,
        "address_info": {
            "address_number": address["house_number"],
            "street": address["street"],
            "neighborhood": None,
            "municipality": address["ward"],
            "sub_region": address["province"],
            "country": "VNM" if address_new else None,
        },
    }


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
        "_address_raw": f"{house} {street}, {admin_tail}",
        "address": {
            "province": entry["expected_province"],
            "ward": entry["expected_ward"],
            "street": street,
            "house_number": house,
        },
    }
    return text, expected


def render_edge_case(index: int) -> tuple[str, dict, str]:
    def p(offset: int) -> tuple[str, str]:
        phone = phone_for(500 + index + offset)
        return phone, phone_variant(phone, index + offset)

    cases = []

    apartment_cases = [
        ("Trần Bích Ngọc", "Võ Văn Ngân", "Căn hộ 12B, Chung cư Sunrise, 90", "đường Võ Văn Ngân", "Thủ Đức", None, "gọi trước 30p"),
        ("chị Thu", "Vinhomes Ocean Park", "Căn hộ B1205, Tòa S2.03", "Vinhomes Ocean Park", "Gia Lâm", "Thủ Đô Hà Nội", "ship sau 6h"),
        ("anh Quang", "Masteri Thảo Điền", "Block T2 căn 1808", "Masteri Thảo Điền", "Thảo Điền", None, "để lễ tân"),
        ("cô Yến", "Nguyễn Hữu Cảnh", "Căn A1902, The Manor", "đường Nguyễn Hữu Cảnh", "Bình Thạnh", "Thành Phố Hồ Chí Minh", "gọi bảo vệ"),
        ("chị Oanh", "Goldmark City", "Tòa R4 căn 2510", "Goldmark City", "Bắc Từ Liêm", "Thủ Đô Hà Nội", "giao tối"),
        ("anh Lâm", "Hồng Hà", "Căn 09.12 Botanica Premier", "đường Hồng Hà", "Tân Bình", None, "gọi trước"),
        ("bạn Nhi", "Saigon Pearl", "Tòa Ruby 1 căn 1205", "Saigon Pearl", "Bình Thạnh", "Thành Phố Hồ Chí Minh", None),
        ("chị Hà", "Eco Green", "Căn B-2211", "Eco Green Sài Gòn", "Quận 7", None, "thu COD 320k"),
        ("anh Sơn", "River Gate", "Căn Officetel A.08.06", "River Gate", "Quận 4", "Thành Phố Hồ Chí Minh", "giao giờ hành chính"),
        ("cô Thảo", "Imperia Garden", "Tòa B căn 1702", "Imperia Garden", "Thanh Xuân", "Thủ Đô Hà Nội", "khách chuyển khoản rồi"),
    ]
    for i, (name, label, house, street, ward, province, note) in enumerate(apartment_cases):
        phone, phone_text = p(i)
        province_text = f", {province}" if province else ""
        cases.append(
            (
                f"{name} {phone_text} giao {house}, {label}, {ward}{province_text}"
                + (f", note: {note}" if note else ""),
                {
                    "name": name,
                    "phone": phone,
                    "note": note,
                    "address": {
                        "province": province,
                        "ward": ward,
                        "street": street,
                        "house_number": house,
                    },
                },
                "apartment_or_building",
            )
        )

    urban_cases = [
        ("chị Hạnh", "TT08", "KĐT Vinhomes Smart City", "Nam Từ Liêm", "Thủ Đô Hà Nội"),
        ("anh Toàn", "LK12-08", "KĐT Văn Phú", "Hà Đông", "Thủ Đô Hà Nội"),
        ("chị Diễm", "SH05", "KĐT Sala", "Thủ Đức", None),
        ("anh Bảo", "Căn S3.1201", "Vinhomes Grand Park", "Thủ Đức", "Thành Phố Hồ Chí Minh"),
        ("cô Mai", "A18-03", "KĐT Ecopark", "Văn Giang", "Tỉnh Hưng Yên"),
        ("bạn Khánh", "BT2-17", "KĐT Ciputra", "Tây Hồ", "Thủ Đô Hà Nội"),
        ("chị Dung", "N12", "KĐT Đặng Xá", "Gia Lâm", None),
        ("anh Hiếu", "Căn C0907", "Celadon City", "Tân Phú", "Thành Phố Hồ Chí Minh"),
        ("chị Giang", "TT21", "KĐT Phú Mỹ Hưng", "Quận 7", "Thành Phố Hồ Chí Minh"),
        ("anh Đức", "B5-1206", "KĐT Times City", "Hai Bà Trưng", "Thủ Đô Hà Nội"),
    ]
    for i, (name, house, street, ward, province) in enumerate(urban_cases, 20):
        phone, phone_text = p(i)
        province_text = f", {province}" if province else ""
        cases.append(
            (
                f"{name} {phone_text} ship số nhà {house}, {street}, {ward}{province_text}, gọi trước",
                {
                    "name": name,
                    "phone": phone,
                    "note": "gọi trước",
                    "address": {
                        "province": province,
                        "ward": ward,
                        "street": street,
                        "house_number": house,
                    },
                },
                "urban_area",
            )
        )

    poi_cases = [
        ("anh Long", "Trường THPT Chu Văn An", "Tây Hồ", "Thủ Đô Hà Nội", "giao buổi sáng"),
        ("chị Bảo", "Bệnh viện Bạch Mai", "Đống Đa", "Thủ Đô Hà Nội", "gọi khi tới cổng"),
        ("cô Vân", "Đại học Sư phạm TP.HCM", "Quận 5", "Thành Phố Hồ Chí Minh", None),
        ("anh Phú", "Nhà thờ Đức Bà", "Quận 1", "Thành Phố Hồ Chí Minh", "giao sau 3h"),
        ("chị Tâm", "Chợ Bến Thành", "Quận 1", "Thành Phố Hồ Chí Minh", "đứng cổng chính"),
        ("bạn My", "Ga Hà Nội", "Đống Đa", "Thủ Đô Hà Nội", "gọi trước 5p"),
        ("anh Khang", "Bến xe Miền Đông mới", "Thủ Đức", None, "ship trong hôm nay"),
        ("chị Ngân", "Aeon Mall Long Biên", "Long Biên", "Thủ Đô Hà Nội", None),
        ("cô Hòa", "Lotte Mall Tây Hồ", "Tây Hồ", "Thủ Đô Hà Nội", "để quầy lễ tân"),
        ("anh Tín", "Sân bay Tân Sơn Nhất", "Tân Bình", "Thành Phố Hồ Chí Minh", "giao gấp"),
    ]
    for i, (name, poi, ward, province, note) in enumerate(poi_cases, 40):
        phone, phone_text = p(i)
        province_text = f", {province}" if province else ""
        cases.append(
            (
                f"{name} {phone_text} gửi tới {poi}, {ward}{province_text}"
                + (f", {note}" if note else ""),
                {
                    "name": name,
                    "phone": phone,
                    "note": note,
                    "address": {
                        "province": province,
                        "ward": ward,
                        "street": None,
                        "house_number": poi,
                    },
                },
                "poi_or_landmark",
            )
        )

    district_cases = [
        ("Nguyễn Văn A", "45", "đường Lê Lợi", "Quận 1", "Thành Phố Hồ Chí Minh", "giao buổi sáng"),
        ("chị Minh", "12", "đường Trần Hưng Đạo", "Đống Đa", "Thủ Đô Hà Nội", None),
        ("anh Quốc", "18", "phố Hàng Bông", "Đống Đa", None, "đừng gọi giờ nghỉ trưa"),
        ("cô Lan", None, None, "Quận 3", "Thành Phố Hồ Chí Minh", None),
        ("chị Như", "77", "đường Nguyễn Huệ", "Quận 1", None, "ship trưa"),
        ("anh Việt", "50", "đường Đinh Tiên Hoàng", "Quận Bình Thạnh", "Thành Phố Hồ Chí Minh", "hàng dễ vỡ"),
        ("chị Hương", "22", "đường Hai Bà Trưng", None, None, None),
        ("anh Lợi", "88", "đường Nguyễn Du", None, None, None),
        ("cô Hạnh", "15", "đường Lý Thường Kiệt", "Quận 10", "Thành Phố Hồ Chí Minh", None),
        ("chị Ngọc", "5A", "đường Quang Trung", "Hà Đông", "Thủ Đô Hà Nội", "giao cuối giờ chiều"),
    ]
    for i, (name, house, street, ward, province, note) in enumerate(district_cases, 60):
        phone, phone_text = p(i)
        address_bits = [bit for bit in (house, street, ward, province) if bit]
        cases.append(
            (
                f"{name}, {phone_text}, {', '.join(address_bits)}"
                + (f", {note}" if note else ""),
                {
                    "name": name,
                    "phone": phone,
                    "note": note,
                    "address": {
                        "province": province,
                        "ward": ward,
                        "street": street,
                        "house_number": house,
                    },
                },
                "district_or_missing_admin",
            )
        )

    noisy_cases = [
        ("nhà số 0987654321, giao buổi chiều", None, None, "giao buổi chiều", None, None, None, "0987654321", "phone_like_house_number"),
        ("mã đơn: 0912345678, giao 22 Ngô Quyền", None, None, None, None, None, "đường Ngô Quyền", "22", "phone_like_order_code"),
        ("Lan ơi ship cho mình 1 cái váy size S nha, mình ở 22 Ngô Quyền, phone mình 0901234567", None, "0901234567", None, None, None, "đường Ngô Quyền", "22", "seller_name_not_receiver"),
        ("anh Phúc 09123456789 giao 18 Hàng Bông, Đống Đa, Hà Nội", "anh Phúc", None, None, "Thủ Đô Hà Nội", "Đống Đa", "phố Hàng Bông", "18", "invalid_long_phone"),
        ("chị Vy 091234567 giao 18 Hàng Bông, Đống Đa, Hà Nội", "chị Vy", None, None, "Thủ Đô Hà Nội", "Đống Đa", "phố Hàng Bông", "18", "invalid_short_phone"),
        ("2 số điện thoại: Lan 0901234567, liên hệ shop 0987654321, giao 22 Ngô Quyền", "Lan", "0901234567", None, None, None, "đường Ngô Quyền", "22", "two_phones_prefer_receiver"),
        ("giao cho mình trước 10h sáng nhé, 45 Lê Lợi Q1, HCM, 0978123456", None, "0978123456", "giao trước 10h sáng", "Thành Phố Hồ Chí Minh", "Quận 1", "đường Lê Lợi", "45", "time_note"),
        ("chị Mai :v :3 😭 ship 22 Ngô Quyền nha 0979144879", "chị Mai", "0979144879", None, None, None, "đường Ngô Quyền", "22", "emoji_sticker"),
        ("order mới: áo size M màu đen, ship cho Hùng, 0911222333, 22 Hai Bà Trưng", "Hùng", "0911222333", None, None, None, "đường Hai Bà Trưng", "22", "ignore_product_info"),
        ("Lê Văn Đức, 0812456789, 50 Đinh Tiên Hoàng Q.Bình Thạnh - nhớ ghi \"hàng dễ vỡ\" lên kiện", "Lê Văn Đức", "0812456789", "hàng dễ vỡ", "Thành Phố Hồ Chí Minh", "Quận Bình Thạnh", "đường Đinh Tiên Hoàng", "50", "quoted_note"),
    ]
    for text, name, phone, note, province, ward, street, house, category in noisy_cases:
        cases.append(
            (
                text,
                {
                    "name": name,
                    "phone": phone,
                    "note": note,
                    "address": {
                        "province": province,
                        "ward": ward,
                        "street": street,
                        "house_number": house,
                    },
                },
                category,
            )
        )

    old_admin_cases = [
        ("anh Dũng 0905123641 gửi tới 25/3 ngõ 15 đường Lũy Bán Bích, Phường Âu Cơ, Thị xã Phú Thọ, Phú Thọ; ghi chú: khách cần gấp trong hôm nay", "anh Dũng", "0905123641", "khách cần gấp trong hôm nay", "Tỉnh Phú Thọ", "Phường Âu Cơ", "ngõ 15 đường Lũy Bán Bích", "25/3"),
        ("anh Nam 0961125713 gửi tới 81/3 hẻm 6 đường Cách Mạng Tháng 8, Xã Thạnh Phú, Huyện Thạnh Hóa, Long An; ghi chú: giao giờ hành chính", "anh Nam", "0961125713", "giao giờ hành chính", "Tỉnh Tây Ninh", "Xã Thạnh Phước", "hẻm 6 đường Cách Mạng Tháng 8", "81/3"),
        ("chị Mai 0909123456 giao số 15 ngõ 20 đường Thanh Niên, phường Quán Thánh, quận Ba Đình, Hà Nội, gọi trước 10 phút", "chị Mai", "0909123456", "gọi trước 10 phút", "Thủ Đô Hà Nội", "Phường Ba Đình", "ngõ 20 đường Thanh Niên", "15"),
        ("cô Hạnh 0912345678 ĐC mới: 27/3 đường Cầu Diễn, p Cầu Diễn, q Nam Từ Liêm, Hà Nội, tới nơi gọi trước", "cô Hạnh", "0912345678", "tới nơi gọi trước", "Thủ Đô Hà Nội", "Phường Từ Liêm", "đường Cầu Diễn", "27/3"),
        ("anh Nam 0987654321 ship sn 8 ngách 12 ngõ 99 phố Hàng Bạc, p. Hàng Bạc, q Hoàn Kiếm, HN, giao sau 6h tối", "anh Nam", "0987654321", "giao sau 6h tối", "Thủ Đô Hà Nội", "Phường Hoàn Kiếm", "ngách 12 ngõ 99 phố Hàng Bạc", "8"),
    ]
    for text, name, phone, note, province, ward, street, house in old_admin_cases:
        cases.append(
            (
                text,
                {
                    "name": name,
                    "phone": phone,
                    "note": note,
                    "address": {
                        "province": province,
                        "ward": ward,
                        "street": street,
                        "house_number": house,
                    },
                },
                "old_admin_edge",
            )
        )

    diverse_cases = [
        (
            "chị Liên 0908123456 ship đến Cổng A Bệnh viện Đại học Y Dược, 215 Hồng Bàng, Q5, tphcm, gọi em trước 5p",
            "chị Liên",
            "0908123456",
            "gọi trước 5p",
            "Thành Phố Hồ Chí Minh",
            "Quận 5",
            "đường Hồng Bàng",
            "Cổng A Bệnh viện Đại học Y Dược, 215",
            "poi_with_street_number",
        ),
        (
            "anh Khải đặt 1 đôi giày, giao 30 Nguyễn Chí Thanh, Ba Đình, Hà Nội, sdt shop đừng lấy 0988888888, khách 0916000111",
            "anh Khải",
            "0916000111",
            None,
            "Thủ Đô Hà Nội",
            "Ba Đình",
            "đường Nguyễn Chí Thanh",
            "30",
            "two_phones_shop_noise",
        ),
        (
            "bảo vệ nhận giúp: chị Quyên, căn 1206 tòa G3, Five Star Garden, số 2 Kim Giang, Thanh Xuân, HN, 0933000222",
            "chị Quyên",
            "0933000222",
            "bảo vệ nhận giúp",
            "Thủ Đô Hà Nội",
            "Thanh Xuân",
            "đường Kim Giang",
            "căn 1206 tòa G3, Five Star Garden, số 2",
            "apartment_with_receiver_note_first",
        ),
        (
            "ship cho anh Hòa ở 7A/12 Thành Thái, P.14, Q.10, TP.HCM - hàng dễ vỡ - 0977000333",
            "anh Hòa",
            "0977000333",
            "hàng dễ vỡ",
            "Thành Phố Hồ Chí Minh",
            "Phường 14",
            "đường Thành Thái",
            "7A/12",
            "slash_house_ward_number",
        ),
        (
            "chị Thuỷ 0855000444 nhà trong hẻm 43/8/2 đường Ung Văn Khiêm, Bình Thạnh, nhớ gọi trước",
            "chị Thuỷ",
            "0855000444",
            "nhớ gọi trước",
            None,
            "Bình Thạnh",
            "hẻm 43/8/2 đường Ung Văn Khiêm",
            None,
            "missing_province_deep_alley",
        ),
        (
            "Người nhận: Minh Anh | ĐT 0844000555 | 15 Nguyễn Văn Linh, Hải Châu, Đà Nẵng | note giao giờ hành chính",
            "Minh Anh",
            "0844000555",
            "giao giờ hành chính",
            "Thành phố Đà Nẵng",
            "Hải Châu",
            "đường Nguyễn Văn Linh",
            "15",
            "pipe_format_central_city",
        ),
        (
            "Cô Sáu 0377000666 gửi về số 4 chợ Đà Lạt, phường 1, Đà Lạt, Lâm Đồng, lấy tiền ship khách",
            "Cô Sáu",
            "0377000666",
            "lấy tiền ship khách",
            "Tỉnh Lâm Đồng",
            "Phường 1",
            "chợ Đà Lạt",
            "số 4",
            "market_landmark_old_style",
        ),
        (
            "ship 2 thùng cho nhà thuốc An Khang, 109 Trần Hưng Đạo, P. Cầu Kho, Q1, HCM, 0966000777",
            "nhà thuốc An Khang",
            "0966000777",
            None,
            "Thành Phố Hồ Chí Minh",
            "Phường Cầu Kho",
            "đường Trần Hưng Đạo",
            "109",
            "business_name_receiver",
        ),
        (
            "em ở sau lưng UBND phường, địa chỉ 12/5 Nguyễn Văn Cừ, Long Biên, Hà Nội, tên Hà 0833000888",
            "Hà",
            "0833000888",
            "sau lưng UBND phường",
            "Thủ Đô Hà Nội",
            "Long Biên",
            "đường Nguyễn Văn Cừ",
            "12/5",
            "descriptive_note_plus_address",
        ),
        (
            "A Nam - 0919000999 - kiệt 27 Hải Phòng, Thạch Thang, Hải Châu, Đà Nẵng, giao buổi chiều",
            "A Nam",
            "0919000999",
            "giao buổi chiều",
            "Thành phố Đà Nẵng",
            "Thạch Thang",
            "kiệt 27 đường Hải Phòng",
            None,
            "central_vietnam_alley",
        ),
        (
            "chị Hồng nhận ở 21B Lạch Tray, Ngô Quyền, Hải Phòng, phone +84 912 000 101",
            "chị Hồng",
            "0912000101",
            None,
            "Thành phố Hải Phòng",
            "Ngô Quyền",
            "đường Lạch Tray",
            "21B",
            "phone_plus84_hai_phong",
        ),
        (
            "giao tới Khoa Cấp cứu BV Chợ Rẫy, 201B Nguyễn Chí Thanh, Q5, Sài Gòn, liên hệ chị Nga 0902000202",
            "chị Nga",
            "0902000202",
            None,
            "Thành Phố Hồ Chí Minh",
            "Quận 5",
            "đường Nguyễn Chí Thanh",
            "Khoa Cấp cứu BV Chợ Rẫy, 201B",
            "hospital_department",
        ),
        (
            "chị Duyên, 0934444555, Ấp 2 xã Phú Hữu, huyện Nhơn Trạch, Đồng Nai, nhà cạnh cây xăng",
            "chị Duyên",
            "0934444555",
            "nhà cạnh cây xăng",
            "Tỉnh Đồng Nai",
            "xã Phú Hữu",
            "Ấp 2",
            None,
            "rural_hamlet",
        ),
        (
            "Anh Long 0905555666 gửi về 56 Nguyễn Tất Thành, TP Quy Nhơn, Bình Định, khách cần gấp",
            "Anh Long",
            "0905555666",
            "khách cần gấp",
            "Tỉnh Bình Định",
            "TP Quy Nhơn",
            "đường Nguyễn Tất Thành",
            "56",
            "city_level_district",
        ),
        (
            "địa chỉ mới của Phương: 17 Yết Kiêu, Hoàn Kiếm, HN; sđt 0399999000; bỏ địa chỉ cũ ở Cầu Giấy",
            "Phương",
            "0399999000",
            "bỏ địa chỉ cũ ở Cầu Giấy",
            "Thủ Đô Hà Nội",
            "Hoàn Kiếm",
            "đường Yết Kiêu",
            "17",
            "new_address_overrides_old",
        ),
        (
            "ship cho cô Hoa 0881234000: 3/2A Nguyễn Oanh, Gò Vấp, mai giao trước 11h",
            "cô Hoa",
            "0881234000",
            "mai giao trước 11h",
            None,
            "Gò Vấp",
            "đường Nguyễn Oanh",
            "3/2A",
            "missing_province_hcm_district",
        ),
        (
            "bé Trang 0791111222 nhận tại TTTM Vincom Plaza Xuân Khánh, Ninh Kiều, Cần Thơ",
            "bé Trang",
            "0791111222",
            None,
            "Thành phố Cần Thơ",
            "Ninh Kiều",
            "Vincom Plaza Xuân Khánh",
            None,
            "mall_in_can_tho",
        ),
        (
            "chị Kiều 0322222333, 9 Trần Phú, P. Lộc Thọ, Nha Trang, Khánh Hòa, gọi khi tới nơi",
            "chị Kiều",
            "0322222333",
            "gọi khi tới nơi",
            "Tỉnh Khánh Hòa",
            "Phường Lộc Thọ",
            "đường Trần Phú",
            "9",
            "coastal_city_ward",
        ),
        (
            "anh Trung ở hẻm 12, số 6, đường 30/4, Ninh Kiều, Cần Thơ, 0703333444",
            "anh Trung",
            "0703333444",
            None,
            "Thành phố Cần Thơ",
            "Ninh Kiều",
            "hẻm 12 đường 30/4",
            "số 6",
            "street_name_with_slash",
        ),
        (
            "0904444555 là số khách, giao đến 1 Nguyễn Ái Quốc, Biên Hòa, Đồng Nai, tên anh Bình",
            "anh Bình",
            "0904444555",
            None,
            "Tỉnh Đồng Nai",
            "Biên Hòa",
            "đường Nguyễn Ái Quốc",
            "1",
            "phone_first_name_last",
        ),
        (
            "chị Nhàn cần giao ở tổ 5, khu phố 3, phường Tân Phong, Biên Hòa, Đồng Nai, 0915555666",
            "chị Nhàn",
            "0915555666",
            None,
            "Tỉnh Đồng Nai",
            "Phường Tân Phong",
            "tổ 5, khu phố 3",
            None,
            "neighborhood_no_house",
        ),
        (
            "đừng lấy sđt trên bill 0900000000, người nhận là Tuấn 0826666777, 101 Pasteur, Q1, HCM",
            "Tuấn",
            "0826666777",
            "đừng lấy sđt trên bill",
            "Thành Phố Hồ Chí Minh",
            "Quận 1",
            "đường Pasteur",
            "101",
            "ignore_bill_phone",
        ),
        (
            "Ms Trang, 0347777888, phòng 802 tòa nhà Bitexco, 2 Hải Triều, Q1, tphcm, giao trong giờ trưa",
            "Ms Trang",
            "0347777888",
            "giao trong giờ trưa",
            "Thành Phố Hồ Chí Minh",
            "Quận 1",
            "đường Hải Triều",
            "phòng 802 tòa nhà Bitexco, 2",
            "office_building",
        ),
        (
            "giao giúp em tới nhà văn hóa thôn Đông, xã Phù Đổng, Gia Lâm, Hà Nội, liên hệ 0568888999",
            None,
            "0568888999",
            None,
            "Thủ Đô Hà Nội",
            "Xã Phù Đổng",
            "nhà văn hóa thôn Đông",
            None,
            "communal_landmark",
        ),
        (
            "chị Bích 0359999001, gửi tới Bưu điện trung tâm Sài Gòn, Công xã Paris, Q1, HCM, khách tự ra nhận",
            "chị Bích",
            "0359999001",
            "khách tự ra nhận",
            "Thành Phố Hồ Chí Minh",
            "Quận 1",
            "đường Công xã Paris",
            "Bưu điện trung tâm Sài Gòn",
            "landmark_plus_street_no_number",
        ),
    ]
    for text, name, phone, note, province, ward, street, house, category in diverse_cases:
        cases.append(
            (
                text,
                {
                    "name": name,
                    "phone": phone,
                    "note": note,
                    "address": {
                        "province": province,
                        "ward": ward,
                        "street": street,
                        "house_number": house,
                    },
                },
                category,
            )
        )

    text, expected, category = cases[index % len(cases)]
    return text, expected, category


def main() -> None:
    random.seed(20260527)
    old_entries, new_entries = load_entries()
    random.shuffle(old_entries)
    random.shuffle(new_entries)

    selected = old_entries[:165] + new_entries[:55]
    random.shuffle(selected)

    with OUTPUT.open("w", encoding="utf-8") as f:
        for idx, entry in enumerate(selected, 1):
            text, expected = render_input(entry, idx)
            row = {
                "id": f"bench_{idx:03d}",
                "category": entry["source"],
                "input": text,
                "expected": public_expected(expected),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        for edge_idx in range(80):
            text, expected, category = render_edge_case(edge_idx)
            row = {
                "id": f"bench_{len(selected) + edge_idx + 1:03d}",
                "category": f"edge_{category}",
                "input": text,
                "expected": public_expected(expected),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(selected) + 80} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
