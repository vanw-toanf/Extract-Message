#!/usr/bin/env python3
"""
Smoke test cho OpenAI integration.

Cách chạy:
    conda activate rag
    python test_llm.py

Không cần server đang chạy — test trực tiếp LLMClient.
"""
import asyncio

from dotenv import load_dotenv

load_dotenv()

from app.core_config import get_settings
from app.services.llm_client import LLMClient

CASES = [
    # (id, description, input, expected_name, expect_address)
    (
        "P-01",
        "Happy path",
        "Nguyễn Văn A, 0912345678, 45 Lê Lợi Q1 HCM, giao buổi sáng",
        "Nguyễn Văn A",
        True,
    ),
    (
        "P-03",
        "Tên trong câu gọi không phải người nhận",
        "chị Mai ơi giao cho mình nha, đang ở 88 Nguyễn Du",
        None,
        True,
    ),
    (
        "P-05",
        "Ship cho Hùng",
        "order mới nè: 5 áo size M màu đen, ship cho Hùng, 0911222333, 22 Hai Bà Trưng",
        "Hùng",
        True,
    ),
    (
        "E-hard",
        "chị A lấy đơn giao cho anh B",
        "chị Lan lấy đơn để giao cho anh Minh nha, 0987654321, 22 Ngô Quyền, Hoàn Kiếm, Hà Nội",
        "Minh",
        True,
    ),
    (
        "E-05",
        "Đổi địa chỉ giao",
        "anh ơi đổi địa chỉ nhé, không giao ở 12 Lý Thái Tổ nữa, giao tới 88 Nguyễn Du, HN thôi",
        None,
        True,
    ),
    (
        "guard-len",
        "Input quá dài (> 500 ký tự) → ValueError",
        "a" * 501,
        "ERROR_EXPECTED",
        False,
    ),
]

GREEN = "\033[32m"
RED   = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


async def run_case(client: LLMClient, case_id: str, desc: str, text: str,
                   expected_name: str | None, expect_address: bool) -> bool:
    if expected_name == "ERROR_EXPECTED":
        try:
            await client.extract_order(text)
            print(f"{RED}FAIL{RESET} [{case_id}] {desc} — expected ValueError but got result")
            return False
        except ValueError as e:
            print(f"{GREEN}PASS{RESET} [{case_id}] {desc} — ValueError raised: {e}")
            return True

    try:
        order, raw = await client.extract_order(text)
    except Exception as e:
        print(f"{RED}FAIL{RESET} [{case_id}] {desc} — exception: {type(e).__name__}: {e}")
        return False

    ok_name = order.name == expected_name
    ok_addr = bool(order.address_raw) == expect_address

    reasoning = raw.short_reasoning
    status = f"{GREEN}PASS{RESET}" if (ok_name and ok_addr) else f"{RED}FAIL{RESET}"

    name_str    = f"name={order.name!r}"
    addr_str    = f"addr={order.address_raw!r}"
    reason_str  = f"reasoning={reasoning!r}"

    print(f"{status} [{case_id}] {desc}")
    print(f"       {name_str}  |  {addr_str}  |  {reason_str}")
    if not ok_name:
        print(f"       {YELLOW}expected name={expected_name!r}{RESET}")
    if not ok_addr:
        print(f"       {YELLOW}expected address present={expect_address}{RESET}")

    return ok_name and ok_addr


async def main() -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        print(f"{RED}ERROR{RESET}: OPENAI_API_KEY not set in .env")
        return

    print(f"Model: {settings.llm_model}  |  max_tokens: {settings.llm_max_tokens}\n")
    client = LLMClient(settings)

    results = []
    for case_id, desc, text, expected_name, expect_addr in CASES:
        passed = await run_case(client, case_id, desc, text, expected_name, expect_addr)
        results.append(passed)
        print()

    passed = sum(results)
    total  = len(results)
    color  = GREEN if passed == total else RED
    print(f"{'─'*50}")
    print(f"{color}{passed}/{total} cases passed{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
