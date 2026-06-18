import re
import unicodedata


ADMIN_PREFIXES = (
    "thanh pho",
    "thu do",
    "tp",
    "t p",
    "tinh",
    "quan",
    "q",
    "huyen",
    "thi xa",
    "tx",
    "phuong",
    "p",
    "xa",
    "thi tran",
    "tt",
    "thon",
    "ap",
)


def compact_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"[\t\r]+", " ", text)
    text = re.sub(r"\n+", ", ", text)       # preserve line boundaries as separators
    text = re.sub(r",\s*,", ", ", text)     # collapse consecutive commas
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


def normalize_key(text: str, remove_admin_prefix: bool = True) -> str:
    key = strip_accents(text).lower()
    key = re.sub(r"[^\w\s]", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    if remove_admin_prefix:
        for prefix in sorted(ADMIN_PREFIXES, key=len, reverse=True):
            key = re.sub(rf"\b{re.escape(prefix)}\b", " ", key)
        key = re.sub(r"\s+", " ", key).strip()
        parts = [p for p in key.split() if p not in ADMIN_PREFIXES]
        key = " ".join(parts)
    return key


_PROVINCE_ADMIN_PREFIX_RE = re.compile(
    r"^(thủ\s+đô|thành\s+phố|tỉnh|t\.?p\.?)\s+",
    re.IGNORECASE,
)

# Informal / abbreviated province names → canonical new-2025 name
_PROVINCE_ALIAS: dict[str, str] = {
    "sai gon": "Hồ Chí Minh",
    "saigon": "Hồ Chí Minh",
    "tphcm": "Hồ Chí Minh",
    "tp hcm": "Hồ Chí Minh",
    "hcm": "Hồ Chí Minh",
    "hn": "Hà Nội",
    "da nang": "Đà Nẵng",
    "can tho": "Cần Thơ",
}


def short_province(name: str | None) -> str | None:
    """Strip admin-level prefix from province name for display and geocoding.

    'Thủ đô Hà Nội' → 'Hà Nội', 'Thành phố Hồ Chí Minh' → 'Hồ Chí Minh'
    """
    if not name:
        return name
    return _PROVINCE_ADMIN_PREFIX_RE.sub("", name).strip() or name


def canonical_province(name: str | None) -> str | None:
    """Normalize province: strip admin prefix then resolve common aliases.

    'Thành phố Hồ Chí Minh' → 'Hồ Chí Minh', 'Sài Gòn' → 'Hồ Chí Minh',
    'TP.HCM' → 'Hồ Chí Minh' (dots/punctuation stripped before lookup)
    """
    name = short_province(name)
    if not name:
        return name
    key = strip_accents(name).lower().strip()
    if key in _PROVINCE_ALIAS:
        return _PROVINCE_ALIAS[key]
    # Normalize punctuation: strip dots/hyphens so "tp.hcm" matches "tphcm"
    key_clean = re.sub(r"[^a-z0-9 ]", "", key)
    key_clean = re.sub(r"\s+", " ", key_clean).strip()
    return _PROVINCE_ALIAS.get(key_clean, name)


def normalize_text_key(text: str, remove_admin_prefix: bool = True) -> str:
    key = unicodedata.normalize("NFKC", text or "").lower()
    key = re.sub(r"[^\w\s]", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    if remove_admin_prefix:
        for prefix in sorted(ADMIN_PREFIXES, key=len, reverse=True):
            key = re.sub(rf"\b{re.escape(prefix)}\b", " ", key)
        key = re.sub(r"\s+", " ", key).strip()
        parts = [p for p in key.split() if p not in ADMIN_PREFIXES]
        key = " ".join(parts)
    return key
