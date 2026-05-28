import json
import re
from typing import Any

import requests

from app.core_config import Settings
from app.schemas.order import ExtractedOrder


SYSTEM_PROMPT = """Trích xuất đơn giao hàng Việt Nam. Chỉ trả JSON hợp lệ, không giải thích.
Không bịa. Thiếu/không chắc thì null. Không phải đơn hàng thì tất cả null.
Schema: {"name":string|null,"note":string|null,"address":{"province":string|null,"district_hint":string|null,"ward":string|null,"street":string|null,"house_number":string|null}}
Quy tắc: phone đã xử lý, không trả phone. province chỉ điền nếu text nói rõ tỉnh/thành hoặc viết tắt như HN/HCM/TPHCM; không tự suy diễn tỉnh chỉ từ quận/huyện.
district_hint là quận/huyện/thị xã/tp cấp huyện.
Nếu thiếu phường/xã nhưng có quận/huyện thì để quận/huyện vào ward.
street là đường/ngõ/ngách/hẻm/khu phố/KĐT/chung cư nếu đó là landmark đường đi.
house_number là số nhà/căn hộ/tòa nhà/POI chính, ví dụ "Căn hộ 12B, Chung cư Sunrise, 90" hoặc "Trường THPT Chu Văn An".
Không bịa field thiếu.
"""

# JSON schema dùng cho grammar-constrained generation (llamacpp)
_OUTPUT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "note": {"type": ["string", "null"]},
        "address": {
            "type": "object",
            "properties": {
                "province": {"type": ["string", "null"]},
                "district_hint": {"type": ["string", "null"]},
                "ward": {"type": ["string", "null"]},
                "street": {"type": ["string", "null"]},
                "house_number": {"type": ["string", "null"]},
            },
            "required": ["province", "district_hint", "ward", "street", "house_number"],
        },
    },
    "required": ["name", "note", "address"],
}


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
        self._llm: Any = None
        # Eager load ở startup để request đầu không bị chậm
        if settings.llm_provider == "llamacpp":
            self._get_llm()

    def _get_llm(self) -> Any:
        if self._llm is None:
            from llama_cpp import Llama  # type: ignore[import]

            self._llm = Llama(
                model_path=str(self.settings.llm_model_path),
                n_ctx=self.settings.llm_num_ctx,
                n_threads=self.settings.llm_threads,
                n_gpu_layers=0,  # CPU only
                verbose=False,
            )
        return self._llm

    def extract_order(self, text: str) -> tuple[ExtractedOrder, Any]:
        if self.settings.llm_provider == "llamacpp":
            raw = self._llamacpp_chat(text)
        elif self.settings.llm_provider == "openai_compatible":
            raw = self._openai_compatible_chat(text)
        else:
            raw = self._ollama_chat(text)
        data = _extract_json_object(raw)
        return ExtractedOrder.model_validate(data), raw

    def _llamacpp_chat(self, text: str) -> str:
        llm = self._get_llm()
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=self.settings.llm_max_tokens,
            response_format={
                "type": "json_object",
                "schema": _OUTPUT_JSON_SCHEMA,
            },
        )
        return response["choices"][0]["message"]["content"]

    def _ollama_chat(self, text: str) -> str:
        url = self.settings.llm_base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": self.settings.llm_model,
            "stream": False,
            "format": "json",
            "keep_alive": self.settings.llm_keep_alive,
            "options": {
                "temperature": 0,
                "num_predict": self.settings.llm_max_tokens,
                "num_ctx": self.settings.llm_num_ctx,
            },
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
            "max_tokens": self.settings.llm_max_tokens,
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
