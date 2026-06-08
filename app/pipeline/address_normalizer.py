import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from app.pipeline.text_utils import normalize_key, normalize_text_key
from app.schemas.order import (
    ExtractedAddress,
    NormalizationCandidate,
    NormalizedAddress,
)

_HN_HCM_PROVINCE_KEYS: frozenset[str] = frozenset(
    {normalize_key("Hà Nội"), normalize_key("Hồ Chí Minh")}
)


class AddressNormalizer:
    def __init__(self, db_path: Path, fuzzy_threshold: int = 84):
        self.db_path = db_path
        self.fuzzy_threshold = fuzzy_threshold
        self.records = self._load_records(db_path)
        self._unique_municipality_map = self._build_unique_municipality_map()

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
                        "province_text_key": normalize_text_key(province_name),
                        "district_key": "",
                        "district_text_key": "",
                        "ward_key": normalize_key(ward.get("ward_name", "")),
                        "ward_text_key": normalize_text_key(ward.get("ward_name", "")),
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
                            "province_text_key": normalize_text_key(
                                old.get("old_province_name") or province_name
                            ),
                            "district_key": normalize_key(
                                old.get("old_district_name") or ""
                            ),
                            "district_text_key": normalize_text_key(
                                old.get("old_district_name") or ""
                            ),
                            "ward_key": normalize_key(
                                old.get("old_ward_name") or ward.get("ward_name") or ""
                            ),
                            "ward_text_key": normalize_text_key(
                                old.get("old_ward_name") or ward.get("ward_name") or ""
                            ),
                        }
                    )
        return records

    def _build_unique_municipality_map(self) -> dict[str, str]:
        """Build ward_key/district_key → province_name for names globally unique to HN or HCM.

        District keys and ward keys are tracked separately before merging so that a
        ward named "Bình Thạnh" appearing in many provinces cannot pollute the
        district-key entry for "Quận Bình Thạnh" which is unique to HCM.
        """
        # district_key tracking (separate from ward_key to avoid cross-contamination)
        dk_all: defaultdict[str, set[str]] = defaultdict(set)
        dk_name: dict[str, str] = {}
        # ward_key tracking
        wk_all: defaultdict[str, set[str]] = defaultdict(set)
        wk_name: dict[str, str] = {}

        for rec in self.records:
            pkey = rec["province_key"]
            is_hn_hcm = pkey in _HN_HCM_PROVINCE_KEYS

            dk = rec["district_key"]
            if dk:
                dk_all[dk].add(pkey)
                if is_hn_hcm:
                    dk_name.setdefault(dk, rec["province_name"])

            wk = rec["ward_key"]
            if wk:
                wk_all[wk].add(pkey)
                if is_hn_hcm:
                    wk_name.setdefault(wk, rec["province_name"])

        district_unique = {
            key: dk_name[key]
            for key, provinces in dk_all.items()
            if len(provinces) == 1 and key in dk_name
        }
        ward_unique = {
            key: wk_name[key]
            for key, provinces in wk_all.items()
            if len(provinces) == 1 and key in wk_name
        }
        # district keys take priority (more specific) when both match the same string
        return {**ward_unique, **district_unique}

    def infer_province_from_municipality(self, municipality: str) -> str | None:
        """Return 'Hà Nội' or 'Hồ Chí Minh' if municipality uniquely identifies one of them."""
        if not municipality:
            return None
        key = normalize_key(municipality)
        if key in self._unique_municipality_map:
            return self._unique_municipality_map[key]
        best_score, best_province = 0.0, None
        for known_key, province in self._unique_municipality_map.items():
            score = fuzz.ratio(key, known_key)
            if score > best_score:
                best_score, best_province = score, province
        return best_province if best_score >= 88 else None

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
        province_text_key = normalize_text_key(address.province or "")
        district_text_key = normalize_text_key(address.district_hint or "")
        ward_text_key = normalize_text_key(address.ward or "")

        candidates = self._rank_candidates(
            province_key,
            district_key,
            ward_key,
            province_text_key,
            district_text_key,
            ward_text_key,
        )
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
        self,
        province_key: str,
        district_key: str,
        ward_key: str,
        province_text_key: str,
        district_text_key: str,
        ward_text_key: str,
    ) -> list[NormalizationCandidate]:
        scored: list[tuple[NormalizationCandidate, float, int]] = []
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
            text_tie_score = self._combined_score(
                province_score=self._score(province_text_key, rec["province_text_key"]),
                district_score=self._score(district_text_key, rec["district_text_key"]),
                ward_score=self._score(ward_text_key, rec["ward_text_key"]),
                has_province=bool(province_text_key),
                has_district=bool(district_text_key),
            )
            exact_text_matches = int(province_text_key == rec["province_text_key"])
            if district_text_key:
                exact_text_matches += int(district_text_key == rec["district_text_key"])
            exact_text_matches += int(ward_text_key == rec["ward_text_key"])
            matched_by = "new_address" if rec["source"] == "new" else "old_address_mapping"
            candidate = NormalizationCandidate(
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
            scored.append((candidate, text_tie_score, exact_text_matches))

        scored.sort(
            key=lambda item: (
                item[0].score,
                item[2],
                item[1],
                item[0].old_district_name is not None,
                item[0].matched_by == "new_address",
            ),
            reverse=True,
        )
        return [candidate for candidate, _, _ in scored]

    def _score(self, query: str, candidate: str) -> float:
        if not query:
            return 100.0
        if not candidate:
            return 0.0
        if query == candidate:
            return 100.0
        r = fuzz.ratio(query, candidate)
        tsr = fuzz.token_sort_ratio(query, candidate)
        # Allow token-sort boost only when the base ratio already shows real similarity.
        # Without this guard, purely reversed two-token names like "binh thanh" vs
        # "thanh binh" score 100 via token_sort despite being different places.
        return tsr if r >= 60 else r

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
