import threading
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


app = FastAPI(title="Clipboard Parsing & Smart Order API")

_llm_semaphore = threading.Semaphore(int(get_settings().llm_max_concurrent))


@lru_cache
def get_parser() -> OrderParser:
    return OrderParser(get_settings())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _parse_with_llm(text: str) -> ParseResponse:
    acquired = _llm_semaphore.acquire(timeout=get_settings().llm_queue_timeout)
    if not acquired:
        raise HTTPException(status_code=429, detail="Server busy, please retry later")
    try:
        return get_parser().parse(text, use_llm=True)
    finally:
        _llm_semaphore.release()


@app.post("/parse-text", response_model=ParseResponse)
def parse_text(request: ParseRequest) -> ParseResponse:
    return _parse_with_llm(request.text)


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
async def parse_image(
    file: UploadFile = File(...),
) -> ParseResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")
    try:
        text = image_bytes_to_text(await file.read())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc
    return _parse_with_llm(text)


@app.post("/normalize-address", response_model=NormalizedAddress)
def normalize_address(address: ExtractedAddress) -> NormalizedAddress:
    return get_parser().address_normalizer.normalize(address)
