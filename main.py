import asyncio
from functools import lru_cache

from fastapi import FastAPI, File, HTTPException, UploadFile

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
from app.services.llm_client import CircuitBreakerOpenError

app = FastAPI(title="Clipboard Parsing & Smart Order API")

# asyncio.Semaphore limits concurrent LLM calls without blocking the event loop
_llm_semaphore = asyncio.Semaphore(get_settings().llm_max_concurrent)

_MAX_INPUT_CHARS = 500


@lru_cache
def get_parser() -> OrderParser:
    return OrderParser(get_settings())


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
        return await get_parser().parse(text, use_llm=True)
    except CircuitBreakerOpenError:
        raise HTTPException(
            status_code=503,
            detail="LLM service temporarily unavailable, please retry later",
        )
    finally:
        _llm_semaphore.release()


def _check_input_length(text: str) -> None:
    if len(text) > _MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"input_too_long: max {_MAX_INPUT_CHARS} chars, got {len(text)}",
        )


@app.post("/parse-text", response_model=ParseResponse)
async def parse_text(request: ParseRequest) -> ParseResponse:
    _check_input_length(request.text)
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
