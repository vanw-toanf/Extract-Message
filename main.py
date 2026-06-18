import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core_config import get_settings
from app.pipeline.ocr import image_bytes_to_text
from app.pipeline.parser import OrderParser
from app.schemas.order import (
    ExtractedAddress,
    NormalizedAddress,
    OcrResponse,
    ParseRequest,
    ParseResponse,
)
from app.pipeline.text_utils import short_province, strip_accents
from app.schemas.order import ExtractedAddress as _ExtractedAddress
from app.services.base_client import CircuitBreakerOpenError
from app.services.goong_client import GeocodeResult, GoongClient, GoongGeocodeFailed

# asyncio.Semaphore limits concurrent LLM calls without blocking the event loop
_llm_semaphore = asyncio.Semaphore(get_settings().llm_max_concurrent)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Eager-init singletons so first request pays no setup cost.
    # httpx.AsyncClient and AsyncOpenAI keep their connection pools alive
    # for the full server lifetime.
    get_settings()
    get_parser()
    get_goong()
    yield
    # Gracefully drain connection pools on shutdown.
    await get_goong().aclose()
    await get_parser().aclose()


app = FastAPI(title="Clipboard Parsing & Smart Order API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

_MAX_INPUT_CHARS = 5000  # R-07: API-level input limit


@lru_cache
def get_parser() -> OrderParser:
    return OrderParser(get_settings())


@lru_cache
def get_goong() -> GoongClient:
    return GoongClient(get_settings())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _parse_with_llm(text: str) -> ParseResponse:
    try:
        await asyncio.wait_for(
            _llm_semaphore.acquire(),
            timeout=get_settings().llm_queue_timeout,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=429, detail="Server busy, please retry later")
    try:
        result = await get_parser().parse(text, use_llm=True)
    except CircuitBreakerOpenError:
        raise HTTPException(
            status_code=503,
            detail="LLM service temporarily unavailable, please retry later",
        )
    finally:
        _llm_semaphore.release()

    # R-04: address must be present
    if not (result.address_new or result.address_raw):
        raise HTTPException(status_code=422, detail="address_not_found")

    # Without province we can't validate any geocoding result — skip the API call
    if not result.address_info or not result.address_info.sub_region:
        raise HTTPException(status_code=422, detail="geocode_failed")

    # R-05: geocode with fallback chain
    try:
        lat, lng = await _geocode_with_fallback(result)
        result.lat = lat
        result.lng = lng
    except GoongGeocodeFailed:
        raise HTTPException(status_code=422, detail="geocode_failed")

    return result


_goong_province = short_province


async def _geocode_with_fallback(result: ParseResponse) -> tuple[float, float]:
    """Try geocoding with progressively simpler addresses.

    1. address_new (normalized admin names)
    2. address_raw (original text, in case normalizer introduced wrong names)
    3. house_number + street + province (drop municipality — often source of ambiguity
       when old/new admin names mismatch in Goong's DB)

    Each candidate is also validated: Goong's compound.province is mapped from old
    to new admin system (via AddressNormalizer) and compared with expected sub_region.
    """
    goong = get_goong()
    info = result.address_info
    candidates: list[str] = []

    if result.address_new:
        candidates.append(result.address_new)
    if result.address_raw and result.address_raw != result.address_new:
        candidates.append(result.address_raw)
    # minimal: street + province (short name), no municipality
    province = _goong_province(info.sub_region) if info.sub_region else None
    minimal = ", ".join(
        p for p in [info.address_number, info.street, province] if p
    )
    if minimal and minimal not in candidates:
        candidates.append(minimal)

    last_exc: GoongGeocodeFailed | None = None
    for addr in candidates:
        try:
            geo = await goong.geocode(addr)
        except GoongGeocodeFailed as exc:
            last_exc = exc
            continue
        if not _province_matches(geo, info.sub_region):
            last_exc = GoongGeocodeFailed(
                f"Province mismatch: expected {info.sub_region!r}, "
                f"Goong returned {geo.compound_province!r}"
            )
            continue
        return geo.lat, geo.lng

    raise last_exc or GoongGeocodeFailed("All geocode attempts failed")


def _province_matches(geo: GeocodeResult, expected_sub_region: str | None) -> bool:
    """Check if Goong compound.province (old admin system) corresponds to expected
    province (new admin system) by mapping through AddressNormalizer.

    Returns True when:
    - No expected province (can't validate)
    - No Goong compound province (can't validate)
    - Normalizer maps old→new province and it fuzzy-matches expected
    """
    # Goong couldn't determine province → coordinate is ambiguous, reject
    if not geo.compound_province:
        return False
    # We have no expected province to validate against → trust Goong's result
    if not expected_sub_region:
        return True

    # Map Goong's old-system address to new province via AddressNormalizer DB
    old_addr = _ExtractedAddress(
        province=geo.compound_province,
        district_hint=geo.compound_district,
        ward=geo.compound_commune,
    )
    normalized = get_parser().address_normalizer.normalize(old_addr)
    mapped_province = normalized.province or geo.compound_province

    # Normalize both for comparison (strip prefixes, remove diacritics)
    a = strip_accents(_goong_province(mapped_province).lower())
    b = strip_accents(_goong_province(expected_sub_region).lower())
    # Allow partial match — e.g. "ha noi" in "thu do ha noi"
    return a == b or a in b or b in a


def _check_input_length(text: str) -> None:
    if len(text) > _MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail="input_too_long",
        )


@app.post("/parse-text", response_model=ParseResponse)
async def parse_text(request: ParseRequest) -> ParseResponse:
    _check_input_length(request.text)
    asyncio.create_task(_increment_request())
    return await _parse_with_llm(request.text)


@app.post("/ocr-image", response_model=OcrResponse)
async def ocr_image(file: UploadFile = File(...)) -> OcrResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")
    try:
        text = image_bytes_to_text(await file.read())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc
    return OcrResponse(text=text)


@app.post("/parse-image", response_model=ParseResponse)
async def parse_image(file: UploadFile = File(...)) -> ParseResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")
    try:
        text = image_bytes_to_text(await file.read())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc
    _check_input_length(text)
    return await _parse_with_llm(text)


@app.post("/normalize-address", response_model=NormalizedAddress)
def normalize_address(address: ExtractedAddress) -> NormalizedAddress:
    return get_parser().address_normalizer.normalize(address)


_FEEDBACK_PATH     = Path("data/feedback.jsonl")
_REQUEST_COUNT_PATH = Path("data/request_count.txt")
_count_lock        = asyncio.Lock()


async def _increment_request() -> None:
    async with _count_lock:
        n = int(_REQUEST_COUNT_PATH.read_text()) if _REQUEST_COUNT_PATH.exists() else 0
        _REQUEST_COUNT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _REQUEST_COUNT_PATH.write_text(str(n + 1))


class FeedbackRequest(BaseModel):
    input_text: str
    api_response: dict
    corrections: dict   # {"f-name": {"original": "...", "corrected": "..."}}


@app.post("/feedback", status_code=204)
async def submit_feedback(item: FeedbackRequest) -> None:
    if not item.corrections:
        return
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "input_text": item.input_text,
        "api_response": item.api_response,
        "corrections": item.corrections,
    }
    _FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _FEEDBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


@app.get("/feedback")
async def get_feedback() -> dict:
    records = []
    if _FEEDBACK_PATH.exists():
        for line in _FEEDBACK_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    total_requests = 0
    if _REQUEST_COUNT_PATH.exists():
        try:
            total_requests = int(_REQUEST_COUNT_PATH.read_text())
        except ValueError:
            pass
    return {"total_requests": total_requests, "records": records}
