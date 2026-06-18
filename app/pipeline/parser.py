import re

from app.core_config import Settings
from app.pipeline.address_normalizer import AddressNormalizer
from app.pipeline.phone_extractor import extract_phone, mask_phone, normalize_phone
from app.pipeline.rule_extractor import extract_rule_hints, extract_rule_note
from app.pipeline.text_utils import canonical_province, compact_text
from app.schemas.order import (
    ExtractedAddress,
    ExtractedOrder,
    FinalAddressInfo,
    ParseResponse,
)
from app.services.base_client import CircuitBreakerOpenError
from app.services.llm_client import LLMClient


class OrderParser:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm = LLMClient(settings)
        self.address_normalizer = AddressNormalizer(
            settings.admin_db_path, settings.fuzzy_threshold
        )

    async def parse(self, text: str, use_llm: bool = True) -> ParseResponse:
        cleaned = compact_text(text)
        regex_phone = extract_phone(cleaned)
        rule_name, rule_address = extract_rule_hints(cleaned)
        rule_note = extract_rule_note(cleaned)
        llm_input = compact_text(mask_phone(cleaned))

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
                extracted, _ = await self.llm.extract_order(llm_input)
            except (CircuitBreakerOpenError, ValueError):
                raise
            except Exception:
                extracted = ExtractedOrder()

        if regex_phone:
            extracted.phone = regex_phone
        if not extracted.name and rule_name:
            extracted.name = rule_name
        if rule_note and not extracted.note:
            extracted.note = rule_note
        self._merge_address_hints(extracted.address, rule_address)

        extracted.phone = self._normalize_phone(extracted.phone)
        self._fix_address_parts(extracted.address)
        address_raw = extracted.address_raw or self._format_address(
            extracted.address.house_number,
            extracted.address.street,
            extracted.address.ward,
            extracted.address.district_hint,
            extracted.address.province,
        )
        # Guard: LLM sometimes puts a district name in the province field (e.g. "Gia Lâm"
        # instead of "Hà Nội"). Detect this before normalization so the province filter
        # doesn't exclude the correct province's records from candidate scoring.
        if not extracted.address.district_hint and extracted.address.province:
            inferred_prov = self.address_normalizer.infer_province_from_municipality(
                extracted.address.province
            )
            if inferred_prov and inferred_prov.lower() != extracted.address.province.lower():
                extracted.address.district_hint = extracted.address.province
                extracted.address.province = inferred_prov

        normalized_address = self.address_normalizer.normalize(extracted.address)

        address_number = (
            normalized_address.house_number or extracted.address.house_number
        )
        street = normalized_address.street or extracted.address.street
        # Trust normalizer's ward/province when confident and unambiguous.
        # When ambiguous (e.g. "Phường 14, Q10" split into two new wards),
        # fall back to district_hint — cleaner than showing the old ward name.
        if normalized_address.is_normalized:
            municipality = (
                normalized_address.ward
                or extracted.address.ward
                or extracted.address.district_hint
            )
            sub_region = normalized_address.province or extracted.address.province
        else:
            municipality = extracted.address.district_hint or extracted.address.ward
            sub_region = normalized_address.province or extracted.address.province
        # Model đôi khi nhầm tên quận/phường vào sub_region (vd: "Thủ Đức" thay vì municipality).
        # Nếu sub_region tra được trong unique map và kết quả khác với chính nó → đó là municipality.
        if sub_region and not municipality:
            inferred = self.address_normalizer.infer_province_from_municipality(sub_region)
            if inferred and inferred.lower() != sub_region.lower():
                municipality = sub_region
                sub_region = inferred
        if not sub_region and municipality:
            sub_region = self.address_normalizer.infer_province_from_municipality(municipality)
        sub_region = canonical_province(sub_region)
        address_new = self._format_address(
            address_number,
            street,
            municipality,
            sub_region,
        )
        has_address = bool(
            address_raw or address_number or street or municipality or sub_region
        )
        return ParseResponse(
            recipient_name=self._strip_recipient_honorific(extracted.name),
            phone_number=extracted.phone,
            note=extracted.note,
            address_raw=address_raw,
            address_new=address_new,
            address_info=FinalAddressInfo(
                address_number=address_number,
                street=street,
                municipality=municipality,
                sub_region=sub_region,
                country="VNM" if has_address else None,
            ),
        )

    async def aclose(self) -> None:
        await self.llm.aclose()

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
            if field == "ward" and hints.ward:
                # Don't use rule ward hint when its core name is a substring of any
                # already-extracted address field (street OR house_number).
                # E.g. WARD_RE matches "xã Paris" inside street/POI "Công xã Paris".
                address_text = " ".join(
                    x for x in (address.street, address.house_number) if x
                ).lower()
                if address_text:
                    ward_core = re.sub(
                        r"^(phường|xã|thị trấn|p\.?|x\.?|tt\.?)\s+",
                        "",
                        hints.ward,
                        flags=re.IGNORECASE,
                    ).strip().lower()
                    if ward_core and ward_core in address_text:
                        continue
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

    def _format_address(
        self,
        address_number: str | None,
        street: str | None,
        municipality: str | None,
        sub_region: str | None,
        province: str | None = None,
    ) -> str | None:
        first_line = self._join_street(address_number, street)
        parts: list[str] = []
        for part in (first_line, municipality, sub_region, province):
            clean = (part or "").strip(" ,")
            if clean and clean.lower() not in {item.lower() for item in parts}:
                parts.append(clean)
        return ", ".join(parts) if parts else None

    _NON_NAME_WORDS: frozenset[str] = frozenset({
        "nhé", "nha", "nhe", "nhỉ", "nhi", "ạ", "à", "ư", "ừ",
        "ha", "hả", "ha", "nhờ", "nho", "vậy", "vay", "thôi", "thoi",
        "được", "duoc", "ok", "oke", "okay", "rồi", "roi", "xong",
    })

    def _strip_recipient_honorific(self, name: str | None) -> str | None:
        if not name:
            return None
        cleaned = re.sub(
            r"^(?:anh|chị|chi|cô|co|chú|chu|bạn|ban|bé|be|b|c|a)\s+",
            "",
            name.strip(),
            flags=re.IGNORECASE,
        )
        # Strip particles bám vào cuối tên (e.g. "Quỳnh Anh nhé" → "Quỳnh Anh")
        cleaned = re.sub(
            r"\s+(?:nhé|nha|nhe|nhỉ|nhi|ạ|à|nhờ|vậy|thôi|được|ok|oke|ha|hả|rồi|xong)$",
            "",
            cleaned.strip(),
            flags=re.IGNORECASE,
        )
        if cleaned.lower() in self._NON_NAME_WORDS or len(cleaned) < 2:
            return None
        return cleaned or None
