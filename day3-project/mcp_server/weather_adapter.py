"""Open-Meteo and NWS adapter used by the weather MCP server.

The MCP layer deliberately knows nothing about HTTP, response shapes, WMO
weather codes, or location geocoding.  This module owns those concerns and
returns small, JSON-serializable dictionaries for the tools and dashboard.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from collections.abc import Callable
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests


OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
NWS_POINTS_URL = "https://api.weather.gov/points"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"
COORDINATE_PATTERN = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$"
)


class WeatherAdapterError(RuntimeError):
    """Raised for an invalid location, invalid date, or upstream API failure."""


@dataclass(frozen=True)
class WeatherLocation:
    """A human label and WGS84 coordinates resolved for an API request."""

    label: str
    latitude: float
    longitude: float


WMO_DESCRIPTIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Light freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with light hail",
    99: "Thunderstorm with heavy hail",
}
PRECIPITATION_CODES = set(range(51, 68)) | set(range(80, 83)) | set(range(95, 100))


def weather_code_description(code: Any) -> str:
    """Return a readable WMO weather description for a numeric code."""

    try:
        return WMO_DESCRIPTIONS.get(int(code), "Unknown conditions")
    except (TypeError, ValueError):
        return "Unknown conditions"


def _as_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _date_value(value: str, *, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise WeatherAdapterError(
            f"{field_name} must be an ISO date in YYYY-MM-DD format"
        ) from exc


class WeatherAdapter:
    """Resolve locations and normalize weather data from free public APIs.

    Open-Meteo is keyless and provides worldwide forecasts.  NWS alerts are
    used only for U.S. coordinates because the NWS alert endpoint is U.S.-only.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        timeout: float | tuple[float, float] = (8.0, 30.0),
        user_agent: str | None = None,
        timezone_name: str | None = None,
        today_provider: Callable[[], date] | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.timezone_name = timezone_name or os.getenv("WEATHER_TIMEZONE", "UTC")
        try:
            self.timezone = ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise WeatherAdapterError(
                f"Unknown WEATHER_TIMEZONE {self.timezone_name!r}; use an IANA timezone"
            ) from exc
        self._today_provider = today_provider
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": user_agent
                or os.getenv(
                    "WEATHER_USER_AGENT",
                    "databricks-weather-prediction-homework/1.0",
                ),
            }
        )

    def _today(self) -> date:
        """Return the runtime date in the configured agent timezone.

        A provider can be injected by tests so relative-date behavior is
        deterministic around midnight and daylight-saving transitions.
        """

        if self._today_provider is not None:
            return self._today_provider()
        return datetime.now(self.timezone).date()

    def get_runtime_date(self) -> dict[str, Any]:
        """Return the runtime date used to interpret relative date phrases."""

        return {
            "status": "success",
            "today": self._today().isoformat(),
            "timezone": self.timezone_name,
            "source": "Weather MCP runtime clock",
        }

    def _get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        try:
            response = self.session.get(
                url,
                params=params,
                headers=dict(headers or {}),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.Timeout as exc:
            raise WeatherAdapterError("The weather service timed out") from exc
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            raise WeatherAdapterError(
                f"The weather service returned HTTP {status_code}"
            ) from exc
        except requests.RequestException as exc:
            raise WeatherAdapterError("The weather service could not be reached") from exc
        except ValueError as exc:
            raise WeatherAdapterError("The weather service returned invalid JSON") from exc

    @staticmethod
    def _validate_coordinates(latitude: Any, longitude: Any) -> tuple[float, float]:
        lat = _as_float(latitude)
        lon = _as_float(longitude)
        if lat is None or lon is None:
            raise WeatherAdapterError("Latitude and longitude must be numbers")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise WeatherAdapterError("Latitude or longitude is outside its valid range")
        return lat, lon

    def resolve_location(self, value: str | Sequence[float] | Mapping[str, Any]) -> WeatherLocation:
        """Resolve a city, postal-style place string, or coordinate pair."""

        if isinstance(value, Mapping):
            latitude = value.get("lat", value.get("latitude"))
            longitude = value.get("lon", value.get("lng", value.get("longitude")))
            if latitude is None or longitude is None:
                raise WeatherAdapterError(
                    "Location objects must contain lat/lon or latitude/longitude"
                )
            lat, lon = self._validate_coordinates(latitude, longitude)
            label = str(value.get("label") or value.get("location") or f"{lat},{lon}")
            return WeatherLocation(label, lat, lon)

        if isinstance(value, (list, tuple)) and len(value) == 2:
            lat, lon = self._validate_coordinates(value[0], value[1])
            return WeatherLocation(f"{lat},{lon}", lat, lon)

        if not isinstance(value, str) or not value.strip():
            raise WeatherAdapterError(
                "Location must be a city, postal-style place, or 'latitude,longitude'"
            )

        text = value.strip()
        coordinate_match = COORDINATE_PATTERN.fullmatch(text)
        if coordinate_match:
            lat, lon = self._validate_coordinates(
                coordinate_match.group(1), coordinate_match.group(2)
            )
            return WeatherLocation(text, lat, lon)

        payload = self._get_json(
            OPEN_METEO_GEOCODING_URL,
            params={"name": text, "count": 5, "language": "en", "format": "json"},
        )
        results = payload.get("results", []) if isinstance(payload, Mapping) else []
        if not results or not isinstance(results[0], Mapping):
            raise WeatherAdapterError(
                f"Could not resolve {text!r}. Try 'City, Country' or coordinates."
            )
        if len(results) > 1:
            choices = []
            for result in results[:3]:
                if not isinstance(result, Mapping):
                    continue
                choice_parts = [result.get("name"), result.get("admin1"), result.get("country_code")]
                choice = ", ".join(str(part) for part in choice_parts if part)
                if choice:
                    choices.append(choice)
            suffix = f" Matches include: {'; '.join(choices)}." if choices else ""
            raise WeatherAdapterError(
                f"Location {text!r} is ambiguous. Add a state or country, or use coordinates.{suffix}"
            )
        first = results[0]
        lat, lon = self._validate_coordinates(first.get("latitude"), first.get("longitude"))
        label_parts = [first.get("name"), first.get("admin1"), first.get("country_code")]
        label = ", ".join(str(part) for part in label_parts if part)
        return WeatherLocation(label or text, lat, lon)

    def _forecast_payload(self, location: WeatherLocation, *, days: int) -> dict[str, Any]:
        return self._get_json(
            OPEN_METEO_FORECAST_URL,
            params={
                "latitude": location.latitude,
                "longitude": location.longitude,
                "timezone": "auto",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "forecast_days": days,
                "current": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "weather_code,wind_speed_10m,wind_gusts_10m"
                ),
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "apparent_temperature_max,apparent_temperature_min,"
                    "precipitation_probability_max,precipitation_probability_mean,"
                    "precipitation_sum,rain_sum,snowfall_sum,wind_speed_10m_max,"
                    "wind_gusts_10m_max,sunrise,sunset"
                ),
            },
        )

    @staticmethod
    def _daily_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        daily = payload.get("daily", {})
        if not isinstance(daily, Mapping):
            raise WeatherAdapterError("The weather service returned no daily forecast")
        dates = daily.get("time", [])
        if not isinstance(dates, list) or not dates:
            raise WeatherAdapterError("The weather service returned an empty forecast")

        def at(name: str, index: int, default: Any = None) -> Any:
            values = daily.get(name, [])
            return values[index] if isinstance(values, list) and index < len(values) else default

        records: list[dict[str, Any]] = []
        for index, day_value in enumerate(dates):
            code = _as_int(at("weather_code", index))
            records.append(
                {
                    "date": str(day_value),
                    "conditions": weather_code_description(code),
                    "weather_code": code,
                    "temperature_high_f": _as_float(at("temperature_2m_max", index)),
                    "temperature_low_f": _as_float(at("temperature_2m_min", index)),
                    "feels_like_high_f": _as_float(at("apparent_temperature_max", index)),
                    "feels_like_low_f": _as_float(at("apparent_temperature_min", index)),
                    "precipitation_probability_max_pct": _as_int(
                        at("precipitation_probability_max", index)
                    ),
                    "precipitation_probability_mean_pct": _as_int(
                        at("precipitation_probability_mean", index)
                    ),
                    "precipitation_sum_mm": _as_float(at("precipitation_sum", index)),
                    "rain_sum_mm": _as_float(at("rain_sum", index)),
                    "snowfall_sum_cm": _as_float(at("snowfall_sum", index)),
                    "wind_speed_max_mph": _as_float(at("wind_speed_10m_max", index)),
                    "wind_gusts_max_mph": _as_float(at("wind_gusts_10m_max", index)),
                    "sunrise": at("sunrise", index),
                    "sunset": at("sunset", index),
                }
            )
        return records

    def get_current_weather(self, location: str) -> dict[str, Any]:
        """Return normalized current conditions for a location."""

        resolved = self.resolve_location(location)
        payload = self._forecast_payload(resolved, days=1)
        current = payload.get("current", {})
        if not isinstance(current, Mapping):
            raise WeatherAdapterError("The weather service returned no current conditions")
        code = _as_int(current.get("weather_code"))
        return {
            "status": "success",
            "location": resolved.label,
            "coordinates": {"latitude": resolved.latitude, "longitude": resolved.longitude},
            "timezone": payload.get("timezone"),
            "observed_at": current.get("time"),
            "temperature_f": _as_float(current.get("temperature_2m")),
            "feels_like_f": _as_float(current.get("apparent_temperature")),
            "conditions": weather_code_description(code),
            "weather_code": code,
            "humidity_pct": _as_int(current.get("relative_humidity_2m")),
            "wind_speed_mph": _as_float(current.get("wind_speed_10m")),
            "wind_gusts_mph": _as_float(current.get("wind_gusts_10m")),
            "source": "Open-Meteo",
        }

    def get_forecast(self, location: str, days: int = 5) -> dict[str, Any]:
        """Return a normalized multi-day forecast with precipitation signals."""

        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 16:
            raise WeatherAdapterError("days must be an integer between 1 and 16")
        resolved = self.resolve_location(location)
        payload = self._forecast_payload(resolved, days=days)
        return {
            "status": "success",
            "location": resolved.label,
            "coordinates": {"latitude": resolved.latitude, "longitude": resolved.longitude},
            "timezone": payload.get("timezone"),
            "days": self._daily_records(payload),
            "source": "Open-Meteo",
        }

    @staticmethod
    def _find_day(records: Sequence[Mapping[str, Any]], requested_date: date) -> Mapping[str, Any]:
        requested = requested_date.isoformat()
        for record in records:
            if record.get("date") == requested:
                return record
        raise WeatherAdapterError(
            f"The requested date {requested} is outside the available forecast window"
        )

    def predict_umbrella_needed(self, location: str, requested_date: str | None = None) -> dict[str, Any]:
        """Apply a transparent umbrella rule to the daily forecast.

        The recommendation is ``bring_umbrella`` when maximum precipitation
        probability is at least 40%, daily precipitation is at least 0.3 mm,
        or the WMO code signals rain, snow, or thunderstorms.  The tool
        returns the inputs and reasoning so an agent can explain the judgment.
        """

        runtime_today = self._today()
        target = (
            _date_value(requested_date, field_name="date")
            if requested_date
            else runtime_today + timedelta(days=1)
        )
        if target < runtime_today:
            raise WeatherAdapterError("Prediction date must be today or later")
        span = max(1, (target - runtime_today).days + 1)
        # Open-Meteo starts daily data at the location's local date. Adding a
        # small cushion prevents a date near midnight in another time zone from
        # being rejected even though it is within the requested forecast window.
        forecast = self.get_forecast(location, days=min(16, span + 2))
        day = self._find_day(forecast["days"], target)
        probability = _as_int(day.get("precipitation_probability_max_pct"), 0) or 0
        precipitation = _as_float(day.get("precipitation_sum_mm"), 0.0) or 0.0
        weather_code = _as_int(day.get("weather_code"))
        code_signal = weather_code in PRECIPITATION_CODES
        bring_umbrella = probability >= 40 or precipitation >= 0.3 or code_signal
        reasons: list[str] = []
        if probability >= 40:
            reasons.append(f"precipitation probability is {probability}%")
        if precipitation >= 0.3:
            reasons.append(f"forecast precipitation is {precipitation:.1f} mm")
        if code_signal:
            reasons.append(f"conditions are {day['conditions'].lower()}")
        if not reasons:
            reasons.append("the forecast stays below the precipitation thresholds")
        return {
            "status": "success",
            "location": forecast["location"],
            "date": day["date"],
            "recommendation": "Bring an umbrella" if bring_umbrella else "An umbrella is optional",
            "bring_umbrella": bring_umbrella,
            "reasoning": "; ".join(reasons) + ".",
            "forecast": dict(day),
            "rule": "umbrella if probability >= 40%, precipitation >= 0.3 mm, or precipitation-coded conditions",
            "source": forecast["source"],
            "runtime_today": runtime_today.isoformat(),
            "runtime_timezone": self.timezone_name,
        }

    def get_travel_recommendation(self, location: str, requested_date: str | None = None) -> dict[str, Any]:
        """Recommend clothing and rain gear using one daily forecast."""

        umbrella = self.predict_umbrella_needed(location, requested_date)
        day = umbrella["forecast"]
        low = _as_float(day.get("temperature_low_f"))
        wind = _as_float(day.get("wind_gusts_max_mph"), 0.0) or 0.0
        bring_jacket = (low is not None and low < 60) or wind >= 25
        items = []
        if bring_jacket:
            items.append("a light jacket")
        if umbrella["bring_umbrella"]:
            items.append("an umbrella")
        if not items:
            items.append("light layers")
        return {
            "status": "success",
            "location": umbrella["location"],
            "date": umbrella["date"],
            "recommendation": "Pack " + " and ".join(items) + ".",
            "reasoning": (
                f"Low temperature is {low:.0f} F and maximum gusts are {wind:.0f} mph. "
                if low is not None
                else f"Maximum gusts are {wind:.0f} mph. "
            )
            + umbrella["reasoning"].capitalize(),
            "forecast": day,
            "source": umbrella["source"],
        }

    def get_severe_weather_alerts(self, location: str) -> dict[str, Any]:
        """Return active NWS alerts for a U.S. location, or explain coverage."""

        resolved = self.resolve_location(location)
        point = f"{resolved.latitude:.4f},{resolved.longitude:.4f}"
        try:
            self._get_json(
                f"{NWS_POINTS_URL}/{point}",
                headers={"Accept": "application/geo+json, application/json"},
            )
            payload = self._get_json(
                NWS_ALERTS_URL,
                params={"point": point},
                headers={"Accept": "application/geo+json, application/json"},
            )
        except WeatherAdapterError as exc:
            if "HTTP 404" in str(exc):
                return {
                    "status": "unsupported",
                    "location": resolved.label,
                    "alerts": [],
                    "message": "NWS alerts are available for U.S. locations only.",
                    "source": "National Weather Service",
                }
            raise

        features = payload.get("features", []) if isinstance(payload, Mapping) else []
        alerts = []
        for feature in features:
            properties = feature.get("properties", {}) if isinstance(feature, Mapping) else {}
            if not isinstance(properties, Mapping):
                continue
            alerts.append(
                {
                    "event": properties.get("event"),
                    "headline": properties.get("headline"),
                    "severity": properties.get("severity"),
                    "urgency": properties.get("urgency"),
                    "certainty": properties.get("certainty"),
                    "effective": properties.get("effective"),
                    "expires": properties.get("expires"),
                    "instruction": properties.get("instruction"),
                }
            )
        return {
            "status": "success",
            "location": resolved.label,
            "alert_count": len(alerts),
            "alerts": alerts,
            "source": "National Weather Service",
        }

    def get_historical_weather(self, location: str, requested_date: str) -> dict[str, Any]:
        """Return daily historical weather from Open-Meteo's archive API."""

        target = _date_value(requested_date, field_name="date")
        if target >= self._today():
            raise WeatherAdapterError("Historical date must be before today")
        resolved = self.resolve_location(location)
        payload = self._get_json(
            OPEN_METEO_ARCHIVE_URL,
            params={
                "latitude": resolved.latitude,
                "longitude": resolved.longitude,
                "start_date": target.isoformat(),
                "end_date": target.isoformat(),
                "timezone": "auto",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_sum,rain_sum,snowfall_sum,wind_speed_10m_max"
                ),
            },
        )
        records = self._daily_records(payload)
        return {
            "status": "success",
            "location": resolved.label,
            "date": target.isoformat(),
            "weather": records[0] if records else None,
            "source": "Open-Meteo Historical Weather API",
        }

    def compare_weather(self, locations: Sequence[str], requested_date: str | None = None) -> dict[str, Any]:
        """Compare rain, temperature, wind, and conditions across locations."""

        if not isinstance(locations, Sequence) or isinstance(locations, (str, bytes)):
            raise WeatherAdapterError("locations must be a list of at least two places")
        if not 2 <= len(locations) <= 5:
            raise WeatherAdapterError("Compare between 2 and 5 locations")
        runtime_today = self._today()
        target = (
            _date_value(requested_date, field_name="date")
            if requested_date
            else runtime_today + timedelta(days=1)
        )
        if target < runtime_today:
            raise WeatherAdapterError("Comparison date must be today or later")
        span = max(1, (target - runtime_today).days + 1)
        rows = []
        for location in locations:
            forecast = self.get_forecast(str(location), days=min(16, span + 2))
            day = self._find_day(forecast["days"], target)
            rows.append(
                {
                    "location": forecast["location"],
                    "date": day["date"],
                    "conditions": day["conditions"],
                    "temperature_high_f": day["temperature_high_f"],
                    "temperature_low_f": day["temperature_low_f"],
                    "precipitation_probability_max_pct": day[
                        "precipitation_probability_max_pct"
                    ],
                    "wind_gusts_max_mph": day["wind_gusts_max_mph"],
                }
            )
        driest = min(rows, key=lambda row: row["precipitation_probability_max_pct"] or 0)
        warmest = max(rows, key=lambda row: row["temperature_high_f"] or float("-inf"))
        return {
            "status": "success",
            "date": target.isoformat(),
            "locations": rows,
            "best_for_outdoor_plans": driest["location"],
            "warmest_location": warmest["location"],
            "source": "Open-Meteo",
            "runtime_today": runtime_today.isoformat(),
            "runtime_timezone": self.timezone_name,
        }
