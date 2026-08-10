"""Small read-only dashboard for recent weather-agent predictions."""

from __future__ import annotations

import os
from collections import deque
from typing import Any

from flask import Flask, jsonify, render_template, request

from weather_adapter import DashboardWeatherError, WeatherAdapter


app = Flask(__name__)
adapter = WeatherAdapter()
history: deque[dict[str, Any]] = deque(maxlen=12)


@app.get("/health")
def health() -> Any:
    return jsonify({"ok": True, "history_count": len(history)})


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/history")
def get_history() -> Any:
    return jsonify({"items": list(history)})


@app.post("/api/query")
def query_weather() -> Any:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    location = payload.get("location")
    if not isinstance(location, str) or not location.strip():
        return jsonify({"error": "location is required"}), 400
    requested_date = payload.get("date")
    if requested_date is not None and not isinstance(requested_date, str):
        return jsonify({"error": "date must be YYYY-MM-DD"}), 400
    try:
        prediction = adapter.predict(location, requested_date)
    except (DashboardWeatherError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 502
    entry = {
        "question": payload.get("question") or f"Weather recommendation for {prediction['location']}",
        "created_at": prediction["runtime_today"],
        **prediction,
    }
    history.appendleft(entry)
    return jsonify(entry)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("DATABRICKS_APP_PORT", "8001")))
