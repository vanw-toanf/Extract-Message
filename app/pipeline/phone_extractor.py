import re


PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.\-]?\d){8,10}(?!\d)")


def extract_phone(text: str) -> str | None:
    match = PHONE_RE.search(text or "")
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(0))
    if digits.startswith("84"):
        digits = "0" + digits[2:]
    if len(digits) in {10, 11} and digits.startswith("0"):
        return digits
    return None


def remove_phone(text: str) -> str:
    return PHONE_RE.sub(" ", text or "")
