import re

from app.schemas.order import ExtractedAddress


NAME_RE = re.compile(
    r"\b(anh|chị|chi|cô|co|chú|chu|bạn|ban|b|c)\s+([A-ZÀ-Ỵ][\wÀ-ỹ]+)",
    flags=re.IGNORECASE,
)
HOUSE_RE = re.compile(
    r"\b(?:sn|số nhà|so nha|số|so)\s*([0-9]+[a-zA-Z]?(?:/[0-9]+[a-zA-Z]?)?)\b",
    flags=re.IGNORECASE,
)
LEADING_HOUSE_RE = re.compile(
    r"\b([0-9]+[a-zA-Z]?(?:/[0-9]+[a-zA-Z]?)?)\s+"
    r"(?=(?:ngách|ngach|ngõ|ngo|hẻm|hem|kiệt|kiet|đường|duong|phố|pho)\b)",
    flags=re.IGNORECASE,
)
WARD_RE = re.compile(
    r"\b(p\.?\s*\d+|p\.\s*[^,.;\n]+|p\s+[^,.;\n]+|phường\s+[^,.;\n]+|phuong\s+[^,.;\n]+|"
    r"x\.\s*[^,.;\n]+|x\s+[^,.;\n]+|xã\s+[^,.;\n]+|xa\s+[^,.;\n]+|"
    r"tt\.\s*[^,.;\n]+|thị trấn\s+[^,.;\n]+|thi tran\s+[^,.;\n]+)",
    flags=re.IGNORECASE,
)
DISTRICT_RE = re.compile(
    r"\b(q\.?\s*\d+|q\.\s*[^,.;\n]+|q\s+[^,.;\n]+|quận\s+[^,.;\n]+|quan\s+[^,.;\n]+|"
    r"h\.\s*[^,.;\n]+|h\s+[^,.;\n]+|huyện\s+[^,.;\n]+|huyen\s+[^,.;\n]+|"
    r"tx\.\s*[^,.;\n]+|thị xã\s+[^,.;\n]+|thi xa\s+[^,.;\n]+)",
    flags=re.IGNORECASE,
)
STREET_RE = re.compile(
    r"\b((?:ngách|ngach|ngõ|ngo|hẻm|hem|kiệt|kiet)\s+[^,.;]+?\s+)?"
    r"((?:đường|duong|phố|pho)\s+[^,.;\n]+)",
    flags=re.IGNORECASE,
)
NOTE_RE = re.compile(
    r"\b(?:note|ghi chú|ghi chu)\s*[:：]?\s*([^.;\n]+(?:[.;]\s*[^.;\n]+)?)",
    flags=re.IGNORECASE,
)
SIMPLE_NOTE_RE = re.compile(
    r"\b(gọi trước[^.;\n]*|goi truoc[^.;\n]*|giao giờ[^.;\n]*|giao gio[^.;\n]*|"
    r"ship sau[^.;\n]*|thu cod[^.;\n]*|cod\s*\d+[kK]?|"
    r"để hàng[^.;\n]*|de hang[^.;\n]*|chuyển khoản rồi|chuyen khoan roi)",
    flags=re.IGNORECASE,
)


def extract_rule_hints(text: str) -> tuple[str | None, ExtractedAddress]:
    return _extract_name(text), ExtractedAddress(
        province=_extract_province(text),
        district_hint=_extract_district(text),
        ward=_extract_ward(text),
        street=_extract_street(text),
        house_number=_extract_house_number(text),
    )


def extract_rule_note(text: str) -> str | None:
    match = NOTE_RE.search(text or "")
    if match:
        return match.group(1).strip(" ,;.")
    matches = [m.group(1).strip(" ,;.") for m in SIMPLE_NOTE_RE.finditer(text or "")]
    if not matches:
        return None
    deduped = []
    for match_text in matches:
        if match_text.lower() not in {item.lower() for item in deduped}:
            deduped.append(match_text)
    return ", ".join(deduped)


def _extract_name(text: str) -> str | None:
    match = NAME_RE.search(text or "")
    if not match:
        return None
    prefix = match.group(1)
    name = match.group(2)
    return f"{prefix} {name}"


def _extract_province(text: str) -> str | None:
    lowered = (text or "").lower()
    if re.search(r"\b(hn|hà nội|ha noi)\b", lowered):
        return "Hà Nội"
    if re.search(r"\b(hcm|tphcm|tp\.?\s*hcm|sài gòn|sai gon|hồ chí minh|ho chi minh)\b", lowered):
        return "Hồ Chí Minh"
    match = re.search(
        r"\b(?:tỉnh|tinh|thành phố|thanh pho|tp\.?)\s+([^,.;\n]+)",
        text or "",
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _extract_house_number(text: str) -> str | None:
    match = HOUSE_RE.search(text or "")
    if match:
        return match.group(1).strip()
    match = LEADING_HOUSE_RE.search(text or "")
    return match.group(1).strip() if match else None


def _extract_street(text: str) -> str | None:
    match = STREET_RE.search(text or "")
    if not match:
        return None
    return " ".join(part.strip() for part in match.groups() if part).strip()


def _extract_first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text or "")
    return match.group(1).strip() if match else None


def _extract_ward(text: str) -> str | None:
    match = WARD_RE.search(text or "")
    if not match:
        return None
    raw = match.group(1).strip()
    raw_lower = raw.lower()
    name = re.sub(
        r"^(phường|phuong|thị trấn|thi tran|p\.?|x\.?|xã|xa|tt\.?)\s*",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()
    if raw_lower.startswith(("p", "phường", "phuong")):
        return f"Phường {name}"
    if raw_lower.startswith(("x.", "x ", "xã", "xa")):
        return f"Xã {name}"
    return f"Thị trấn {name}"


def _extract_district(text: str) -> str | None:
    match = DISTRICT_RE.search(text or "")
    if not match:
        return None
    raw = match.group(1).strip()
    raw_lower = raw.lower()
    name = re.sub(
        r"^(quận|quan|huyện|huyen|thị xã|thi xa|q\.?|h\.?|tx\.?)\s*",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()
    if raw_lower.startswith(("q", "quận", "quan")):
        return f"Quận {name}"
    if raw_lower.startswith(("h.", "huyện", "huyen")):
        return f"Huyện {name}"
    return f"Thị xã {name}"
