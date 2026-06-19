"""Cong cu cho quan gia: dieu khien thiet bi qua MQTT, tra cuu tai lieu, ghi nho so thich.

Lenh thiet bi va doc cam bien di qua app/device.py (MQTT). Khi khong co broker o localhost,
device.py tu chuyen sang gia lap, va cac ham o day fall back ve dict HOME/SENSORS, gan hau to
'(gia lap)' vao cau xac nhan de khong bi nham la dang dung thiet bi that.

Phan khai bao cong cu TOOLS la hop dong voi model, giu on dinh du ha tang ben duoi thay doi.
"""
import json
import config
from app import llm, vector_store, memory, device as hub, weather, calendar_store

# Trang thai nha gia lap, dung khi khong co broker. Thuc te doc qua MQTT.
HOME = {
    "den phong khach": {"on": False},
    "den phong ngu": {"on": False},
    "quat phong khach": {"on": False},
    "dieu hoa phong ngu": {"on": False, "temp": 26},
}

# Gia tri cam bien gia lap, dung khi khong co cam bien that tra ve.
SENSORS = {
    "nhiet_do": 28,
    "do_am": 65,
    "chat_luong_khong_khi": "tot",
    "do_sang": 300,
}

# Map key moi truong sang topic MQTT tuong ung.
_SENSOR_TOPICS = {
    "nhiet_do": config.SENSOR_TOPIC_NHIET_DO,
    "do_am": config.SENSOR_TOPIC_DO_AM,
    "chat_luong_khong_khi": config.SENSOR_TOPIC_KHONG_KHI,
    "do_sang": config.SENSOR_TOPIC_DO_SANG,
}

# Timeout ngan khi doc trang thai/cam bien de cong cu khong cham.
_READ_TIMEOUT = 2


def _set_topic(device):
    return f"home/devices/{device}/set"


def _parse_value(raw):
    """Chuyen payload tho tu MQTT thanh gia tri don gian (so, hoac dict da parse, hoac chuoi)."""
    raw = raw.strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj.get("value", obj.get("state", obj))
        return obj
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        return float(raw) if "." in raw else int(raw)
    except ValueError:
        return raw


def turn_on_device(device):
    if device not in HOME:
        return f"Khong tim thay thiet bi '{device}'."
    if hub.publish(_set_topic(device), {"state": "ON"}):
        return f"Da bat {device}."
    if hub.simulated():
        HOME[device]["on"] = True
        return f"Da bat {device}. (gia lap)"
    return f"Khong gui duoc lenh toi {device}."


def turn_off_device(device):
    if device not in HOME:
        return f"Khong tim thay thiet bi '{device}'."
    if hub.publish(_set_topic(device), {"state": "OFF"}):
        return f"Da tat {device}."
    if hub.simulated():
        HOME[device]["on"] = False
        return f"Da tat {device}. (gia lap)"
    return f"Khong gui duoc lenh toi {device}."


def set_temperature(device, temperature):
    d = HOME.get(device)
    if d is None or "temp" not in d:
        return f"Thiet bi '{device}' khong chinh duoc nhiet do."
    if hub.publish(_set_topic(device), {"state": "ON", "temperature": temperature}):
        return f"Da dat {device} o {temperature} do."
    if hub.simulated():
        d["on"] = True
        d["temp"] = temperature
        return f"Da dat {device} o {temperature} do. (gia lap)"
    return f"Khong gui duoc lenh toi {device}."


def _format_state(state):
    """Chuyen trang thai thiet bi thanh chuoi de model doc de hieu (tranh bat model tu parse JSON)."""
    parts = []
    for name, st in state.items():
        if isinstance(st, dict):
            status = "bat" if st.get("on") else "tat"
            if "temp" in st:
                status += f", {st['temp']} do"
        else:
            status = str(st)
        parts.append(f"{name}: {status}")
    return "; ".join(parts) if parts else "Khong co thiet bi nao."


def get_home_state():
    """Trang thai thiet bi: doc tu broker, fall back ve HOME dict khi gia lap hoac chua co du lieu."""
    if hub.simulated():
        return _format_state(HOME)
    state = {}
    for name in HOME:
        raw = hub.read_sensor(f"home/devices/{name}/state", timeout=_READ_TIMEOUT)
        if raw is None:
            state[name] = HOME[name]
            continue
        try:
            state[name] = json.loads(raw)  # giu nguyen object trang thai day du
        except (json.JSONDecodeError, ValueError):
            state[name] = raw.strip()
    return _format_state(state)


def get_environment():
    """Chi so moi truong: doc tung cam bien qua MQTT, fall back ve gia tri gia lap khi thieu."""
    labels = {"nhiet_do": "nhiet do", "do_am": "do am",
              "chat_luong_khong_khi": "chat luong khong khi", "do_sang": "do sang"}
    parts = []
    for key, topic in _SENSOR_TOPICS.items():
        raw = hub.read_sensor(topic, timeout=_READ_TIMEOUT)
        value = _parse_value(raw) if raw is not None else SENSORS[key]
        parts.append(f"{labels.get(key, key)}: {value}")
    return "; ".join(parts)


def search_knowledge(query):
    memory.note_topic(query)  # hoc dan tu cau hoi: chu de hoi nhieu lan se thanh quan tam
    docs, metas = vector_store.query(llm.embed(query))
    if not docs:
        return "Khong tim thay thong tin trong tai lieu."
    return "\n\n".join(f"[{m['source']}] {d}" for d, m in zip(docs, metas))


def remember_preference(preference):
    return memory.add(preference)


def remember_fact(fact):
    return memory.add_fact(fact)


def get_weather():
    """Thoi tiet ngoai troi hien tai va du bao hom nay (qua Open-Meteo)."""
    return weather.current_text()


def get_calendar():
    """Su kien trong lich hom nay va su kien sap toi."""
    text = calendar_store.as_text()
    return text or "Lich hien dang trong."


def add_event(date, time="", title=""):
    """Them mot su kien vao lich. date dang YYYY-MM-DD, time dang HH:MM."""
    return calendar_store.add(date, time, title)


_REGISTRY = {
    "turn_on_device": turn_on_device,
    "turn_off_device": turn_off_device,
    "set_temperature": set_temperature,
    "get_home_state": get_home_state,
    "get_environment": get_environment,
    "search_knowledge": search_knowledge,
    "remember_preference": remember_preference,
    "remember_fact": remember_fact,
    "get_weather": get_weather,
    "get_calendar": get_calendar,
    "add_event": add_event,
}


def execute(name, arguments):
    """Goi mot cong cu theo ten voi tham so dang dict. Tra ve chuoi ket qua."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return f"Khong co cong cu '{name}'."
    try:
        return fn(**arguments)
    except TypeError as e:
        return f"Tham so khong hop le cho '{name}': {e}"


# Mo ta cong cu theo chuan OpenAI tool calling
TOOLS = [
    {"type": "function", "function": {
        "name": "turn_on_device",
        "description": "Bat mot thiet bi trong nha nhu den, quat, dieu hoa.",
        "parameters": {"type": "object", "properties": {
            "device": {"type": "string", "description": "Ten thiet bi, vi du 'den phong khach'"},
        }, "required": ["device"]}}},
    {"type": "function", "function": {
        "name": "turn_off_device",
        "description": "Tat mot thiet bi trong nha.",
        "parameters": {"type": "object", "properties": {
            "device": {"type": "string", "description": "Ten thiet bi"},
        }, "required": ["device"]}}},
    {"type": "function", "function": {
        "name": "set_temperature",
        "description": "Dat nhiet do cho thiet bi co dieu chinh nhiet nhu dieu hoa.",
        "parameters": {"type": "object", "properties": {
            "device": {"type": "string", "description": "Ten thiet bi"},
            "temperature": {"type": "integer", "description": "Nhiet do tinh bang do C"},
        }, "required": ["device", "temperature"]}}},
    {"type": "function", "function": {
        "name": "get_home_state",
        "description": "Xem TRANG THAI hien tai cua thiet bi trong nha (bat/tat, nhiet do dieu hoa). "
                       "GOI cong cu nay khi chu nha hoi ve tinh trang thiet bi, vi du 'den phong khach "
                       "co dang bat khong', 'nha co thiet bi gi', 'dieu hoa dang bao nhieu do'. Day la "
                       "nguon du lieu thiet bi that — hay goi de lay, dung doan.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_environment",
        "description": "Xem chi so moi truong trong nha hien tai: nhiet do, do am, chat luong khong "
                       "khi, do sang. GOI khi chu nha hoi ve cac chi so nay (vi du 'trong nha bao nhieu "
                       "do', 'khong khi the nao').",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "search_knowledge",
        "description": "Tra cuu tai lieu, huong dan trong nha va tin tuc de tra loi cau hoi kien thuc, "
                       "cach lam, va cach khac phuc su co (router/wifi/mang, thiet bi hong, dieu hoa, "
                       "den, quat). DUNG cong cu nay cho MOI cau dang 'lam sao / xu ly the nao / cach / "
                       "tai sao' ve nha hoac thiet bi.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Cau truy van can tra cuu"},
        }, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "remember_preference",
        "description": "Ghi nho mot so thich cua chu nha de ca nhan hoa goi y lan sau.",
        "parameters": {"type": "object", "properties": {
            "preference": {"type": "string", "description": "So thich, vi du thich de dieu hoa 25 do vao ban dem"},
        }, "required": ["preference"]}}},
    {"type": "function", "function": {
        "name": "remember_fact",
        "description": "Ghi nho thong tin co dinh ve ngoi nha hoac gia dinh, vi du ten phong, "
                       "thanh vien, thoi quen sinh hoat.",
        "parameters": {"type": "object", "properties": {
            "fact": {"type": "string", "description": "Thong tin can ghi nho, vi du 'phong ngu chinh o tang 2'"},
        }, "required": ["fact"]}}},
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "Lay thoi tiet ngoai troi hien tai va du bao hom nay: nhiet do, do am, tinh "
                       "trang troi. Dung khi chu nha hoi ve thoi tiet ben ngoai.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_calendar",
        "description": "Xem lich su kien hom nay va su kien sap toi cua chu nha.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "add_event",
        "description": "Them mot su kien vao lich cua chu nha de nhac sau nay.",
        "parameters": {"type": "object", "properties": {
            "date": {"type": "string", "description": "Ngay dang YYYY-MM-DD"},
            "time": {"type": "string", "description": "Gio dang HH:MM, co the de trong"},
            "title": {"type": "string", "description": "Noi dung su kien, vi du 'hop gia dinh'"},
        }, "required": ["date", "title"]}}},
]
