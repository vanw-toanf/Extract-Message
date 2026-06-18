"""OpenAI LLM client: async, structured outputs, prompt caching."""
import re

import openai
from openai import AsyncOpenAI

from app.core_config import Settings
from app.schemas.order import (
    ExtractedAddress,
    ExtractedOrder,
    LLMOrderStrict,
)
from app.services.base_client import BaseHttpClient

MAX_INPUT_LENGTH = 5000  # chars; hard limit before touching the API

# ── System Prompt (static → OpenAI auto-caches when > 1024 tokens) ────────────
SYSTEM_PROMPT = """Bạn là engine trích xuất thông tin đơn giao hàng Việt Nam. Luôn trả về JSON đúng schema, không giải thích.

=== SCHEMA ===
{
  "short_reasoning": string | null,
  "recipient_name": string | null,
  "phone_number": "[PHONE]" | null,
  "note": string | null,
  "address_raw": string | null,
  "address_info": {
    "address_number": string | null,
    "street": string | null,
    "neighborhood": string | null,
    "municipality": string | null,
    "sub_region": string | null,
    "country": "VNM" | null
  }
}

=== LUẬT BẮT BUỘC ===

[R1] Không bịa dữ liệu. Thiếu thông tin hoặc không chắc → null.
[R2] Input không phải đơn hàng (không có địa chỉ/người nhận) → tất cả trường null.
[R3] phone_number: Số điện thoại đã được xử lý và thay bằng token [PHONE] trong input. Nếu có [PHONE] → phone_number = "[PHONE]". Không có → null.
[R4] address_raw: Copy nguyên văn phần địa chỉ từ input, không chỉnh sửa.
[R5] address_info: Phân tách địa chỉ thô, chưa chuẩn hóa.
  - Địa chỉ 2 cấp mới (sau sáp nhập 2025): neighborhood = null, municipality = xã/phường/thị trấn mới, sub_region = tỉnh/thành phố mới.
  - Địa chỉ 3 cấp cũ: neighborhood = xã/phường cũ, municipality = quận/huyện/thị xã/TP cấp huyện cũ, sub_region = tỉnh/thành cũ.
  - Nếu input chỉ có tỉnh/thành phố (không có phường/quận): municipality = null, sub_region = tên tỉnh/thành. VD: "45 Lê Lợi, Hà Nội" → municipality=null, sub_region="Hà Nội".
  - thôn/xóm/ấp là đơn vị dưới xã, KHÔNG phải cấp hành chính xã/phường → đưa vào address_number cùng POI, không đặt vào neighborhood/municipality. VD: "Quán giằng, thôn Hạ, xã A Sào, Hưng Yên" → address_number="Quán giằng, thôn Hạ", neighborhood=null, municipality="xã A Sào", sub_region="Hưng Yên".
  - street: đường/ngõ/ngách/hẻm/khu phố/KĐT/chung cư là landmark đường đi.
  - address_number: số nhà/căn hộ/tòa nhà/POI chính.
  - Không tự suy diễn tỉnh/thành chỉ từ quận/huyện trừ khi input nói rõ.
  - country: "VNM" nếu có địa chỉ, null nếu không có địa chỉ.

[R6] NHẬN DIỆN NGƯỜI NHẬN (quan trọng nhất):
  - Người nhận là người sẽ NHẬN hàng tại địa chỉ giao, không phải người nhắn tin, người gọi, shop, hay courier.
  - "giao cho [Tên]", "ship tới [Tên]" → [Tên] là người nhận.
  - "[Tên] ơi", "anh/chị/em [Tên] ơi", "shop [Tên] ơi" → [Tên] là người được gọi (shop/courier), KHÔNG phải người nhận → recipient_name = null nếu không có tên khác.
  - "chị/anh/em (hoặc viết tắt là a/c/e) [A] lấy đơn/lấy hàng để giao cho anh/em/chị [B]" → [B] là người nhận, [A] là courier.
  - "[A] ơi giao cho mình nha", "khách anh/chị/cô/chú [A]", "mình/tôi/em ở [địa chỉ]" → người viết là người nhận, name = null (không biết tên).

[R7] ĐỊA CHỈ KHI CÓ NHIỀU ĐỊA CHỈ:
  - "lấy hàng ở A, giao tới B" → address là B (địa chỉ giao đến, destination).
  - "đổi địa chỉ thành B" / "không giao ở A nữa, giao ở B" → address là B (địa chỉ mới).
  - "lấy tại A" mà không có địa chỉ giao → address_raw = null.

[R8] note: Ghi chú giao hàng bao gồm:
  - Thời gian: "giao buổi sáng", "giao sau 5h"
  - Liên lạc: "gọi trước 30p", "nhắn tin trước"
  - Vị trí tìm nhà: "nhà trong hẻm", "nhà cuối ngõ", "cổng màu xanh", "tầng 3"
  - Nơi để hàng: "để ở cổng", "để trước cửa", "gửi bảo vệ"
  - Hàng hóa: "hàng dễ vỡ", "không bẻ gập"
  Không bao gồm số nhà, tên đường, phường/quận vào note.

[R9] short_reasoning: Tối đa 15 từ. Quy tắc:
  - Đơn giản (1 người, 1 địa chỉ, rõ ràng) → bắt buộc trả về null.
  - Phức tạp (có 2 người cần phân biệt, đổi địa chỉ, ambiguous) → ghi lý do ngắn gọn.

=== VÍ DỤ ===

[Đơn đơn giản → short_reasoning: null]
User: Trần Bích Ngọc, [PHONE], Căn hộ 12B, Chung cư Sunrise, 90 Võ Văn Ngân, Thủ Đức, gọi trước 30p
Assistant: {"short_reasoning":null,"recipient_name":"Trần Bích Ngọc","phone_number":"[PHONE]","note":"gọi trước 30p","address_raw":"Căn hộ 12B, Chung cư Sunrise, 90 Võ Văn Ngân, Thủ Đức","address_info":{"address_number":"Căn hộ 12B, Chung cư Sunrise, 90","street":"Võ Văn Ngân","neighborhood":null,"municipality":"Thủ Đức","sub_region":null,"country":"VNM"}}

[Hai người: A lấy đơn giao cho B → B là người nhận]
User: chị Lan lấy đơn giao cho anh Minh nhé, [PHONE], 22 Ngô Quyền, Hoàn Kiếm, Hà Nội
Assistant: {"short_reasoning":"Lan giao, Minh nhận","recipient_name":"Minh","phone_number":"[PHONE]","note":null,"address_raw":"22 Ngô Quyền, Hoàn Kiếm, Hà Nội","address_info":{"address_number":"22","street":"Ngô Quyền","neighborhood":null,"municipality":"Hoàn Kiếm","sub_region":"Hà Nội","country":"VNM"}}

[Gọi tên shop/courier bằng "[Tên] ơi" → tên đó không phải người nhận]
User: chị Mai ơi giao cho mình nha, mình đang ở 88 Nguyễn Du Q1, [PHONE]
Assistant: {"short_reasoning":"Mai là courier, mình là người nhận","recipient_name":null,"phone_number":"[PHONE]","note":null,"address_raw":"88 Nguyễn Du Q1","address_info":{"address_number":"88","street":"Nguyễn Du","neighborhood":null,"municipality":"Quận 1","sub_region":null,"country":"VNM"}}

[Đổi địa chỉ giao → chỉ lấy địa chỉ mới]
User: anh ơi đổi địa chỉ giao nhé, không giao ở 12 Lý Thái Tổ nữa, giao tới 88 Nguyễn Du, Hoàn Kiếm, Hà Nội thôi, [PHONE]
Assistant: {"short_reasoning":"địa chỉ mới: 88 Nguyễn Du","recipient_name":null,"phone_number":"[PHONE]","note":null,"address_raw":"88 Nguyễn Du, Hoàn Kiếm, Hà Nội","address_info":{"address_number":"88","street":"Nguyễn Du","neighborhood":null,"municipality":"Hoàn Kiếm","sub_region":"Hà Nội","country":"VNM"}}
"""


# ── LLM Client ────────────────────────────────────────────────────────────────

class LLMClient(BaseHttpClient):
    _RETRYABLE = (
        openai.RateLimitError,
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.InternalServerError,  # covers HTTP 500 and 503
    )

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
        )
        self._model = settings.llm_model
        self._max_tokens = settings.llm_max_tokens

    async def extract_order(self, text: str) -> tuple[ExtractedOrder, LLMOrderStrict]:
        """Input guardrail → circuit breaker + retry → structured output → guardrail."""
        if len(text) > MAX_INPUT_LENGTH:
            raise ValueError(
                f"Input too long: {len(text)} chars (max {MAX_INPUT_LENGTH})"
            )
        data: LLMOrderStrict = await self._protected_call(lambda: self._single_call(text))
        self._post_process(data)
        return self._to_internal(data), data

    async def aclose(self) -> None:
        await self._client.close()

    async def _single_call(self, text: str) -> LLMOrderStrict:
        response = await self._client.beta.chat.completions.parse(
            model=self._model,
            temperature=0,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format=LLMOrderStrict,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError(
                "OpenAI returned null parsed result (model refused or schema mismatch)"
            )
        return parsed

    def _post_process(self, data: LLMOrderStrict) -> None:
        info = data.address_info
        if info.country is not None and info.country != "VNM":
            info.country = "VNM"
        if not data.address_raw:
            info.address_number = None
            info.street = None
            info.neighborhood = None
            info.municipality = None
            info.sub_region = None
            info.country = None

    _DISTRICT_PREFIX_RE = re.compile(
        r"^\s*(quận|huyện|thị\s+xã|q\.)\s*",
        re.IGNORECASE,
    )
    # thôn/xóm/ấp là đơn vị dưới xã — không phải cấp hành chính phường/xã
    _HAMLET_PREFIX_RE = re.compile(
        r"^\s*(thôn|xóm|ấp|khu phố|khu|khối)\s*",
        re.IGNORECASE,
    )

    def _to_internal(self, data: LLMOrderStrict) -> ExtractedOrder:
        info = data.address_info
        neighborhood = info.neighborhood
        municipality = info.municipality

        if neighborhood and self._HAMLET_PREFIX_RE.match(neighborhood):
            # LLM nhầm thôn/xóm/ấp vào neighborhood — đây không phải cấp xã/phường
            # municipality thực sự là xã/phường, hoặc quận/huyện cần giữ làm district_hint
            if municipality and self._DISTRICT_PREFIX_RE.match(municipality):
                ward = None
                district_hint = municipality
            else:
                ward = municipality
                district_hint = None
        elif neighborhood:
            ward = neighborhood
            district_hint = municipality
        elif municipality and self._DISTRICT_PREFIX_RE.match(municipality):
            ward = None
            district_hint = municipality
        else:
            ward = municipality
            district_hint = None

        return ExtractedOrder(
            name=data.recipient_name,
            phone=None if data.phone_number in {None, "[PHONE]"} else data.phone_number,
            note=data.note,
            address_raw=data.address_raw,
            address=ExtractedAddress(
                province=info.sub_region,
                district_hint=district_hint,
                ward=ward,
                street=info.street,
                house_number=info.address_number,
            ),
        )
