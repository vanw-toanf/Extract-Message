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
    r"\b(?:p\.?|phường|phuong|xã|xa|tt\.?|thị trấn|thi tran)\s+([^,.;\n]+)",
    flags=re.IGNORECASE,
)
DISTRICT_RE = re.compile(
    r"\b(?:q\.?|quận|quan|h\.?|huyện|huyen|tx\.?|thị xã|thi xa)\s+([^,.;\n]+)",
    flags=re.IGNORECASE,
)
STREET_RE = re.compile(
    r"\b((?:ngách|ngach|ngõ|ngo|hẻm|hem|kiệt|kiet)\s+[^,.;]+?\s+)?"
    r"((?:đường|duong|phố|pho)\s+[^,.;\n]+)",
    flags=re.IGNORECASE,
)


def extract_rule_hints(text: str) -> tuple[str | None, ExtractedAddress]:
    return _extract_name(text), ExtractedAddress(
        province=_extract_province(text),
        district_hint=_extract_first(DISTRICT_RE, text),
        ward=_extract_first(WARD_RE, text),
        street=_extract_street(text),
        house_number=_extract_house_number(text),
    )


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
