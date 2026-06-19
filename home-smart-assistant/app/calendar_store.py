"""Lich su kien cuc bo cua chu nha, luu trong data/events.json.

Moi su kien la mot dict {"date": "YYYY-MM-DD", "time": "HH:MM", "title": "..."}.
Chu nha co the dien san file nay, hoac quan gia ghi them qua cong cu add_event.
Tach rieng khoi kho tai lieu, giong cach lam cua memory.py.
"""
import os
import json
from datetime import datetime
import config


def load():
    """Doc danh sach su kien, sap theo ngay gio. Thieu file thi tra ve []."""
    if not os.path.exists(config.EVENTS_PATH):
        return []
    with open(config.EVENTS_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)
    items.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
    return items


def _save(items):
    os.makedirs(os.path.dirname(config.EVENTS_PATH), exist_ok=True)
    with open(config.EVENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add(date, time, title):
    """Them mot su kien moi vao lich. date dang YYYY-MM-DD, time dang HH:MM."""
    title = (title or "").strip()
    date = (date or "").strip()
    if not title or not date:
        return "Thieu ngay hoac noi dung su kien."
    items = load()
    items.append({"date": date, "time": (time or "").strip(), "title": title})
    _save(items)
    return f"Da them vao lich: {date} {time} {title}".strip()


def _fmt(e):
    t = e.get("time", "")
    return f"{t} {e['title']}".strip() if t else e["title"]


def as_text():
    """Su kien hom nay va su kien sap toi gan nhat, dang chuoi. Rong neu khong co gi."""
    items = load()
    if not items:
        return ""
    today = datetime.now().strftime("%Y-%m-%d")
    today_evs = [e for e in items if e.get("date") == today]
    upcoming = [e for e in items if e.get("date", "") > today]

    parts = []
    if today_evs:
        parts.append("Hom nay: " + "; ".join(_fmt(e) for e in today_evs))
    else:
        parts.append("Hom nay khong co lich")
    if upcoming:
        # Hien TAT CA su kien sap toi (toi da 5) de khong bo sot, da sap xep tang dan.
        parts.append("Sap toi: " + "; ".join(f"{e['date']} {_fmt(e)}".strip() for e in upcoming[:5]))
    return ". ".join(parts)
