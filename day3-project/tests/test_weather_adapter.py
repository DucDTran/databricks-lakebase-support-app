from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "mcp_server"))

from weather_adapter import WeatherAdapter, WeatherAdapterError  # noqa: E402


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self, forecast_payload: dict) -> None:
        self.headers: dict[str, str] = {}
        self.forecast_payload = forecast_payload
        self.calls: list[str] = []

    def get(self, url: str, **_: object) -> FakeResponse:
        self.calls.append(url)
        if "geocoding-api" in url:
            return FakeResponse(
                {
                    "results": [
                        {
                            "name": "Chicago",
                            "admin1": "Illinois",
                            "country_code": "US",
                            "latitude": 41.8781,
                            "longitude": -87.6298,
                        }
                    ]
                }
            )
        if "archive-api" in url:
            return FakeResponse(
                {
                    "timezone": "America/Chicago",
                    "daily": {
                        "time": ["2026-08-07"],
                        "weather_code": [61],
                        "temperature_2m_max": [79],
                        "temperature_2m_min": [65],
                        "precipitation_sum": [4.2],
                        "rain_sum": [4.2],
                        "snowfall_sum": [0],
                        "wind_speed_10m_max": [12],
                    },
                }
            )
        if "api.weather.gov" in url:
            return FakeResponse({"features": []})
        return FakeResponse(self.forecast_payload)


class NwsOutsideUsSession(FakeSession):
    def get(self, url: str, **kwargs: object) -> FakeResponse:
        if "api.weather.gov" in url:
            return FakeResponse({}, status_code=404)
        return super().get(url, **kwargs)


class AmbiguousLocationSession(FakeSession):
    def get(self, url: str, **kwargs: object) -> FakeResponse:
        if "geocoding-api" in url:
            return FakeResponse(
                {
                    "results": [
                        {
                            "name": "Springfield",
                            "admin1": "Illinois",
                            "country_code": "US",
                            "latitude": 39.7817,
                            "longitude": -89.6501,
                        },
                        {
                            "name": "Springfield",
                            "admin1": "Missouri",
                            "country_code": "US",
                            "latitude": 37.2153,
                            "longitude": -93.2982,
                        },
                    ]
                }
            )
        return super().get(url, **kwargs)


def forecast_payload(*, rain_probability: int = 75) -> dict:
    return {
        "timezone": "America/Chicago",
        "current": {
            "time": "2026-08-10T10:00",
            "temperature_2m": 76,
            "relative_humidity_2m": 68,
            "apparent_temperature": 78,
            "weather_code": 2,
            "wind_speed_10m": 8,
            "wind_gusts_10m": 14,
        },
        "daily": {
            "time": ["2026-08-10", "2026-08-11"],
            "weather_code": [2, 63 if rain_probability >= 40 else 1],
            "temperature_2m_max": [82, 80],
            "temperature_2m_min": [66, 61],
            "apparent_temperature_max": [84, 81],
            "apparent_temperature_min": [65, 60],
            "precipitation_probability_max": [10, rain_probability],
            "precipitation_probability_mean": [4, rain_probability // 2],
            "precipitation_sum": [0.0, 1.2 if rain_probability >= 40 else 0.0],
            "rain_sum": [0.0, 1.2 if rain_probability >= 40 else 0.0],
            "snowfall_sum": [0.0, 0.0],
            "wind_speed_10m_max": [12, 15],
            "wind_gusts_10m_max": [18, 22],
            "sunrise": ["2026-08-10T05:50", "2026-08-11T05:51"],
            "sunset": ["2026-08-10T20:05", "2026-08-11T20:04"],
        },
    }


def test_resolve_city_and_normalize_current_conditions() -> None:
    session = FakeSession(forecast_payload())
    adapter = WeatherAdapter(session=session)

    current = adapter.get_current_weather("Chicago, IL")

    assert current["status"] == "success"
    assert current["location"] == "Chicago, Illinois, US"
    assert current["temperature_f"] == 76.0
    assert current["conditions"] == "Partly cloudy"
    assert "geocoding-api.open-meteo.com" in session.calls[0]


def test_umbrella_prediction_exposes_reasoning_and_applies_threshold() -> None:
    adapter = WeatherAdapter(session=FakeSession(forecast_payload(rain_probability=75)))

    prediction = adapter.predict_umbrella_needed("41.8781,-87.6298", "2026-08-11")

    assert prediction["bring_umbrella"] is True
    assert prediction["recommendation"] == "Bring an umbrella"
    assert "75%" in prediction["reasoning"]
    assert prediction["rule"].startswith("umbrella if probability >= 40%")


def test_historical_lookup_uses_archive_shape() -> None:
    adapter = WeatherAdapter(session=FakeSession(forecast_payload()))

    historical = adapter.get_historical_weather("41.8781,-87.6298", "2026-08-07")

    assert historical["status"] == "success"
    assert historical["weather"]["conditions"] == "Light rain"
    assert historical["weather"]["precipitation_sum_mm"] == 4.2


def test_invalid_historical_date_is_clean_error() -> None:
    adapter = WeatherAdapter(session=FakeSession(forecast_payload()))

    try:
        adapter.get_historical_weather("41.8781,-87.6298", "not-a-date")
    except WeatherAdapterError as exc:
        assert "ISO date" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected WeatherAdapterError")


def test_nws_alerts_disclose_non_us_coverage() -> None:
    adapter = WeatherAdapter(session=NwsOutsideUsSession(forecast_payload()))

    alerts = adapter.get_severe_weather_alerts("51.5072,-0.1276")

    assert alerts["status"] == "unsupported"
    assert alerts["alerts"] == []
    assert "U.S. locations only" in alerts["message"]


def test_ambiguous_location_is_a_clean_clarification_error() -> None:
    adapter = WeatherAdapter(session=AmbiguousLocationSession(forecast_payload()))

    try:
        adapter.resolve_location("Springfield")
    except WeatherAdapterError as exc:
        message = str(exc)
        assert "ambiguous" in message
        assert "Illinois" in message
        assert "Missouri" in message
    else:  # pragma: no cover
        raise AssertionError("Expected an ambiguity clarification error")


def test_compare_weather_echoes_one_selected_date_for_every_location() -> None:
    adapter = WeatherAdapter(session=FakeSession(forecast_payload()))

    comparison = adapter.compare_weather(
        ["Seattle, WA", "Denver, CO"],
        requested_date="2026-08-11",
    )

    assert comparison["date"] == "2026-08-11"
    assert {row["date"] for row in comparison["locations"]} == {"2026-08-11"}


def test_relative_date_uses_runtime_clock_and_discloses_timezone() -> None:
    adapter = WeatherAdapter(
        session=FakeSession(forecast_payload()),
        timezone_name="Asia/Ho_Chi_Minh",
        today_provider=lambda: date(2026, 8, 10),
    )

    runtime = adapter.get_runtime_date()
    prediction = adapter.predict_umbrella_needed("41.8781,-87.6298")

    assert runtime == {
        "status": "success",
        "today": "2026-08-10",
        "timezone": "Asia/Ho_Chi_Minh",
        "source": "Weather MCP runtime clock",
    }
    assert prediction["runtime_today"] == "2026-08-10"
    assert prediction["runtime_timezone"] == "Asia/Ho_Chi_Minh"
    assert prediction["date"] == "2026-08-11"


def test_evidence_relative_dates_and_final_answers_match_tool_results() -> None:
    evidence = (Path(__file__).parents[1] / "evidence" / "sample_runs.md").read_text()

    umbrella = evidence.split("## 2. Travel recommendation", 1)[0]
    umbrella_call = umbrella.split("**Tool call 2:**", 1)[1].split(
        "**Relevant tool result:**", 1
    )[0]
    assert '"date": "2026-08-11"' in umbrella_call
    assert '"date": "2026-08-10"' not in umbrella_call
    assert "2026-08-11" in umbrella

    comparison = evidence.split("## 3. City comparison", 1)[1].split(
        "## 4. Severe-alert coverage", 1
    )[0]
    assert '"date": "2026-08-11"' in comparison
    assert "For **2026-08-11**" in comparison
    assert "August 10" not in comparison
