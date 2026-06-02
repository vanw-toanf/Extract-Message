#!/usr/bin/env python3
"""Generate masked Vietnamese delivery-order extraction records for SFT."""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pipeline.phone_extractor import mask_phone
from app.pipeline.text_utils import compact_text, strip_accents


DEFAULT_DB = ROOT / "vietnam_admin_db" / "vietnam_administrative.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "finetune"
COUNTRY = "VNM"

NAMES = [
    "anh Bình",
    "chị Mai",
    "cô Hạnh",
    "chú Nam",
    "bạn Linh",
    "chị Vy",
    "anh Khoa",
    "cô Lan",
    "chị Hương",
    "anh Tuấn",
    "b Ngọc",
    "c Trang",
    "chị Thảo",
    "anh Huy",
    "cô Hoa",
    "bạn Minh",
]

FULL_NAMES = [
    "Nguyễn Thị Hoa",
    "Trần Văn Bình",
    "Lê Thị Mai",
    "Phạm Văn Nam",
    "Hoàng Thị Lan",
    "Vũ Văn Hùng",
    "Đặng Thị Ngọc",
    "Bùi Văn Tuấn",
    "Ngô Thị Hương",
    "Đỗ Văn Khoa",
    "Trần Bích Ngọc",
    "Lê Văn Đức",
    "Nguyễn Minh Quân",
    "Phạm Thị Duyên",
    "Hoàng Văn Phúc",
    "Vũ Thị Thảo",
    "anh Nguyễn Văn Tùng",
    "chị Trần Thị Hà",
    "cô Lê Thị Phương",
    "anh Phạm Minh Đức",
]

STREETS = [
    "đường Nguyễn Văn Cừ",
    "đường Lê Lợi",
    "đường Trần Phú",
    "phố Hàng Bạc",
    "đường Cầu Diễn",
    "đường Lũy Bán Bích",
    "đường Điện Biên Phủ",
    "đường Hoàng Hoa Thám",
    "đường Quang Trung",
    "đường Võ Văn Kiệt",
    "đường Cách Mạng Tháng 8",
    "đường Lý Thường Kiệt",
    "đường Phan Đình Phùng",
    "đường Nguyễn Huệ",
]

NOTES = [
    None,
    "gọi trước 10 phút",
    "giao giờ hành chính",
    "ship sau 6h tối",
    "đừng gọi giờ nghỉ trưa",
    "nhà trong hẻm, tới nơi gọi trước",
    "để hàng ở bảo vệ nếu không nghe máy",
    "khách chuyển khoản rồi",
]

SELLER_NAMES = ["Lan", "Mai", "Hương", "Trang", "Ngọc", "Linh", "Vy", "Thảo",
                "Quỳnh", "Hà", "Dung", "Phương"]
RECEIVER_NAMES = ["Hùng", "Bình", "Hoa", "Nam", "Quân", "Duyên", "Phúc", "Minh",
                  "Quỳnh Anh", "Minh Tuấn", "Bích Ngọc", "Thanh Hà"]
PARTICLES = ["nhé", "nha", "nhen", "ạ", "ha"]
DELIVERY_PREFIXES = ["anh", "chị", "cô", "bạn"]

HONORIFIC_RE = re.compile(
    r"^(?:anh|chị|chi|cô|co|chú|chu|bạn|ban|bé|be|b|c|a)\s+",
    flags=re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--train-size", type=int, default=10000)
    parser.add_argument("--valid-size", type=int, default=2500)
    parser.add_argument("--seed", type=int, default=20260601)
    return parser.parse_args()


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def recipient_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = HONORIFIC_RE.sub("", name.strip())
    return cleaned or None


def phone_for(index: int) -> str:
    prefixes = ["090", "091", "093", "096", "097", "098", "032", "035", "070", "083"]
    return f"{prefixes[index % len(prefixes)]}{(1234567 + index * 7919) % 10000000:07d}"


def phone_variant(phone: str, index: int) -> str:
    variants = [
        phone,
        f"{phone[:4]}.{phone[4:7]}.{phone[7:]}",
        f"{phone[:4]} {phone[4:7]} {phone[7:]}",
        f"+84 {phone[1:4]} {phone[4:7]} {phone[7:]}",
    ]
    return variants[index % len(variants)]


def house_for(index: int) -> str:
    variants = [
        str(index % 180 + 1),
        f"{index % 80 + 1}/3",
        f"{index % 35 + 1}A",
        f"{index % 25 + 1}B/2",
    ]
    return variants[index % len(variants)]


def street_for(index: int) -> str:
    street = STREETS[index % len(STREETS)]
    variants = [
        street,
        f"ngõ {index % 50 + 4} {street}",
        f"hẻm {index % 40 + 3} {street}",
        f"ngách {index % 20 + 2} ngõ {index % 60 + 5} {street}",
    ]
    return variants[index % len(variants)]


def abbreviate_admin(value: str | None, dotted: bool = True) -> str | None:
    if not value:
        return None
    prefixes = [
        ("Thành Phố ", "tp. " if dotted else "tp "),
        ("Thành phố ", "tp. " if dotted else "tp "),
        ("Thủ Đô ", ""),
        ("Thủ đô ", ""),
        ("Thị trấn ", "tt. " if dotted else "tt "),
        ("Thị xã ", "tx. " if dotted else "tx "),
        ("Phường ", "p. " if dotted else "p "),
        ("Huyện ", "h. " if dotted else "h "),
        ("Quận ", "q. " if dotted else "q "),
        ("Tỉnh ", "tỉnh " if dotted else ""),
        ("Xã ", "x." if dotted else "x "),
    ]
    for prefix, replacement in prefixes:
        if value.startswith(prefix):
            return replacement + value.removeprefix(prefix)
    return value


def join_address(parts: list[str | None], separator: str = ", ") -> str:
    return separator.join(part for part in parts if part)


def new_response(
    name: str | None,
    has_phone: bool,
    note: str | None,
    address_raw: str | None,
    address_number: str | None,
    street: str | None,
    municipality: str | None,
    sub_region: str | None,
    neighborhood: str | None = None,
) -> dict[str, Any]:
    has_address = bool(address_raw)
    return {
        "recipient_name": recipient_name(name),
        "phone_number": "[PHONE]" if has_phone else None,
        "note": note,
        "address_raw": address_raw,
        "address_info": {
            "address_number": address_number,
            "street": street,
            "neighborhood": neighborhood,
            "municipality": municipality,
            "sub_region": sub_region,
            "country": COUNTRY if has_address else None,
        },
    }


def record(input_text: str, response: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_masked": compact_text(mask_phone(input_text)),
        "response": response,
    }


def render_order(
    index: int,
    name: str | None,
    phone: str | None,
    address_raw: str,
    note: str | None,
) -> str:
    phone_text = phone_variant(phone, index) if phone else None
    prefix = name or ""
    style = index % 10
    if style == 0:
        return f"{prefix} sđt {phone_text or ''} {address_raw}" + (
            f" note: {note}" if note else ""
        )
    if style == 1:
        return f"khách {prefix}, phone {phone_text or ''}, cần giao {address_raw}" + (
            f"; ghi chú {note}" if note else ""
        )
    if style == 2:
        return f"{prefix}\n{phone_text or ''}\nđịa chỉ: {address_raw}" + (
            f"\n{note}" if note else ""
        )
    if style == 3:
        return f"Shop ơi đơn của {prefix}: {phone_text or ''}; gửi tới {address_raw}" + (
            f"; ghi chú: {note}" if note else ""
        )
    if style == 4:
        return f"{prefix} đổi địa chỉ nha shop. ĐC mới: {address_raw}. {phone_text or ''}" + (
            f". {note}" if note else ""
        )
    if style == 5:
        return f"{prefix} chốt 1 đơn nha\nsđt {phone_text or ''}\nship {address_raw}" + (
            f"\nnote: {note}" if note else ""
        )
    # --- address-first styles ---
    if style == 6:
        return f"giao tới {address_raw}, người nhận: {prefix}, sđt {phone_text or ''}" + (
            f", ghi chú: {note}" if note else ""
        )
    if style == 7:
        return (
            f"địa chỉ giao: {address_raw}\nngười nhận: {prefix}\nliên hệ: {phone_text or ''}"
            + (f"\nnote: {note}" if note else "")
        )
    if style == 8:
        return f"ship {address_raw} | {prefix} | {phone_text or ''}" + (
            f" | {note}" if note else ""
        )
    # style == 9
    return f"ĐC: {address_raw} - {prefix} - {phone_text or ''}" + (
        f" - {note}" if note else ""
    )


def load_db_entries(db_path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    provinces = json.loads(db_path.read_text(encoding="utf-8"))
    old_entries: list[dict[str, str]] = []
    new_entries: list[dict[str, str]] = []

    for province in provinces:
        new_province = province["province_name"]
        for ward in province.get("wards", []):
            new_ward = ward["ward_name"]
            new_entries.append(
                {
                    "municipality": new_ward,
                    "sub_region": new_province,
                }
            )
            for old in ward.get("merged_from") or []:
                if not old.get("old_district_name") or not old.get("old_province_name"):
                    continue
                old_entries.append(
                    {
                        "neighborhood": old["old_ward_name"],
                        "municipality": old["old_district_name"],
                        "sub_region": old["old_province_name"],
                    }
                )

    return old_entries, new_entries


def build_generated_record(entry: dict[str, str], index: int, is_old: bool) -> dict[str, Any]:
    # Mỗi 4 record dùng 1 full name thay vì honorific+tên đơn (~25%)
    name = FULL_NAMES[(index // 4) % len(FULL_NAMES)] if index % 4 == 3 else NAMES[index % len(NAMES)]
    phone = phone_for(index)
    note = NOTES[index % len(NOTES)]
    house = house_for(index)
    street = street_for(index)
    style = index % 16
    house_text = f"số {house}"
    street_text: str | None = street
    separator = ", "

    if is_old:
        neighborhood = entry["neighborhood"]
        municipality = entry["municipality"]
        sub_region = entry["sub_region"]
    else:
        neighborhood = None
        municipality = entry["municipality"]
        sub_region = entry["sub_region"]

    if style in {1, 7}:
        neighborhood = abbreviate_admin(neighborhood, dotted=True)
        municipality = abbreviate_admin(municipality, dotted=True)
        sub_region = abbreviate_admin(sub_region, dotted=True)
    elif style in {2, 8}:
        neighborhood = abbreviate_admin(neighborhood, dotted=False)
        municipality = abbreviate_admin(municipality, dotted=False)
        sub_region = abbreviate_admin(sub_region, dotted=False)
    elif style == 3:
        neighborhood = neighborhood.lower() if neighborhood else None
        municipality = municipality.lower() if municipality else None
        sub_region = sub_region.lower() if sub_region else None
        separator = " "
    elif style == 4:
        neighborhood = None
    elif style == 5:
        municipality = None
    elif style == 6:
        sub_region = None
    elif style == 9:
        street_text = None
    elif style == 10:
        house_text = house
        separator = " "
    elif style == 11:
        municipality = abbreviate_admin(municipality, dotted=False)
        sub_region = abbreviate_admin(sub_region, dotted=False)
        separator = " "
    elif style == 12:
        house_text = strip_accents(house_text)
        street_text = strip_accents(street_text) if street_text else None
        neighborhood = strip_accents(neighborhood) if neighborhood else None
        municipality = strip_accents(municipality) if municipality else None
        sub_region = strip_accents(sub_region) if sub_region else None
    elif style == 13:
        neighborhood = abbreviate_admin(neighborhood, dotted=True)
        municipality = abbreviate_admin(municipality, dotted=True)
        sub_region = abbreviate_admin(sub_region, dotted=True)
    elif style == 14:
        neighborhood = neighborhood.lower() if neighborhood else None
        municipality = municipality.lower() if municipality else None
        sub_region = sub_region.lower() if sub_region else None
    elif style == 15:
        sub_region = None
        municipality = abbreviate_admin(municipality, dotted=False)

    address_first = join_address([house_text, street_text], " ")
    if style in {13, 14}:
        address_raw = join_address(
            [sub_region, municipality, neighborhood, address_first], separator
        )
    else:
        address_raw = join_address(
            [address_first, neighborhood, municipality, sub_region], separator
        )

    raw_text = render_order(index, name, phone, address_raw, note)
    return record(
        raw_text,
        new_response(
            name=name,
            has_phone=True,
            note=note,
            address_raw=address_raw,
            address_number=house,
            street=street_text,
            neighborhood=neighborhood,
            municipality=municipality,
            sub_region=sub_region,
        ),
    )


def build_role_confusion_record(index: int, style_index: int | None = None) -> dict[str, Any]:
    seller = SELLER_NAMES[index % len(SELLER_NAMES)]
    receiver = RECEIVER_NAMES[(index * 3) % len(RECEIVER_NAMES)]
    phone = phone_for(500_000 + index)
    phone_text = phone_variant(phone, index)
    house = f"{index % 900 + 1}/{index % 37 + 1}"
    street = STREETS[index % len(STREETS)].removeprefix("đường ").removeprefix("phố ")
    address_raw = f"{house} ngõ {index % 91 + 1} {street}"
    style = (style_index if style_index is not None else index) % 13

    if style == 0:
        raw_text = (
            f"{seller} ơi ship cho mình 1 cái áo nha, mình ở {address_raw}, "
            f"phone mình {phone_text}"
        )
        name = None
    elif style == 1:
        raw_text = (
            f"chị {seller} ơi em chốt váy size M, giao về {address_raw}, "
            f"sdt em {phone_text}"
        )
        name = None
    elif style == 2:
        raw_text = (
            f"shop {seller} gửi giúp đơn này cho anh {receiver}, {phone_text}, "
            f"địa chỉ {address_raw}"
        )
        name = f"anh {receiver}"
    elif style == 3:
        raw_text = (
            f"{seller} là nhân viên chốt đơn, người nhận: chị {receiver}, "
            f"sđt {phone_text}, giao {address_raw}"
        )
        name = f"chị {receiver}"
    elif style == 4:
        raw_text = (
            f"liên hệ shop {seller} nếu cần, khách nhận hàng là {receiver} "
            f"{phone_text}, ship {address_raw}"
        )
        name = receiver
    elif style == 5:
        raw_text = (
            f"{seller} ơi giao hộ mình về {address_raw}, số mình {phone_text}, "
            "tới nơi gọi trước"
        )
        name = None
    elif style == 6:
        raw_text = (
            f"người gửi {seller}, người nhận {receiver}, điện thoại {phone_text}, "
            f"địa chỉ nhận {address_raw}"
        )
        name = receiver
    elif style == 7:
        raw_text = (
            f"chị {seller} sale, ship cho cô {receiver} ở {address_raw}, "
            f"liên hệ {phone_text}"
        )
        name = f"cô {receiver}"

    # --- Patterns: sender tells delivery person to deliver to recipient ---
    elif style == 8:
        particle = PARTICLES[index % len(PARTICLES)]
        verb = ["giao", "ship", "đưa"][index % 3]
        raw_text = (
            f"{seller} ơi {verb} cho {receiver} {phone_text} tới {address_raw} {particle}"
        )
        name = receiver

    elif style == 9:
        prefix = DELIVERY_PREFIXES[index % len(DELIVERY_PREFIXES)]
        particle = PARTICLES[(index + 1) % len(PARTICLES)]
        raw_text = (
            f"{seller} ơi đến {address_raw} giao cho {prefix} {receiver} {particle}, "
            f"số khách {phone_text}"
        )
        name = f"{prefix} {receiver}"

    elif style == 10:
        particle = PARTICLES[(index + 2) % len(PARTICLES)]
        raw_text = (
            f"{seller} ơi đi giao hàng cho {receiver} {particle}, "
            f"giao tới {address_raw}, sdt khách {phone_text}"
        )
        name = receiver

    # Seller có honorific prefix, người nói là người nhận (recipient_name = null)
    elif style == 11:
        hon = ["anh", "chị", "cô"][index % 3]
        verb = ["giao cho mình", "ship cho mình", "giao hộ mình"][index % 3]
        particle = PARTICLES[index % len(PARTICLES)]
        raw_text = (
            f"{hon} {seller} ơi {verb} {particle}, "
            f"mình đang ở {address_raw}, phone mình {phone_text}"
        )
        name = None

    else:  # style == 12
        hon = ["anh", "chị", "bạn"][index % 3]
        verb = ["giao cho mình nha", "ship cho mình đi", "giao hộ mình với"][index % 3]
        raw_text = (
            f"{hon} {seller} ơi {verb}, đang ở {address_raw}"
        )
        name = None

    note = "tới nơi gọi trước" if style == 5 else None
    return record(
        raw_text,
        new_response(
            name=name,
            has_phone=True,
            note=note,
            address_raw=address_raw,
            address_number=house,
            street=f"ngõ {index % 91 + 1} {street}",
            municipality=None,
            sub_region=None,
        ),
    )


OLD_STREETS = [
    "đường Hai Bà Trưng",
    "đường Bà Triệu",
    "đường Kim Mã",
    "phố Huế",
    "đường Tôn Đức Thắng",
    "đường Ngô Gia Tự",
    "đường Trường Chinh",
    "phố Vọng",
]


def build_address_correction_record(index: int) -> dict[str, Any]:
    """Tin nhắn đính chính địa chỉ: nêu cả địa chỉ cũ và địa chỉ mới, model chỉ lấy địa chỉ mới."""
    name = NAMES[index % len(NAMES)]
    phone = phone_for(600_000 + index)
    phone_text = phone_variant(phone, index)

    # Địa chỉ cũ (fake, không cần khớp DB)
    old_house = str((index * 13 + 7) % 200 + 1)
    old_street = OLD_STREETS[index % len(OLD_STREETS)]
    old_address = f"{old_house} {old_street}"

    # Địa chỉ mới (địa chỉ thực sự cần giao)
    new_house = house_for(index)
    new_street = street_for(index)
    address_raw = f"{new_house} {new_street}"
    style = index % 5

    if style == 0:
        raw_text = (
            f"{name} ơi, hồi nãy nhắn nhầm địa chỉ rồi. "
            f"Đúng ra giao {address_raw} không phải {old_address}, sđt {phone_text}"
        )
    elif style == 1:
        raw_text = (
            f"{name} đổi lại địa chỉ nha shop, địa chỉ cũ {old_address} "
            f"giờ giao sang {address_raw} nhé. {phone_text}"
        )
    elif style == 2:
        raw_text = (
            f"xin lỗi shop nhé, địa chỉ vừa nhắn sai: {old_address}. "
            f"Đúng là: {address_raw}. {name}, {phone_text}"
        )
    elif style == 3:
        raw_text = (
            f"{name} {phone_text} đính chính địa chỉ: "
            f"trước là {old_address}, nay đổi thành {address_raw}"
        )
    else:
        raw_text = (
            f"cho mình sửa địa chỉ nha, từ {old_address} đổi thành {address_raw}, "
            f"liên hệ {name} {phone_text}"
        )

    return record(
        raw_text,
        new_response(
            name=name,
            has_phone=True,
            note=None,
            address_raw=address_raw,
            address_number=new_house,
            street=new_street,
            municipality=None,
            sub_region=None,
        ),
    )


def curated_records() -> list[dict[str, Any]]:
    rows = [
        (
            "anh Bình sdt 0987654321 Số nhà TT08, KĐT Vinhomes Smart City, Nam Từ Liêm, Hà Nội",
            new_response("anh Bình", True, None, "Số nhà TT08, KĐT Vinhomes Smart City, Nam Từ Liêm, Hà Nội", "TT08", "KĐT Vinhomes Smart City", "Nam Từ Liêm", "Hà Nội"),
        ),
        (
            "Tên: Trần Bích Ngọc | ĐT: 0901 234 567 | Địa chỉ: Căn hộ 12B, Chung cư Sunrise, 90 Võ Văn Ngân, Thủ Đức | Ghi chú: gọi trước 30p",
            new_response("Trần Bích Ngọc", True, "gọi trước 30p", "Căn hộ 12B, Chung cư Sunrise, 90 Võ Văn Ngân, Thủ Đức", "Căn hộ 12B, Chung cư Sunrise, 90", "Võ Văn Ngân", "Thủ Đức", None),
        ),
        (
            "chú Bình chốt 1 đơn nha\nsđt 0908.123.752\nship sn 18 đường Nguyễn Văn Cừ, x. Yên Hợp, h. Quỳ Hợp, Nghệ An\nnote: đừng gọi giờ nghỉ trưa",
            new_response("chú Bình", True, "đừng gọi giờ nghỉ trưa", "sn 18 đường Nguyễn Văn Cừ, x. Yên Hợp, h. Quỳ Hợp, Nghệ An", "18", "đường Nguyễn Văn Cừ", "h. Quỳ Hợp", "Nghệ An", "x. Yên Hợp"),
        ),
        (
            "gửi tới Trường THPT Chu Văn An, Tây Hồ, Hà Nội, liên hệ chị Nga 0902000202",
            new_response("chị Nga", True, None, "Trường THPT Chu Văn An, Tây Hồ, Hà Nội", "Trường THPT Chu Văn An", None, "Tây Hồ", "Hà Nội"),
        ),
        (
            "bé Trang 0791111222 nhận tại TTTM Vincom Plaza Xuân Khánh, Ninh Kiều, Cần Thơ",
            new_response("bé Trang", True, None, "TTTM Vincom Plaza Xuân Khánh, Ninh Kiều, Cần Thơ", None, "TTTM Vincom Plaza Xuân Khánh", "Ninh Kiều", "Cần Thơ"),
        ),
        (
            "Lan ơi ship cho mình 1 cái váy size S nha, mình ở 22 Ngô Quyền, phone mình 0901234567",
            new_response(None, True, None, "22 Ngô Quyền", "22", "Ngô Quyền", None, None),
        ),
        (
            "mã đơn: 0912345678, giao 22 Ngô Quyền",
            new_response(None, False, None, "22 Ngô Quyền", "22", "Ngô Quyền", None, None),
        ),
        (
            "nhà số 0987654321, giao buổi chiều",
            new_response(None, False, "giao buổi chiều", "nhà số 0987654321", "0987654321", None, None, None),
        ),
        (
            "hôm nay trời đẹp quá, shop có màu xanh không?",
            new_response(None, False, None, None, None, None, None, None),
        ),
        (
            "ship cho cô Hoa 0881234000: 3/2A Nguyễn Oanh, Gò Vấp, mai giao trước 11h",
            new_response("cô Hoa", True, "mai giao trước 11h", "3/2A Nguyễn Oanh, Gò Vấp", "3/2A", "Nguyễn Oanh", "Gò Vấp", None),
        ),
        (
            "chị Mai :v :3 😭 ship 22 Ngô Quyền nha 0979144879",
            new_response("chị Mai", True, None, "22 Ngô Quyền", "22", "Ngô Quyền", None, None),
        ),
        (
            "Lê Văn Đức, 0812456789, 50 Đinh Tiên Hoàng Q.Bình Thạnh - nhớ ghi \"hàng dễ vỡ\" lên kiện",
            new_response("Lê Văn Đức", True, "hàng dễ vỡ", "50 Đinh Tiên Hoàng Q.Bình Thạnh", "50", "Đinh Tiên Hoàng", "Q.Bình Thạnh", None),
        ),
        (
            "sdt: 0987654321 - địa chỉ: 12 Trần Hưng Đạo, Đống Đa, Hà Nội",
            new_response(None, True, None, "12 Trần Hưng Đạo, Đống Đa, Hà Nội", "12", "Trần Hưng Đạo", "Đống Đa", "Hà Nội"),
        ),
        (
            "chị Vy 091234567 giao 18 Hàng Bông, Đống Đa, Hà Nội",
            new_response("chị Vy", False, None, "18 Hàng Bông, Đống Đa, Hà Nội", "18", "Hàng Bông", "Đống Đa", "Hà Nội"),
        ),
        (
            "giao tới Khoa Cấp cứu BV Chợ Rẫy, 201B Nguyễn Chí Thanh, Q5, Sài Gòn, liên hệ chị Nga 0902000202",
            new_response("chị Nga", True, None, "Khoa Cấp cứu BV Chợ Rẫy, 201B Nguyễn Chí Thanh, Q5, Sài Gòn", "Khoa Cấp cứu BV Chợ Rẫy, 201B", "Nguyễn Chí Thanh", "Q5", "Sài Gòn"),
        ),
        (
            "chị Duyên, 0934444555, Ấp 2 xã Phú Hữu, huyện Nhơn Trạch, Đồng Nai, nhà cạnh cây xăng",
            new_response("chị Duyên", True, "nhà cạnh cây xăng", "Ấp 2 xã Phú Hữu, huyện Nhơn Trạch, Đồng Nai", None, "Ấp 2", "huyện Nhơn Trạch", "Đồng Nai", "xã Phú Hữu"),
        ),
        (
            "giao giúp em tới nhà văn hóa thôn Đông, xã Phù Đổng, Gia Lâm, Hà Nội, liên hệ 0568888999",
            new_response(None, True, None, "nhà văn hóa thôn Đông, xã Phù Đổng, Gia Lâm, Hà Nội", None, "nhà văn hóa thôn Đông", "Gia Lâm", "Hà Nội", "xã Phù Đổng"),
        ),
        (
            "không có địa chỉ, tên: Lan, sdt: 0999888777",
            new_response("Lan", True, None, None, None, None, None, None),
        ),
        (
            "+84 912 345 678",
            new_response(None, True, None, None, None, None, None, None),
        ),
        (
            "lấy hàng ở 12 Lý Thái Tổ, giao tới 88 Nguyễn Du, gọi số 0901234567",
            new_response(None, True, None, "88 Nguyễn Du", "88", "Nguyễn Du", None, None),
        ),
        (
            "chị Mai 0909123456 giao 12 Nguyễn Trãi, x.An Thái, h Quỳnh Phụ tỉnh Thái Bình",
            new_response("chị Mai", True, None, "12 Nguyễn Trãi, x.An Thái, h Quỳnh Phụ tỉnh Thái Bình", "12", "Nguyễn Trãi", "h Quỳnh Phụ", "tỉnh Thái Bình", "x.An Thái"),
        ),
        (
            "anh Hoàng sđt 0988111222 giao 94 đường Hoàng Mai, Quận Hoàng Mai, Hà Nội",
            new_response("anh Hoàng", True, None, "94 đường Hoàng Mai, Quận Hoàng Mai, Hà Nội", "94", "đường Hoàng Mai", "Quận Hoàng Mai", "Hà Nội"),
        ),
        (
            "ship 18 phố Huế, Hà Nội cho chị Hoa 0911222444",
            new_response("chị Hoa", True, None, "18 phố Huế, Hà Nội", "18", "phố Huế", None, "Hà Nội"),
        ),
        (
            "anh Lâm 0966777888 số 5A, p. Tân Định, q 1, tphcm",
            new_response("anh Lâm", True, None, "số 5A, p. Tân Định, q 1, tphcm", "5A", None, "q 1", "tphcm", "p. Tân Định"),
        ),
        (
            "giao số 27 ngõ 4 đường Cầu Giấy, q.Cầu Giấy cho cô Vân 0833555777",
            new_response("cô Vân", True, None, "số 27 ngõ 4 đường Cầu Giấy, q.Cầu Giấy", "27", "ngõ 4 đường Cầu Giấy", "q.Cầu Giấy", None),
        ),
        (
            "anh Hoàng 0988111222 giao 94 đường Hoàng Mai, Quận Hoàng Mai",
            new_response("anh Hoàng", True, None, "94 đường Hoàng Mai, Quận Hoàng Mai", "94", "đường Hoàng Mai", "Quận Hoàng Mai", None),
        ),
        (
            "chị Linh 0904123604 giao căn hộ 12B, chung cư Sunrise, 90 Võ Văn Ngân, Thủ Đức",
            new_response("chị Linh", True, None, "căn hộ 12B, chung cư Sunrise, 90 Võ Văn Ngân, Thủ Đức", "căn hộ 12B, chung cư Sunrise, 90", "Võ Văn Ngân", "Thủ Đức", None),
        ),
        (
            "chị Mai 0909123456 giao Ha Noi, q. Dong Da, p. Hang Bot, 18 Ton Duc Thang",
            new_response("chị Mai", True, None, "Ha Noi, q. Dong Da, p. Hang Bot, 18 Ton Duc Thang", "18", "Ton Duc Thang", "q. Dong Da", "Ha Noi", "p. Hang Bot"),
        ),
        (
            "anh Nam 0987654321 ship tinh Thai Binh, h. Quynh Phu, x. An Thai, 12 Nguyen Trai",
            new_response("anh Nam", True, None, "tinh Thai Binh, h. Quynh Phu, x. An Thai, 12 Nguyen Trai", "12", "Nguyen Trai", "h. Quynh Phu", "tinh Thai Binh", "x. An Thai"),
        ),
        # --- sender-tells-delivery patterns ---
        (
            "Trang ơi đi giao hàng cho Quỳnh Anh nhé, giao tới 88 Nguyễn Du, Hà Nội, số khách 0901234567",
            new_response("Quỳnh Anh", True, None, "88 Nguyễn Du, Hà Nội", "88", "Nguyễn Du", None, "Hà Nội"),
        ),
        (
            "Lan ơi ship cho Minh Tuấn 0912345678 tới 22 Lê Lợi, Hoàn Kiếm nha",
            new_response("Minh Tuấn", True, None, "22 Lê Lợi, Hoàn Kiếm", "22", "Lê Lợi", "Hoàn Kiếm", None),
        ),
        (
            "Hương ơi đến 45 Trần Duy Hưng, Cầu Giấy giao cho chị Phương ạ, số khách 0903444555",
            new_response("chị Phương", True, None, "45 Trần Duy Hưng, Cầu Giấy", "45", "Trần Duy Hưng", "Cầu Giấy", None),
        ),
        (
            "Ngọc ơi giao cho Bích Ngọc 0977888123 tại số 5 Đinh Tiên Hoàng, Quận 1 nha",
            new_response("Bích Ngọc", True, None, "số 5 Đinh Tiên Hoàng, Quận 1", "5", "Đinh Tiên Hoàng", "Quận 1", None),
        ),
        (
            "Vy ơi ship giúp cho anh Hùng ở 12/3 Cách Mạng Tháng 8, Quận 3 nhé, liên hệ 0908999111",
            new_response("anh Hùng", True, None, "12/3 Cách Mạng Tháng 8, Quận 3", "12/3", "Cách Mạng Tháng 8", "Quận 3", None),
        ),
        # Seller có honorific, người nói là người nhận → recipient_name = null
        (
            "chị Mai ơi giao cho mình nha, đang ở 88 Nguyễn Du",
            new_response(None, False, None, "88 Nguyễn Du", "88", "Nguyễn Du", None, None),
        ),
        (
            "anh Hùng ơi ship cho mình cái này với, mình ở 45 Lê Lợi, Hoàn Kiếm, phone 0901234567",
            new_response(None, True, None, "45 Lê Lợi, Hoàn Kiếm", "45", "Lê Lợi", "Hoàn Kiếm", None),
        ),
        (
            "chị Lan ơi giao hộ mình nha, địa chỉ 22 Trần Phú, Hà Đông, sđt 0912345678",
            new_response(None, True, None, "22 Trần Phú, Hà Đông", "22", "Trần Phú", "Hà Đông", None),
        ),
        (
            "bạn Ngọc ơi ship cho mình đi, mình đang ở số 5 Đinh Tiên Hoàng",
            new_response(None, False, None, "số 5 Đinh Tiên Hoàng", "5", "Đinh Tiên Hoàng", None, None),
        ),
    ]
    return [record(text, response) for text, response in rows]


def generate_records(
    old_entries: list[dict[str, str]],
    new_entries: list[dict[str, str]],
    count: int,
    rng: random.Random,
    start_index: int,
) -> list[dict[str, Any]]:
    records = []
    old_count = int(count * 0.7)
    for offset in range(count):
        if offset % 10 == 0:
            records.append(
                build_role_confusion_record(start_index + offset, offset // 10)
            )
            continue
        if offset % 20 == 5:   # 5%, không trùng với role_confusion (offset%10==0)
            records.append(build_address_correction_record(start_index + offset))
            continue
        is_old = offset < old_count
        pool = old_entries if is_old else new_entries
        entry = rng.choice(pool)
        records.append(build_generated_record(entry, start_index + offset, is_old))
    rng.shuffle(records)
    return records


def dataset_profile(records: list[dict[str, Any]]) -> dict[str, int]:
    def input_count(pattern: str) -> int:
        return sum(
            bool(re.search(pattern, row["input_masked"], flags=re.IGNORECASE))
            for row in records
        )

    def null_count(field: str) -> int:
        return sum(
            row["response"]["address_info"].get(field) is None for row in records
        )

    role_pattern = (
        r"(ơi ship cho mình|ơi em chốt|shop .+ gửi giúp|nhân viên chốt đơn|"
        r"liên hệ shop|ơi giao hộ|người gửi|sale, ship cho|"
        r"ơi giao cho|ơi ship cho|ơi đi giao|ơi đến .+ giao)"
    )
    role_records = [
        row
        for row in records
        if re.search(role_pattern, row["input_masked"], flags=re.IGNORECASE)
    ]

    return {
        "records": len(records),
        "masked_phone_records": sum("[PHONE]" in row["input_masked"] for row in records),
        "x_dot_or_space_inputs": input_count(r"\bx(?:\.|\s)"),
        "h_dot_or_space_inputs": input_count(r"\bh(?:\.|\s)"),
        "p_dot_or_space_inputs": input_count(r"\bp(?:\.|\s)"),
        "q_dot_or_space_inputs": input_count(r"\bq(?:\.|\s)"),
        "neighborhood_null": null_count("neighborhood"),
        "municipality_null": null_count("municipality"),
        "sub_region_null": null_count("sub_region"),
        "street_null": null_count("street"),
        "accentless_address_records": sum(
            bool(row["response"]["address_raw"])
            and strip_accents(row["response"]["address_raw"])
            == row["response"]["address_raw"]
            for row in records
        ),
        "reverse_order_records": sum(
            bool(
                re.match(
                    r"^(?:tinh|tỉnh|thanh pho|thành phố|tp\.?|ha noi|hà nội|"
                    r"ho chi minh|hồ chí minh)",
                    row["response"]["address_raw"] or "",
                    flags=re.IGNORECASE,
                )
            )
            for row in records
        ),
        "role_confusion_records": len(role_records),
        "role_confusion_recipient_null": sum(
            row["response"]["recipient_name"] is None for row in role_records
        ),
    }


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    old_entries, new_entries = load_db_entries(args.db)
    curated = curated_records()

    valid = curated + generate_records(
        old_entries, new_entries, max(args.valid_size - len(curated), 0), rng, 100_000
    )
    train = generate_records(old_entries, new_entries, args.train_size, rng, 0)

    valid_masked = {row["input_masked"] for row in valid}
    train = [row for row in train if row["input_masked"] not in valid_masked]

    train_path = args.output_dir / "records_train.jsonl"
    valid_path = args.output_dir / "records_valid.jsonl"
    write_jsonl(train_path, train)
    write_jsonl(valid_path, valid)

    summary = {
        "train_records": len(train),
        "valid_records": len(valid),
        "curated_valid_records": len(curated),
        "old_db_entries": len(old_entries),
        "new_db_entries": len(new_entries),
        "schema": {
            "address_raw": "original address fragment from input",
            "old_address": "neighborhood=old ward, municipality=old district, sub_region=old province",
            "new_address": "neighborhood=null, municipality=new ward, sub_region=new province",
        },
        "train_profile": dataset_profile(train),
        "valid_profile": dataset_profile(valid),
    }
    (args.output_dir / "dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {train_path}")
    print(f"Wrote {valid_path}")


if __name__ == "__main__":
    main()
