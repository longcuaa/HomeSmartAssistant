"""Thoi tiet ngoai troi qua Open-Meteo (mien phi, khong can API key).

Lay nhiet do, do am, tinh trang troi hien tai va khoang nhiet do hom nay theo toa do
HOME_LAT/HOME_LON trong config. Co cache ngan de khong goi mang lien tuc. Khong bao gio
nem loi: khi mat mang hay loi thi tra ve mot cau bao loi nhe.
"""
import time
import requests
import config

_URL = "https://api.open-meteo.com/v1/forecast"

# Ma thoi tiet WMO -> mo ta ngan (tieng Viet co dau cho TTS doc dung).
_CODES = {
    0: "quang đãng",
    1: "ít mây", 2: "mây rải rác", 3: "nhiều mây",
    45: "sương mù", 48: "sương mù đóng băng",
    51: "mưa phùn nhẹ", 53: "mưa phùn", 55: "mưa phùn dày",
    56: "mưa phùn lạnh", 57: "mưa phùn lạnh dày",
    61: "mưa nhẹ", 63: "mưa", 65: "mưa to",
    66: "mưa lạnh", 67: "mưa lạnh to",
    71: "tuyết nhẹ", 73: "tuyết", 75: "tuyết dày", 77: "hạt tuyết",
    80: "mưa rào nhẹ", 81: "mưa rào", 82: "mưa rào to",
    85: "mưa tuyết nhẹ", 86: "mưa tuyết to",
    95: "dông", 96: "dông kèm mưa đá", 99: "dông mạnh kèm mưa đá",
}

# Cache trong bo nho: thoi diem lay (monotonic) va cau ket qua.
_cache = {"t": 0.0, "text": None}


def _desc(code):
    return _CODES.get(code, "không rõ")


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
            f"Thời tiết ngoài trời: {round(cur['temperature_2m'])} độ, "
            f"độ ẩm {round(cur['relative_humidity_2m'])}%, {_desc(cur['weather_code'])}. "
            f"Hôm nay {round(daily['temperature_2m_min'][0])}-{round(daily['temperature_2m_max'][0])} độ, "
            f"{_desc(daily['weather_code'][0])}."
        )
        _cache["t"] = now
        _cache["text"] = text
        return text
    except Exception:
        return "Không lấy được thời tiết lúc này."
