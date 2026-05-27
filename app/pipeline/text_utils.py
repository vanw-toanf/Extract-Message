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
    text = re.sub(r"[\t\r\n]+", " ", text)
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
