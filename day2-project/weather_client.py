"""Client and normalization helpers for the National Weather Service API.

The NWS API is intentionally kept behind this module.  The rest of the
application works with ``WeatherDocument`` records and does not need to know
whether a document came from an alert or a forecast period.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import urljoin

import requests


NWS_BASE_URL = "https://api.weather.gov"
GEOCODER_URL = "https://nominatim.openstreetmap.org/search"
COORDINATE_PATTERN = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$"
)


class WeatherClientError(RuntimeError):
    """Raised when a location cannot be resolved or NWS cannot be reached."""


@dataclass(frozen=True)
class WeatherLocation:
    """A location resolved to coordinates used by NWS ``/points``."""

    label: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class WeatherDocument:
    """Normalized unstructured weather content ready for Lakebase."""

    id: str
    location: str
    source_type: str
    headline: str
    narrative_text: str
    issued_at: datetime | None
    effective_at: datetime | None
    payload: dict[str, Any]
    synced_at: datetime

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _stable_hash(*parts: Any) -> str:
    value = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_text(*parts: Any) -> str:
    return "\n\n".join(str(part).strip() for part in parts if part and str(part).strip())


class WeatherClient:
    """Fetch NWS alerts and narrative forecasts for user-supplied locations.

    A location may be supplied as a ``"City, ST"`` string, a two-item
    ``[latitude, longitude]``/tuple, or a mapping containing ``lat`` and
    ``lon`` (with an optional ``label``).  City/state strings are resolved by
    Nominatim; weather content itself always comes from NWS.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        timeout: float | tuple[float, float] = (8.0, 30.0),
        user_agent: str | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.session.headers.update(
            {
                "Accept": "application/geo+json, application/json",
                # NWS requires an identifying User-Agent header.
                "User-Agent": user_agent
                or os.getenv("NWS_USER_AGENT")
                or "databricks-weather-intelligence-homework (contact@example.com)",
            }
        )

    def _get_json(
        self,
        url_or_path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        url = url_or_path
        if not url.startswith(("http://", "https://")):
            url = urljoin(NWS_BASE_URL, url)
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise WeatherClientError(f"Weather API request failed: {url}") from exc
        return payload

    @staticmethod
    def _validate_coordinates(latitude: Any, longitude: Any) -> tuple[float, float]:
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError) as exc:
            raise WeatherClientError("Latitude and longitude must be numbers") from exc
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise WeatherClientError("Latitude or longitude is outside its valid range")
        return lat, lon

    def _geocode_city_state(self, value: str) -> WeatherLocation:
        payload = self._get_json(
            GEOCODER_URL,
            params={
                "q": f"{value}, USA",
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "us",
            },
        )
        if not isinstance(payload, list) or not payload:
            raise WeatherClientError(f"Could not geocode location: {value}")
        first = payload[0]
        latitude, longitude = self._validate_coordinates(
            first.get("lat"), first.get("lon")
        )
        return WeatherLocation(
            label=value,
            latitude=latitude,
            longitude=longitude,
        )

    def resolve_location(self, value: Any) -> WeatherLocation:
        """Resolve a request location to a label and valid coordinates."""

        if isinstance(value, Mapping):
            latitude = value.get("lat", value.get("latitude"))
            longitude = value.get("lon", value.get("lng", value.get("longitude")))
            if latitude is None or longitude is None:
                raise WeatherClientError(
                    "Location objects must contain lat/lon or latitude/longitude"
                )
            lat, lon = self._validate_coordinates(latitude, longitude)
            label = str(value.get("label") or value.get("location") or f"{lat},{lon}")
            return WeatherLocation(label=label, latitude=lat, longitude=lon)

        if isinstance(value, (list, tuple)) and len(value) == 2:
            lat, lon = self._validate_coordinates(value[0], value[1])
            return WeatherLocation(label=f"{lat},{lon}", latitude=lat, longitude=lon)

        if not isinstance(value, str) or not value.strip():
            raise WeatherClientError("Each location must be a city/state string or coordinates")

        text = value.strip()
        coordinate_match = COORDINATE_PATTERN.fullmatch(text)
        if coordinate_match:
            lat, lon = self._validate_coordinates(
                coordinate_match.group(1), coordinate_match.group(2)
            )
            return WeatherLocation(label=text, latitude=lat, longitude=lon)
        return self._geocode_city_state(text)

    def fetch_location_documents(self, location: WeatherLocation) -> list[WeatherDocument]:
        """Fetch alerts and 12-hour forecast periods for one location."""

        point_value = f"{location.latitude:.6f},{location.longitude:.6f}"
        point_payload = self._get_json(f"/points/{point_value}")
        point_properties = point_payload.get("properties", {})
        forecast_url = point_properties.get("forecast")
        if not forecast_url:
            raise WeatherClientError(f"NWS did not return a forecast URL for {location.label}")

        synced_at = _utc_now()
        documents: list[WeatherDocument] = []

        alerts_payload = self._get_json("/alerts/active", params={"point": point_value})
        for feature in alerts_payload.get("features", []):
            if not isinstance(feature, Mapping):
                continue
            properties = feature.get("properties", {})
            if not isinstance(properties, Mapping):
                continue
            alert_id = str(feature.get("id") or properties.get("id") or "")
            if not alert_id:
                alert_id = _stable_hash(
                    "alert",
                    location.latitude,
                    location.longitude,
                    properties.get("sent"),
                    properties.get("event"),
                )
            narrative = _clean_text(
                properties.get("headline"),
                properties.get("description"),
                properties.get("instruction"),
            )
            if not narrative:
                continue
            documents.append(
                WeatherDocument(
                    id=f"nws-alert:{alert_id}",
                    location=location.label,
                    source_type="alert",
                    headline=str(
                        properties.get("event")
                        or properties.get("headline")
                        or "Weather alert"
                    ),
                    narrative_text=narrative,
                    issued_at=_parse_timestamp(properties.get("sent")),
                    effective_at=_parse_timestamp(
                        properties.get("effective") or properties.get("onset")
                    ),
                    payload=dict(feature),
                    synced_at=synced_at,
                )
            )

        forecast_payload = self._get_json(str(forecast_url))
        forecast_properties = forecast_payload.get("properties", {})
        for period in forecast_properties.get("periods", []):
            if not isinstance(period, Mapping):
                continue
            detailed_forecast = str(period.get("detailedForecast") or "").strip()
            if not detailed_forecast:
                continue
            valid_time = period.get("startTime") or period.get("validTime")
            period_name = str(period.get("name") or "Forecast")
            documents.append(
                WeatherDocument(
                    id="nws-forecast:"
                    + _stable_hash(
                        "forecast",
                        f"{location.latitude:.6f},{location.longitude:.6f}",
                        valid_time,
                        period_name,
                    ),
                    location=location.label,
                    source_type="forecast",
                    headline=period_name,
                    narrative_text=detailed_forecast,
                    issued_at=None,
                    effective_at=_parse_timestamp(valid_time),
                    payload=dict(period),
                    synced_at=synced_at,
                )
            )

        return documents

    def harvest(
        self,
        locations: Iterable[Any],
        *,
        limit: int = 50,
    ) -> list[WeatherDocument]:
        """Harvest at most ``limit`` unique documents across all locations."""

        if limit < 1:
            return []
        by_id: dict[str, WeatherDocument] = {}
        for raw_location in locations:
            location = self.resolve_location(raw_location)
            for document in self.fetch_location_documents(location):
                by_id.setdefault(document.id, document)
                if len(by_id) >= limit:
                    return list(by_id.values())
        return list(by_id.values())
