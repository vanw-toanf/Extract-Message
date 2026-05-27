import json
import re
from typing import Any

import requests

from app.core_config import Settings
from app.schemas.order import ExtractedOrder


SYSTEM_PROMPT = """Bạn là hệ thống trích xuất thông tin đơn giao hàng tại Việt Nam.
Chỉ trả về JSON hợp lệ, không markdown, không giải thích.
Không tự bịa dữ liệu. Nếu thiếu hoặc không chắc, dùng null.
Nếu nội dung không phải tin nhắn/đơn giao hàng hoặc không có thông tin khách hàng,
hãy trả JSON đúng schema với tất cả trường là null.

Schema bắt buộc:
{
  "name": string|null,
  "note": string|null,
  "address": {
    "province": string|null,
    "district_hint": string|null,
    "ward": string|null,
    "street": string|null,
    "house_number": string|null
  }
}

Quy tắc:
- province là tỉnh/thành phố khách nhập, có thể là tên cũ hoặc tên mới.
- district_hint là quận/huyện/thành phố cấp huyện nếu xuất hiện trong text; dùng để phân biệt xã/phường trùng tên.
- ward là xã/phường/thị trấn khách nhập, có thể là tên cũ hoặc tên mới.
- street gồm tên đường/ngõ/ngách/hẻm/ấp/thôn/khu phố nếu có.
- house_number là số nhà hoặc số hẻm/ngõ chính nếu có.
- Nếu chỉ có số nhà, xã/phường, tỉnh/thành phố mà không có đường/ngõ/ngách/hẻm,
  street phải là null. Tuyệt đối không tự bịa tên đường.
- note là ghi chú giao hàng, ví dụ gọi trước, giờ giao, COD, màu nhà, gần địa điểm.
- name có thể đi kèm cách gọi như anh/chị/cô/chú/bạn + tên, ví dụ "chị Mai", "anh Nam".
- phone đã được hệ thống regex xử lý trước, không cần trích xuất số điện thoại.
- Nếu thấy "quận", "huyện", "q.", "h.", "tp. cấp huyện" thì điền vào district_hint, không bỏ qua.
- Nếu địa chỉ có "số X ngõ Y đường Z", house_number là "số X", street giữ phần "ngõ Y đường Z".
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text or "", flags=re.S)
    if not match:
        raise ValueError("LLM response does not contain a JSON object")
    return json.loads(match.group(0))


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def extract_order(self, text: str) -> tuple[ExtractedOrder, Any]:
        if self.settings.llm_provider == "openai_compatible":
            raw = self._openai_compatible_chat(text)
        else:
            raw = self._ollama_chat(text)
        data = _extract_json_object(raw)
        return ExtractedOrder.model_validate(data), raw

    def _ollama_chat(self, text: str) -> str:
        url = self.settings.llm_base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": self.settings.llm_model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        response = requests.post(
            url, json=payload, timeout=self.settings.llm_timeout_seconds
        )
        response.raise_for_status()
        body = response.json()
        return body.get("message", {}).get("content", "")

    def _openai_compatible_chat(self, text: str) -> str:
        base_url = self.settings.llm_base_url.rstrip("/")
        if base_url.endswith("/v1"):
            url = base_url + "/chat/completions"
        else:
            url = base_url + "/v1/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        response = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            timeout=self.settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        return body["choices"][0]["message"]["content"]
