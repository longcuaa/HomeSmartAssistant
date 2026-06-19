"""Thoi tiet ngoai troi qua Open-Meteo (mien phi, khong can API key).

Lay nhiet do, do am, tinh trang troi hien tai va khoang nhiet do hom nay theo toa do
HOME_LAT/HOME_LON trong config. Co cache ngan de khong goi mang lien tuc. Khong bao gio
nem loi: khi mat mang hay loi thi tra ve mot cau bao loi nhe.
"""
import time
import requests
import config

_URL = "https://api.open-meteo.com/v1/forecast"

# Ma thoi tiet WMO -> mo ta ngan (tieng Viet ASCII).
_CODES = {
    0: "quang dang",
    1: "it may", 2: "may rai rac", 3: "nhieu may",
    45: "suong mu", 48: "suong mu dong bang",
    51: "mua phun nhe", 53: "mua phun", 55: "mua phun day",
    56: "mua phun lanh", 57: "mua phun lanh day",
    61: "mua nhe", 63: "mua", 65: "mua to",
    66: "mua lanh", 67: "mua lanh to",
    71: "tuyet nhe", 73: "tuyet", 75: "tuyet day", 77: "hat tuyet",
    80: "mua rao nhe", 81: "mua rao", 82: "mua rao to",
    85: "mua tuyet nhe", 86: "mua tuyet to",
    95: "dong", 96: "dong kem mua da", 99: "dong manh kem mua da",
}

# Cache trong bo nho: thoi diem lay (monotonic) va cau ket qua.
_cache = {"t": 0.0, "text": None}


def _desc(code):
    return _CODES.get(code, "khong ro")


def current_text():
    """Mot cau ngan ve thoi tiet ngoai troi. Dung cache, khong nem loi."""
    now = time.monotonic()
    if _cache["text"] is not None and now - _cache["t"] < config.WEATHER_CACHE_SECS:
        return _cache["text"]
    try:
        r = requests.get(
            _URL,
            params={
                "latitude": config.HOME_LAT,
                "longitude": config.HOME_LON,
                "current": "temperature_2m,relative_humidity_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "timezone": "auto",
                "forecast_days": 1,
            },
            headers={"User-Agent": config.WEATHER_USER_AGENT},
            timeout=config.WEATHER_TIMEOUT,
        )
        r.raise_for_status()
        d = r.json()
        cur = d["current"]
        daily = d["daily"]
        text = (
            f"Thoi tiet ngoai troi: {round(cur['temperature_2m'])} do, "
            f"do am {round(cur['relative_humidity_2m'])}%, {_desc(cur['weather_code'])}. "
            f"Hom nay {round(daily['temperature_2m_min'][0])}-{round(daily['temperature_2m_max'][0])} do, "
            f"{_desc(daily['weather_code'][0])}."
        )
        _cache["t"] = now
        _cache["text"] = text
        return text
    except Exception:
        return "Khong lay duoc thoi tiet luc nay."
