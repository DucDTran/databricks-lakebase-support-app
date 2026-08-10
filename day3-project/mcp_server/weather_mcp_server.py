"""Weather prediction MCP server for Databricks Agent Bricks.

The server exposes weather tools over FastMCP's HTTP transport.  FastMCP's
``transport="http"`` is the Streamable HTTP transport used by current MCP
clients and Databricks Apps.  The decorated functions stay intentionally
thin: all API calls, parsing, and recommendation logic live in
``weather_adapter.py``.

Run locally from this directory with:

    python weather_mcp_server.py

The MCP endpoint is served at ``http://localhost:8000/mcp`` by FastMCP.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any, TypeVar

from fastmcp import FastMCP

from weather_adapter import WeatherAdapter, WeatherAdapterError


logger = logging.getLogger("weather-mcp-server")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

mcp = FastMCP("weather-forecast-agent")
adapter = WeatherAdapter()
T = TypeVar("T")


def _safe_call(function: Callable[..., T], *args: Any, **kwargs: Any) -> T | dict[str, Any]:
    """Convert expected upstream failures into agent-readable tool results."""

    try:
        return function(*args, **kwargs)
    except WeatherAdapterError as exc:
        return {"status": "error", "error": str(exc)}
    except Exception:
        logger.exception("Unhandled weather tool failure")
        return {
            "status": "error",
            "error": "The weather service is temporarily unavailable. Please try again.",
        }


@mcp.tool
def get_runtime_date() -> dict[str, Any]:
    """Get the runtime date and timezone used for relative-date questions.

    Args:
        None.

    Returns:
        A JSON object containing the exact runtime date, configured IANA
        timezone, and source label. Use this before converting words such as
        "today" or "tomorrow" into an ISO date.
    """

    return _safe_call(adapter.get_runtime_date)  # type: ignore[return-value]


@mcp.tool
def get_current_weather(location: str) -> dict[str, Any]:
    """Get current temperature, conditions, humidity, and wind.

    Args:
        location: City and country/state such as "Chicago, IL" or coordinates
            such as "41.88,-87.63".

    Returns:
        A normalized JSON object with current conditions, location metadata,
        and the Open-Meteo source.  On failure, returns status="error" and a
        user-readable error message.
    """

    return _safe_call(adapter.get_current_weather, location)  # type: ignore[return-value]


@mcp.tool
def get_forecast(location: str, days: int = 5) -> dict[str, Any]:
    """Get a multi-day forecast with temperature and precipitation signals.

    Args:
        location: City and country/state or latitude,longitude coordinates.
        days: Number of forecast days from 1 through 16. Defaults to 5.

    Returns:
        A normalized JSON object containing daily high/low temperatures,
        conditions, precipitation probabilities, precipitation amounts, and
        wind.  On failure, returns status="error" instead of a stack trace.
    """

    return _safe_call(adapter.get_forecast, location, days)  # type: ignore[return-value]


@mcp.tool
def predict_umbrella_needed(location: str, date: str | None = None) -> dict[str, Any]:
    """Decide whether a person should bring an umbrella using forecast logic.

    Args:
        location: City and country/state or latitude,longitude coordinates.
        date: Optional ISO date in YYYY-MM-DD format. Defaults to tomorrow.

    Returns:
        A recommendation, the selected forecast day, the rule inputs, and an
        explanation. The rule recommends an umbrella when precipitation
        probability is at least 40%, precipitation is at least 0.3 mm, or the
        weather code indicates rain, snow, or a thunderstorm.
    """

    return _safe_call(adapter.predict_umbrella_needed, location, date)  # type: ignore[return-value]


@mcp.tool
def get_travel_recommendation(location: str, date: str | None = None) -> dict[str, Any]:
    """Recommend clothing and rain gear for a date using the forecast.

    Args:
        location: City and country/state or latitude,longitude coordinates.
        date: Optional ISO date in YYYY-MM-DD format. Defaults to tomorrow.

    Returns:
        A short packing recommendation and the forecast-based reasoning.
        Returns status="error" when the location or date cannot be resolved.
    """

    return _safe_call(adapter.get_travel_recommendation, location, date)  # type: ignore[return-value]


@mcp.tool
def get_severe_weather_alerts(location: str) -> dict[str, Any]:
    """Get active U.S. National Weather Service alerts for a location.

    Args:
        location: City and state/country or latitude,longitude coordinates.

    Returns:
        Active alerts when the location is covered by NWS. For non-U.S.
        locations, returns status="unsupported" with an explanation rather
        than pretending that no alerts exist.
    """

    return _safe_call(adapter.get_severe_weather_alerts, location)  # type: ignore[return-value]


@mcp.tool
def get_historical_weather(location: str, date: str) -> dict[str, Any]:
    """Look up a past day's normalized weather from Open-Meteo reanalysis.

    Args:
        location: City and country/state or latitude,longitude coordinates.
        date: Past ISO date in YYYY-MM-DD format. Today and future dates are
            rejected because they are not historical observations.

    Returns:
        Daily historical temperature, precipitation, wind, and condition data.
    """

    return _safe_call(adapter.get_historical_weather, location, date)  # type: ignore[return-value]


@mcp.tool
def compare_weather(locations: list[str], date: str | None = None) -> dict[str, Any]:
    """Compare forecast conditions across two to five locations.

    Args:
        locations: Two to five city/state or city/country strings.
        date: Optional ISO forecast date. Defaults to tomorrow.

    Returns:
        Per-location temperature, rain probability, wind, and conditions, plus
        the driest and warmest locations for quick planning.
    """

    return _safe_call(adapter.compare_weather, locations, date)  # type: ignore[return-value]


if __name__ == "__main__":
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))
    mcp.run(transport="http", host="0.0.0.0", port=port)
