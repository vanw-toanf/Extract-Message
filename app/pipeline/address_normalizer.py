import json
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from app.pipeline.text_utils import normalize_key
from app.schemas.order import (
    ExtractedAddress,
    NormalizationCandidate,
    NormalizedAddress,
)


class AddressNormalizer:
    def __init__(self, db_path: Path, fuzzy_threshold: int = 84):
        self.db_path = db_path
        self.fuzzy_threshold = fuzzy_threshold
        self.records = self._load_records(db_path)

    def _load_records(self, db_path: Path) -> list[dict[str, Any]]:
        with db_path.open("r", encoding="utf-8") as f:
            provinces = json.load(f)

        records: list[dict[str, Any]] = []
        for province in provinces:
            province_name = province.get("province_name")
            province_code = province.get("province_code")
            for ward in province.get("wards", []):
                base = {
                    "province_name": province_name,
                    "province_code": province_code,
                    "ward_name": ward.get("ward_name"),
                    "ward_code": ward.get("ward_code"),
                }

                records.append(
                    {
                        **base,
                        "source": "new",
                        "old_province_name": None,
                        "old_district_name": None,
                        "old_ward_name": None,
                        "province_key": normalize_key(province_name),
                        "district_key": "",
                        "ward_key": normalize_key(ward.get("ward_name", "")),
                    }
                )

                for old in ward.get("merged_from") or []:
                    records.append(
                        {
                            **base,
                            "source": "old",
                            "old_province_name": old.get("old_province_name"),
                            "old_district_name": old.get("old_district_name"),
                            "old_ward_name": old.get("old_ward_name"),
                            "province_key": normalize_key(
                                old.get("old_province_name") or province_name
                            ),
                            "district_key": normalize_key(
                                old.get("old_district_name") or ""
                            ),
                            "ward_key": normalize_key(
                                old.get("old_ward_name") or ward.get("ward_name") or ""
                            ),
                        }
                    )
        return records

    def normalize(self, address: ExtractedAddress) -> NormalizedAddress:
        warnings: list[str] = []
        if not address.ward:
            warnings.append("missing_ward")
            return NormalizedAddress(
                province=address.province,
                ward=address.ward,
                street=address.street,
                house_number=address.house_number,
                warnings=warnings,
            )

        province_key = normalize_key(address.province or "")
        district_key = normalize_key(address.district_hint or "")
        ward_key = normalize_key(address.ward or "")

        candidates = self._rank_candidates(province_key, district_key, ward_key)
        best = candidates[0] if candidates else None
        if not best:
            warnings.append("admin_normalization_not_found")
            return NormalizedAddress(
                province=address.province,
                ward=address.ward,
                street=address.street,
                house_number=address.house_number,
                warnings=warnings,
            )

        if best.score < self.fuzzy_threshold:
            warnings.append("low_admin_match_confidence")

        is_ambiguous = any(
            other.score >= best.score - 0.01
            and (
                other.province_name != best.province_name
                or other.ward_name != best.ward_name
            )
            for other in candidates[1:5]
        )
        if is_ambiguous:
            warnings.append("ambiguous_admin_match")

        if not address.house_number:
            warnings.append("missing_house_number")

        return NormalizedAddress(
            province=best.province_name,
            ward=best.ward_name,
            street=address.street,
            house_number=address.house_number,
            is_normalized=best.score >= self.fuzzy_threshold and not is_ambiguous,
            confidence=round(best.score / 100, 4),
            matched_by=best.matched_by,
            candidates=candidates[:5],
            warnings=warnings,
        )

    def _rank_candidates(
        self, province_key: str, district_key: str, ward_key: str
    ) -> list[NormalizationCandidate]:
        scored: list[NormalizationCandidate] = []
        for rec in self.records:
            province_score = self._score(province_key, rec["province_key"])
            if province_key and province_score < 78:
                continue

            district_score = self._score(district_key, rec["district_key"])
            if district_key and rec["district_key"] and district_score < 72:
                continue

            ward_score = self._score(ward_key, rec["ward_key"])
            if ward_score < 72:
                continue

            score = self._combined_score(
                province_score=province_score,
                district_score=district_score,
                ward_score=ward_score,
                has_province=bool(province_key),
                has_district=bool(district_key),
            )
            matched_by = "new_address" if rec["source"] == "new" else "old_address_mapping"
            scored.append(
                NormalizationCandidate(
                    province_name=rec["province_name"],
                    ward_name=rec["ward_name"],
                    province_code=rec["province_code"],
                    ward_code=rec["ward_code"],
                    score=round(score, 2),
                    matched_by=matched_by,
                    old_province_name=rec["old_province_name"],
                    old_district_name=rec["old_district_name"],
                    old_ward_name=rec["old_ward_name"],
                )
            )

        scored.sort(
            key=lambda c: (
                c.score,
                c.old_district_name is not None,
                c.matched_by == "new_address",
            ),
            reverse=True,
        )
        return scored

    def _score(self, query: str, candidate: str) -> float:
        if not query:
            return 100.0
        if not candidate:
            return 0.0
        if query == candidate:
            return 100.0
        return max(
            fuzz.ratio(query, candidate),
            fuzz.token_sort_ratio(query, candidate),
        )

    def _combined_score(
        self,
        province_score: float,
        district_score: float,
        ward_score: float,
        has_province: bool,
        has_district: bool,
    ) -> float:
        if has_province and has_district:
            return province_score * 0.42 + district_score * 0.28 + ward_score * 0.30
        if has_province:
            return province_score * 0.55 + ward_score * 0.45
        if has_district:
            return district_score * 0.38 + ward_score * 0.62
        return ward_score
