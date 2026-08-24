"""Helpers for fetching and normalizing Open-Meteo weather data."""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import holidays
import requests
from bs4 import BeautifulSoup

_SAINTS_URL = "https://svetniki.info/"

_WEATHER_CODE_MAP = {
    0: "Sončno",
    1: "Pretežno sončno",
    2: "Delno oblačno",
    3: "Oblačno",
    45: "Megla",
    48: "Zmrznjena megla",
    51: "Rahel dež",
    53: "Dež",
    55: "Močan dež",
    56: "Mrzle kapljice",
    57: "Močne mrzle kapljice",
    61: "Nežen dež",
    63: "Dež",
    65: "Močan dež",
    66: "Mrzle kapljice",
    67: "Močne mrzle kapljice",
    71: "Sneg",
    73: "Močan sneg",
    75: "Sneg",
    77: "Snežne kroglice",
    80: "Plohe",
    81: "Plohe",
    82: "Močne plohe",
    85: "Snegove plohe",
    86: "Močne snežne plohe",
    90: "Nevihta",
    95: "Nevihta",
    96: "Nevihta z točo",
    99: "Močna nevihta z točo",
}

_WEATHER_ICON_MAP = {
    0: "bi-sun",
    1: "bi-sun",
    2: "bi-cloud-sun",
    3: "bi-clouds",
    45: "bi-cloud-fog2",
    48: "bi-cloud-fog2",
    51: "bi-cloud-drizzle",
    53: "bi-cloud-drizzle",
    55: "bi-cloud-drizzle",
    56: "bi-cloud-sleet",
    57: "bi-cloud-sleet",
    61: "bi-cloud-rain",
    63: "bi-cloud-rain",
    65: "bi-cloud-rain-heavy",
    66: "bi-cloud-sleet",
    67: "bi-cloud-sleet",
    71: "bi-cloud-snow",
    73: "bi-cloud-snow",
    75: "bi-cloud-snow",
    77: "bi-cloud-snow",
    80: "bi-cloud-rain",
    81: "bi-cloud-rain",
    82: "bi-cloud-rain-heavy",
    85: "bi-cloud-snow",
    86: "bi-cloud-snow",
    90: "bi-cloud-lightning-rain",
    95: "bi-cloud-lightning-rain",
    96: "bi-cloud-hail",
    99: "bi-cloud-hail",
}

_WEATHER_ICON_CLASS_MAP = {
    0: "sunny",
    1: "sunny",
    2: "partly-cloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "rain",
    56: "rain",
    57: "rain",
    61: "rain",
    63: "rain",
    65: "rain",
    66: "rain",
    67: "rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "rain",
    81: "rain",
    82: "rain",
    85: "snow",
    86: "snow",
    90: "storm",
    95: "storm",
    96: "storm",
    99: "storm",
}
_SLOVENE_WEEKDAYS = (
    "ponedeljek",
    "torek",
    "sreda",
    "četrtek",
    "petek",
    "sobota",
    "nedelja",
)
_LUNAR_MONTH_DAYS = 29.530588


def slovene_holidays(day: date) -> list[str]:
    slovene_calendar = holidays.SI(years=day.year, language="sl")
    print(slovene_calendar)
    return [str(slovene_calendar[day])] if day in slovene_calendar else []


@lru_cache(maxsize=32)
def saint_of_day(day: date) -> dict[str, str] | None:
    """Read current saint link from svetniki.info, once per calendar day."""
    try:
        response = requests.get(_SAINTS_URL, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.select("h2 a, h3 a, article a"):
            name = link.get_text(" ", strip=True)
            href = str(link.get("href") or "")
            parsed = urlparse(href)
            if (
                name
                and name.lower().startswith(
                    ("sveti ", "sveta ", "blaženi ", "marijino ")
                )
                and parsed.netloc == "svetniki.info"
                and parsed.path != "/"
            ):
                return {"name": name, "url": href}
    except (requests.RequestException, ValueError):
        pass
    return None


def daily_calendar(day: date | None = None) -> dict[str, Any]:
    day = day or date.today()
    return {
        "saint": saint_of_day(day),
        "holidays": slovene_holidays(day),
    }


def summarize_weather_code(code: Any) -> str:
    try:
        int_code = int(code)
    except (TypeError, ValueError):
        return "Neznano"
    return _WEATHER_CODE_MAP.get(int_code, "Neznano")


def weather_icon(code: Any) -> str:
    try:
        int_code = int(code)
    except (TypeError, ValueError):
        return "bi-question-circle"
    return _WEATHER_ICON_MAP.get(int_code, "bi-question-circle")


def weather_icon_class(code: Any) -> str:
    try:
        int_code = int(code)
    except (TypeError, ValueError):
        return "unknown"
    return _WEATHER_ICON_CLASS_MAP.get(int_code, "unknown")


def weekday_name(value: Any) -> str:
    try:
        return _SLOVENE_WEEKDAYS[date.fromisoformat(str(value)).weekday()]
    except (TypeError, ValueError, IndexError):
        return ""


def moon_phase_name(value: Any) -> str:
    try:
        phase = float(value) % 1
    except (TypeError, ValueError):
        return "Neznana lunina faza"
    if phase < 0.03 or phase >= 0.97:
        return "Mlada luna"
    if phase < 0.22:
        return "Rastoči srp"
    if phase < 0.28:
        return "Prvi krajec"
    if phase < 0.47:
        return "Rastoča luna"
    if phase < 0.53:
        return "Polna luna"
    if phase < 0.72:
        return "Padajoča luna"
    if phase < 0.78:
        return "Zadnji krajec"
    return "Padajoči srp"


def moon_illumination_percent(value: Any) -> int:
    try:
        phase = float(value) % 1
    except (TypeError, ValueError):
        return 0
    illumination = 1 - abs(2 * phase - 1)
    return round(illumination * 100)


def moon_shadow_offset_percent(value: Any) -> int:
    try:
        phase = float(value) % 1
    except (TypeError, ValueError):
        return 0
    if phase <= 0.5:
        return round(phase * 200)
    return round((phase - 1) * 200)


def hours_until_next_full_moon(
    value: Any, elapsed_hours: float = 0
) -> int | None:
    try:
        phase = float(value) % 1
    except (TypeError, ValueError):
        return None
    days = ((0.5 - phase) % 1) * _LUNAR_MONTH_DAYS
    if days > _LUNAR_MONTH_DAYS - 3:
        days = days - _LUNAR_MONTH_DAYS
    remaining_hours = days * 24 - max(0, elapsed_hours)
    return round(remaining_hours)


def _read_daily_value(daily: dict[str, Any], key: str, index: int):
    values = daily.get(key, [])
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def build_weather_data(
    payload: dict[str, Any], location: str
) -> dict[str, Any]:
    daily = payload.get("daily") or {}
    current = payload.get("current") or {}
    current_time = str(current.get("time") or "")
    current_date = current_time.split("T", 1)[0] or date.today().isoformat()
    try:
        elapsed_hours = (
            datetime.fromisoformat(current_time).hour
            + datetime.fromisoformat(current_time).minute / 60
        )
    except ValueError:
        elapsed_hours = 0
    forecast = []
    daily_times = daily.get("time") or []
    for index, day in enumerate(daily_times):
        code = _read_daily_value(daily, "weather_code", index)
        forecast.append(
            {
                "date": day,
                "weekday": weekday_name(day),
                "is_weekend": weekday_name(day) in {"sobota", "nedelja"},
                "is_past": str(day) < date.today().isoformat(),
                "weather_code": code,
                "weather_label": summarize_weather_code(code),
                "weather_icon": weather_icon(code),
                "weather_icon_class": weather_icon_class(code),
                "temperature_max": _read_daily_value(
                    daily, "temperature_2m_max", index
                ),
                "temperature_min": _read_daily_value(
                    daily, "temperature_2m_min", index
                ),
                "precipitation_sum": _read_daily_value(
                    daily, "precipitation_sum", index
                ),
                "sunrise": _read_daily_value(daily, "sunrise", index),
                "sunset": _read_daily_value(daily, "sunset", index),
                "moon_phase": _read_daily_value(daily, "moon_phase", index),
                "moon_label": moon_phase_name(
                    _read_daily_value(daily, "moon_phase", index)
                ),
                "moon_illumination": moon_illumination_percent(
                    _read_daily_value(daily, "moon_phase", index)
                ),
                "moon_shadow_offset": moon_shadow_offset_percent(
                    _read_daily_value(daily, "moon_phase", index)
                ),
                "hours_until_next_full_moon": hours_until_next_full_moon(
                    _read_daily_value(daily, "moon_phase", index),
                    elapsed_hours if str(day) == current_date else 0,
                ),
            }
        )

    return {
        "location": location,
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "timezone": payload.get("timezone") or "auto",
        "current": {
            "temperature": current.get("temperature_2m"),
            "is_day": current.get("is_day"),
            "precipitation": current.get("precipitation"),
            "weather_code": current.get("weather_code"),
            "weather_label": summarize_weather_code(
                current.get("weather_code")
            ),
            "weather_icon": weather_icon(current.get("weather_code")),
            "weather_icon_class": weather_icon_class(
                current.get("weather_code")
            ),
            "wind_speed": current.get("wind_speed_10m"),
            "cloud_cover": current.get("cloud_cover"),
        },
        "daily": forecast,
        "hourly": payload.get("hourly") or {},
        "hourly_units": payload.get("hourly_units") or {},
        "minutely_15": payload.get("minutely_15") or {},
        "minutely_15_units": payload.get("minutely_15_units") or {},
    }


def geocode_location(name: str) -> list[dict[str, Any]]:
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": name,
        "count": 5,
        "language": "en",
        "format": "json",
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()
    return payload.get("results", [])


def fetch_ip_location(ip: str | None) -> dict[str, Any] | None:
    if not ip or ip in {"127.0.0.1", "::1"}:
        return None
    try:
        response = requests.get(f"https://ipinfo.io/{ip}/json", timeout=5)
        response.raise_for_status()
        data = response.json()
        latitude, longitude = str(data.get("loc", "")).split(",", 1)
        return {
            "name": data.get("city") or data.get("region") or "Moja lokacija",
            "latitude": float(latitude),
            "longitude": float(longitude),
        }
    except (ValueError, IndexError, KeyError, requests.RequestException):
        return None


def fetch_weather_for_location(
    latitude: float, longitude: float, location: str
) -> dict[str, Any]:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,is_day,precipitation,weather_code,cloud_cover,"
            "wind_speed_10m"
        ),
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,sunrise,"
            "sunset,"
            "moon_phase,precipitation_sum"
        ),
        "hourly": (
            "temperature_2m,precipitation,wind_speed_10m,"
            "direct_normal_irradiance"
        ),
        "timezone": "auto",
        "past_days": 3,
        "forecast_days": 16,
        "minutely_15": (
            "temperature_2m,precipitation,wind_speed_10m,"
            "global_tilted_irradiance,weather_code,is_day,snowfall"
        ),
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()
    return build_weather_data(payload, location)
