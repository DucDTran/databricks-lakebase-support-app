"""Small dashboard-local copy of the forecast adapter.

Databricks Apps deploy from independent subfolders. Keeping this read-only
adapter beside the dashboard makes that app deployable without a shared wheel.
The MCP server remains the source of truth for the full tool surface.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import requests


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WMO = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


class DashboardWeatherError(RuntimeError):
    """Raised when the dashboard cannot retrieve a readable forecast."""


class WeatherAdapter:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "databricks-weather-dashboard/1.0"}
        )

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.session.get(url, params=params, timeout=(8, 30))
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise DashboardWeatherError("The weather service timed out") from exc
        except requests.RequestException as exc:
            raise DashboardWeatherError("The weather service could not be reached") from exc
        except ValueError as exc:
            raise DashboardWeatherError("The weather service returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise DashboardWeatherError("The weather service returned an unexpected response")
        return payload

    def resolve(self, location: str) -> tuple[str, float, float]:
        if not location or not location.strip():
            raise DashboardWeatherError("Enter a city or latitude,longitude")
        text = location.strip()
        try:
            lat_text, lon_text = [part.strip() for part in text.split(",", 1)]
            latitude, longitude = float(lat_text), float(lon_text)
            if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                return text, latitude, longitude
        except (ValueError, TypeError):
            pass
        payload = self._get(GEOCODING_URL, {"name": text, "count": 1, "language": "en", "format": "json"})
        result = (payload.get("results") or [None])[0]
        if not isinstance(result, dict):
            raise DashboardWeatherError(f"Could not resolve {text!r}")
        label = ", ".join(str(part) for part in (result.get("name"), result.get("admin1"), result.get("country_code")) if part)
        return label or text, float(result["latitude"]), float(result["longitude"])

    def predict(self, location: str, requested_date: str | None = None) -> dict[str, Any]:
        label, latitude, longitude = self.resolve(location)
        target = date.fromisoformat(requested_date) if requested_date else date.today() + timedelta(days=1)
        span = max(1, (target - date.today()).days + 1)
        payload = self._get(
            FORECAST_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "timezone": "auto",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "forecast_days": min(16, span + 2),
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_gusts_10m_max",
            },
        )
        daily = payload.get("daily", {})
        dates = daily.get("time", [])
        if target.isoformat() not in dates:
            raise DashboardWeatherError("That date is outside the available forecast window")
        index = dates.index(target.isoformat())
        code = int(daily["weather_code"][index])
        rain_probability = int(daily["precipitation_probability_max"][index] or 0)
        precipitation = float(daily["precipitation_sum"][index] or 0)
        umbrella = rain_probability >= 40 or precipitation >= 0.3 or 51 <= code <= 99
        return {
            "location": label,
            "date": target.isoformat(),
            "conditions": WMO.get(code, "Unknown conditions"),
            "temperature_high_f": daily["temperature_2m_max"][index],
            "temperature_low_f": daily["temperature_2m_min"][index],
            "precipitation_probability_pct": rain_probability,
            "precipitation_mm": precipitation,
            "wind_gusts_mph": daily["wind_gusts_10m_max"][index],
            "bring_umbrella": umbrella,
            "recommendation": "Bring an umbrella" if umbrella else "An umbrella is optional",
            "rule": "Umbrella at 40% rain probability, 0.3 mm precipitation, or rain-coded conditions",
        }
