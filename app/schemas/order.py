from pydantic import BaseModel, Field


class ExtractedAddress(BaseModel):
    province: str | None = None
    district_hint: str | None = Field(
        default=None,
        description="Optional old district/city hint, used only for disambiguation.",
    )
    ward: str | None = None
    street: str | None = None
    house_number: str | None = None


class PublicAddress(BaseModel):
    province: str | None = None
    ward: str | None = None
    street: str | None = None
    house_number: str | None = None


class ExtractedOrder(BaseModel):
    name: str | None = None
    phone: str | None = None
    note: str | None = None
    address: ExtractedAddress = Field(default_factory=ExtractedAddress)


class NormalizationCandidate(BaseModel):
    province_name: str
    ward_name: str
    province_code: str | None = None
    ward_code: str | None = None
    score: float
    matched_by: str
    old_province_name: str | None = None
    old_district_name: str | None = None
    old_ward_name: str | None = None


class NormalizedAddress(BaseModel):
    province: str | None = None
    ward: str | None = None
    street: str | None = None
    house_number: str | None = None
    is_normalized: bool = False
    confidence: float = 0.0
    matched_by: str | None = None
    candidates: list[NormalizationCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ParseRequest(BaseModel):
    text: str


class ParseResponse(BaseModel):
    name: str | None = None
    phone: str | None = None
    note: str | None = None
    address: PublicAddress = Field(default_factory=PublicAddress)


class OcrResponse(BaseModel):
    text: str
