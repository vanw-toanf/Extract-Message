import re


PHONE_RE = re.compile(r"(?<!\d)[+()0-9][0-9\s.\-()]{8,18}(?!\d)")
VALID_MOBILE_PREFIXES = ("03", "05", "07", "08", "09")
PHONE_BLOCK_CONTEXT_RE = re.compile(
    r"(mã\s*đơn|ma\s*don|nhà\s*số|nha\s*so|số\s*nhà|so\s*nha)\s*[:#-]?\s*$",
    flags=re.IGNORECASE,
)


def extract_phone(text: str) -> str | None:
    for match in PHONE_RE.finditer(text or ""):
        if _blocked_by_context(text[: match.start()]):
            continue
        digits = normalize_phone(match.group(0))
        if digits:
            return digits
    return None


def remove_phone(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        if _blocked_by_context((text or "")[: match.start()]):
            return match.group(0)
        return " " if normalize_phone(match.group(0)) else match.group(0)

    return PHONE_RE.sub(repl, text or "")


def normalize_phone(raw_phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", raw_phone or "")
    if digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    if len(digits) == 10 and digits.startswith(VALID_MOBILE_PREFIXES):
        return digits
    return None


def _blocked_by_context(prefix: str) -> bool:
    return bool(PHONE_BLOCK_CONTEXT_RE.search(prefix[-32:]))
