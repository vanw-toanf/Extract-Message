"""Async Goong.io geocoding client."""
from dataclasses import dataclass

import httpx

from app.core_config import Settings
from app.services.base_client import BaseHttpClient

GOONG_GEOCODE_URL = "https://rsapi.goong.io/geocode"

_ADMIN_ONLY_TYPES = frozenset({
    "country",
    "province",
    "district",
    "locality",
    "administrative_area_level_1",
    "administrative_area_level_2",
    "administrative_area_level_3",
})


class GoongGeocodeFailed(RuntimeError):
    """Raised when Goong returns no result, errors out, or precision is too low."""


@dataclass
class GeocodeResult:
    lat: float
    lng: float
    compound_province: str | None = None
    compound_district: str | None = None
    compound_commune: str | None = None


class GoongClient(BaseHttpClient):
    _RETRYABLE = (
        httpx.TimeoutException,   # connect/read/write timeout
        httpx.ConnectError,       # TCP connection failed
        httpx.RemoteProtocolError,
    )

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._api_key = settings.goong_api
        self._http = httpx.AsyncClient(timeout=settings.goong_timeout_seconds)

    async def geocode(self, address: str) -> GeocodeResult:
        """Return GeocodeResult for the given address string (with retry + circuit breaker).

        Raises GoongGeocodeFailed when:
        - API errors or returns no results
        - Result is only district/province level centroid (non-empty admin-only types)
        Note: types=[] is allowed — common for Vietnamese alley/ngõ addresses.
        """
        return await self._protected_call(lambda: self._raw_geocode(address))

    async def _raw_geocode(self, address: str) -> GeocodeResult:
        try:
            resp = await self._http.get(
                GOONG_GEOCODE_URL,
                params={"address": address, "api_key": self._api_key},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except GoongGeocodeFailed:
            raise
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError):
            raise  # let BaseHttpClient retry these
        except Exception as exc:
            raise GoongGeocodeFailed(f"Goong API error: {exc}") from exc

        if not results:
            raise GoongGeocodeFailed(f"No geocode results for: {address!r}")

        best = results[0]
        types = set(best.get("types", []))
        if types and types.issubset(_ADMIN_ONLY_TYPES):
            raise GoongGeocodeFailed(
                f"Geocode precision too low (types={types}) for: {address!r}"
            )

        loc = best["geometry"]["location"]
        compound = best.get("compound", {})
        return GeocodeResult(
            lat=float(loc["lat"]),
            lng=float(loc["lng"]),
            compound_province=compound.get("province"),
            compound_district=compound.get("district"),
            compound_commune=compound.get("commune"),
        )

    async def aclose(self) -> None:
        await self._http.aclose()
