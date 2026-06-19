"""Bo nho dai han cua chu nha, luu trong data/memory.json.

Tach rieng khoi kho tai lieu de tranh lan thong tin chua xac thuc vao kien thuc tin cay.
Luu ba loai:
- preferences: so thich chu nha noi ro, ghi qua cong cu remember_preference.
- facts: thong tin co dinh ve ngoi nha va gia dinh (ten phong, thanh vien, thoi quen),
  ghi qua cong cu remember_fact.
- topics: dem so lan chu nha hoi ve mot chu de. Hoi nhieu lan se thanh "quan tam" va
  duoc chen vao system prompt de quan gia chu dong hon. Day la cach hoc dan tu cau hoi.

Tuong thich nguoc: file cu dang list[str] duoc coi la danh sach preferences.
"""
import os
import json
import config


def _empty():
    return {"preferences": [], "facts": [], "topics": {}}


def load():
    """Doc bo nho, chuan hoa ve dict 3 phan. Ho tro file cu dang list."""
    if not os.path.exists(config.MEMORY_PATH):
        return _empty()
    with open(config.MEMORY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):  # dinh dang cu: chi co so thich
        return {"preferences": data, "facts": [], "topics": {}}
    base = _empty()
    base.update({k: data.get(k, base[k]) for k in base})
    return base


def _save(data):
    os.makedirs(os.path.dirname(config.MEMORY_PATH), exist_ok=True)
    with open(config.MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _add_to_list(key, text, label):
    data = load()
    item = (text or "").strip()
    if not item:
        return "Khong co noi dung de ghi nho."
    if item not in data[key]:
        data[key].append(item)
        data[key] = data[key][-config.MEMORY_MAX_ITEMS:]  # giu phan gan day nhat
        _save(data)
    return f"Da ghi nho ({label}): {item}"


def add(preference):
    """Ghi nho mot so thich ro rang cua chu nha."""
    return _add_to_list("preferences", preference, "so thich")


def add_fact(fact):
    """Ghi nho mot thong tin co dinh ve nha hoac gia dinh."""
    return _add_to_list("facts", fact, "thong tin nha")


def note_topic(query):
    """Dem mot lan chu nha hoi ve chu de. Hoi du nhieu lan se thanh quan tam."""
    topic = (query or "").strip().lower()
    if not topic:
        return
    data = load()
    topics = data["topics"]
    topics[topic] = topics.get(topic, 0) + 1
    if len(topics) > config.MEMORY_MAX_TOPICS:  # tia bot: bo chu de chi hoi 1 lan, giu cac chu de hoi nhieu
        topics = dict(sorted(((k, v) for k, v in topics.items() if v > 1),
                             key=lambda kv: kv[1], reverse=True)[:config.MEMORY_MAX_TOPICS])
    data["topics"] = topics
    _save(data)


def interests():
    """Cac chu de chu nha hoi tu nguong tro len, sap theo so lan giam dan."""
    data = load()
    hot = [(t, c) for t, c in data["topics"].items() if c >= config.INTEREST_THRESHOLD]
    hot.sort(key=lambda kv: kv[1], reverse=True)
    return [t for t, _ in hot[:config.MEMORY_MAX_INTERESTS]]


def as_text():
    """Gop bo nho thanh chuoi de chen vao system prompt. Rong neu chua co gi."""
    data = load()
    parts = []
    if data["preferences"]:
        parts.append("So thich: " + "; ".join(data["preferences"]))
    if data["facts"]:
        parts.append("Thong tin nha: " + "; ".join(data["facts"]))
    its = interests()
    if its:
        parts.append("Chu nha hay quan tam: " + ", ".join(its))
    return ". ".join(parts)


def clear():
    _save(_empty())
    return "Da xoa bo nho."
