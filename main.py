from functools import lru_cache

from fastapi import FastAPI

from app.core_config import get_settings
from app.pipeline.parser import OrderParser
from app.schemas.order import ExtractedAddress, NormalizedAddress, ParseRequest, ParseResponse


app = FastAPI(title="Clipboard Parsing & Smart Order API")


@lru_cache
def get_parser() -> OrderParser:
    return OrderParser(get_settings())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/parse-text", response_model=ParseResponse, response_model_exclude_none=True)
def parse_text(request: ParseRequest) -> ParseResponse:
    return get_parser().parse(request.text, use_llm=request.use_llm)


@app.post("/normalize-address", response_model=NormalizedAddress)
def normalize_address(address: ExtractedAddress) -> NormalizedAddress:
    return get_parser().address_normalizer.normalize(address)
