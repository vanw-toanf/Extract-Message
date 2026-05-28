import re

from app.core_config import Settings
from app.pipeline.address_normalizer import AddressNormalizer
from app.pipeline.phone_extractor import extract_phone, normalize_phone, remove_phone
from app.pipeline.rule_extractor import extract_rule_hints, extract_rule_note
from app.pipeline.text_utils import compact_text
from app.schemas.order import ExtractedAddress, ExtractedOrder, ParseResponse, PublicAddress
from app.services.llm_client import LLMClient


class OrderParser:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm = LLMClient(settings)
        self.address_normalizer = AddressNormalizer(
            settings.admin_db_path, settings.fuzzy_threshold
        )

    def parse(self, text: str, use_llm: bool = True) -> ParseResponse:
        cleaned = compact_text(text)
        regex_phone = extract_phone(cleaned)
        rule_name, rule_address = extract_rule_hints(cleaned)
        rule_note = extract_rule_note(cleaned)
        llm_input = compact_text(remove_phone(cleaned))

        if not self._is_likely_order(cleaned, regex_phone, rule_address):
            return ParseResponse()

        extracted = ExtractedOrder()
        should_call_llm = (
            use_llm
            and self.settings.enable_llm
            and not self._can_skip_llm(regex_phone, rule_name, rule_note, rule_address)
        )
        if should_call_llm:
            try:
                extracted, _ = self.llm.extract_order(llm_input)
            except Exception:
                extracted = ExtractedOrder()

        if regex_phone:
            extracted.phone = regex_phone
        if not extracted.name and rule_name:
            extracted.name = rule_name
        if not extracted.note and rule_note:
            extracted.note = rule_note
        self._merge_address_hints(extracted.address, rule_address)

        extracted.phone = self._normalize_phone(extracted.phone)
        self._fix_address_parts(extracted.address)
        normalized_address = self.address_normalizer.normalize(extracted.address)

        return ParseResponse(
            name=extracted.name,
            phone=extracted.phone,
            note=extracted.note,
            address=PublicAddress(
                province=normalized_address.province or extracted.address.province,
                ward=normalized_address.ward
                or extracted.address.ward
                or extracted.address.district_hint,
                street=normalized_address.street or extracted.address.street,
                house_number=normalized_address.house_number
                or extracted.address.house_number,
            ),
        )

    def _can_skip_llm(
        self,
        phone: str | None,
        name: str | None,
        note: str | None,
        address_hint: ExtractedAddress,
    ) -> bool:
        if not self.settings.cpu_fast_mode:
            return False
        address_signal_count = sum(
            bool(value)
            for value in (
                address_hint.province,
                address_hint.ward,
                address_hint.street,
                address_hint.house_number,
            )
        )
        return bool(phone and name and address_signal_count >= 2 and note)

    def _is_likely_order(
        self,
        text: str,
        phone: str | None,
        address_hint: ExtractedAddress,
    ) -> bool:
        if phone:
            return True
        if address_hint.province or address_hint.ward or address_hint.street:
            return True
        return bool(
            re.search(
                r"\b(giao|ship|địa chỉ|dia chi|đc|dc|sđt|sdt|phone|tel|chốt|chot|đơn|don|cod)\b",
                text,
                flags=re.IGNORECASE,
            )
        )

    def _normalize_phone(self, phone: str | None) -> str | None:
        if not phone:
            return None
        digits = re.sub(r"\D", "", phone)
        return normalize_phone(digits)

    def _merge_address_hints(
        self, address: ExtractedAddress, hints: ExtractedAddress
    ) -> None:
        for field in ("province", "district_hint", "ward"):
            if not getattr(address, field) and getattr(hints, field):
                setattr(address, field, getattr(hints, field))
            elif field in {"district_hint", "ward"} and self._should_override_admin_part(
                getattr(address, field), getattr(hints, field)
            ):
                setattr(address, field, getattr(hints, field))

        if not address.street and hints.street:
            address.street = hints.street
        elif hints.street and address.street and len(hints.street) > len(address.street):
            address.street = hints.street

        if hints.house_number and (
            not address.house_number
            or re.match(r"^\s*(sn|số|so)\b", address.house_number, re.IGNORECASE)
            or re.search(
                r"\b(ngõ|ngo|ngách|ngach|hẻm|hem|kiệt|kiet|đường|duong|phố|pho)\b",
                address.house_number,
                flags=re.IGNORECASE,
            )
        ):
            address.house_number = hints.house_number

    def _should_override_admin_part(
        self, current: str | None, hint: str | None
    ) -> bool:
        if not hint:
            return False
        if not current or len(current.strip()) < 4:
            return True
        if "," in current:
            return True
        return bool(
            re.search(
                r"\b(quận|quan|huyện|huyen|thị xã|thi xa|thành phố|thanh pho|tp\.?)\b",
                current,
                flags=re.IGNORECASE,
            )
        )

    def _fix_address_parts(self, address: ExtractedAddress) -> None:
        if address.house_number:
            match = re.match(
                r"^\s*(?:số\s*)?([0-9]+[a-zA-Z]?(?:/[0-9]+[a-zA-Z]?)?)\s+(.+)$",
                address.house_number,
                flags=re.IGNORECASE,
            )
            if match and re.search(
                r"\b(ngõ|ngo|ngách|ngach|hẻm|hem|kiệt|kiet|đường|duong|phố|pho)\b",
                match.group(2),
                flags=re.IGNORECASE,
            ):
                address.house_number = match.group(1)
                address.street = self._join_street(match.group(2), address.street)

        if address.house_number or not address.street:
            return

        match = re.match(
            r"^\s*(?:số\s*)?([0-9]+[a-zA-Z]?(?:/[0-9]+[a-zA-Z]?)?)\s+(.+)$",
            address.street,
            flags=re.IGNORECASE,
        )
        if match:
            address.house_number = match.group(1)
            address.street = match.group(2).strip(" ,")

    def _join_street(self, first: str | None, second: str | None) -> str | None:
        parts = []
        for part in (first, second):
            clean = (part or "").strip(" ,")
            if not clean:
                continue
            clean_lower = clean.lower()
            existing_lower = " ".join(parts).lower()
            if existing_lower and (
                clean_lower in existing_lower or existing_lower in clean_lower
            ):
                if len(clean) > len(" ".join(parts)):
                    parts = [clean]
                continue
            if clean_lower not in {p.lower() for p in parts}:
                parts.append(clean)
        return " ".join(parts) if parts else None
