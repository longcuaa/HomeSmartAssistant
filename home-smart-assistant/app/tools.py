"""Cong cu cho quan gia: dieu khien thiet bi qua MQTT, tra cuu tai lieu, ghi nho so thich.

Lenh thiet bi va doc cam bien di qua app/device.py (MQTT). Khi khong co broker o localhost,
device.py tu chuyen sang gia lap, va cac ham o day fall back ve dict HOME/SENSORS, gan hau to
'(gia lap)' vao cau xac nhan de khong bi nham la dang dung thiet bi that.

Phan khai bao cong cu TOOLS la hop dong voi model, giu on dinh du ha tang ben duoi thay doi.
"""
import json
import unicodedata
import config
from app import llm, vector_store, memory, device as hub, weather, calendar_store

# Trang thai nha gia lap, dung khi khong co broker. Thuc te doc qua MQTT.
# Key dat ASCII khong dau theo quy uoc; ham _find_device() khop ca khi nguoi dung noi co dau.
HOME = {
    "đèn trần phòng khách": {"on": False},
    "đèn LED phòng khách": {"on": False},
    "điều hòa phòng khách": {"on": False, "temp": 26},
    "đèn phòng bếp": {"on": False},
    "đèn phòng ngủ": {"on": False},
    "quạt phòng ngủ": {"on": False},
    "điều hòa phòng ngủ": {"on": False, "temp": 26},
    "đèn phòng học": {"on": False},
    "quạt phòng học": {"on": False},
    "đèn hành lang": {"on": False},
}

# Gia tri cam bien gia lap, dung khi khong co cam bien that tra ve.
SENSORS = {
    "nhiet_do": 28,
    "do_am": 65,
    "chat_luong_khong_khi": "tốt",
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


def _norm(s):
    """Bo dau, ve chu thuong de khop ten thiet bi du nguoi dung go co dau hay khong, hoa hay thuong."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").strip()


def _find_device(name):
    """Tim key thiet bi that trong HOME khop voi ten nguoi dung noi (khong phan biet dau/hoa thuong)."""
    if not name:
        return None
    if name in HOME:
        return name
    target = _norm(name)
    for key in HOME:
        if _norm(key) == target:
            return key
    # Khop mem: tat ca tu trong 'name' nam trong ten thiet bi, va CHI DUNG 1 thiet bi khop
    # (vd 'den bep' -> 'den phong bep'); neu mo ho (nhieu khop) thi tra None de khoi chon bua.
    tw = set(target.split())
    cands = [k for k in HOME if tw and tw <= set(_norm(k).split())]
    return cands[0] if len(cands) == 1 else None


def turn_on_device(device):
    if device not in HOME:
        return f"Không tìm thấy thiết bị '{device}'."
    if hub.publish(_set_topic(device), {"state": "ON"}):
        return f"Đã bật {device}."
    if hub.simulated():
        HOME[device]["on"] = True
        return f"Đã bật {device}. (giả lập)"
    return f"Không gửi được lệnh tới {device}."


def turn_off_device(device):
    if device not in HOME:
        return f"Không tìm thấy thiết bị '{device}'."
    if hub.publish(_set_topic(device), {"state": "OFF"}):
        return f"Đã tắt {device}."
    if hub.simulated():
        HOME[device]["on"] = False
        return f"Đã tắt {device}. (giả lập)"
    return f"Không gửi được lệnh tới {device}."


def set_temperature(device, temperature):
    d = HOME.get(device)
    if d is None or "temp" not in d:
        return f"Thiết bị '{device}' không chỉnh được nhiệt độ."
    if hub.publish(_set_topic(device), {"state": "ON", "temperature": temperature}):
        return f"Đã đặt {device} ở {temperature} độ."
    if hub.simulated():
        d["on"] = True
        d["temp"] = temperature
        return f"Đã đặt {device} ở {temperature} độ. (giả lập)"
    return f"Không gửi được lệnh tới {device}."


def _format_state(state):
    """Chuyen trang thai thiet bi thanh chuoi de model doc de hieu (tranh bat model tu parse JSON)."""
    parts = []
    for name, st in state.items():
        if isinstance(st, dict):
            status = "bật" if st.get("on") else "tắt"
            if "temp" in st:
                status += f", {st['temp']} độ"
        else:
            status = str(st)
        parts.append(f"{name}: {status}")
    return "; ".join(parts) if parts else "Không có thiết bị nào."


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
    labels = {"nhiet_do": "nhiệt độ", "do_am": "độ ẩm",
              "chat_luong_khong_khi": "chất lượng không khí", "do_sang": "độ sáng"}
    units = {"nhiet_do": " độ C", "do_am": "%", "do_sang": " lux"}
    parts = []
    for key, topic in _SENSOR_TOPICS.items():
        raw = hub.read_sensor(topic, timeout=_READ_TIMEOUT)
        value = _parse_value(raw) if raw is not None else SENSORS[key]
        parts.append(f"{labels.get(key, key)}: {value}{units.get(key, '')}")
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
    return text or "Lịch hiện đang trống."


def add_event(date, time="", title=""):
    """Them mot su kien vao lich. date dang YYYY-MM-DD, time dang HH:MM."""
    return calendar_store.add(date, time, title)


# --- Cong cu GOP: it cong cu hon de model nho (3b) chon dung hon va prefill nhe hon.
# Cac ham turn_on_device/turn_off_device/set_temperature/get_home_state/get_environment o tren
# duoc giu lai lam ham noi bo, goi qua cac ham gop nay. ---

def control_device(device, state=None, temperature=None):
    """Dieu khien thiet bi: bat/tat va/hoac dat nhiet do (gop turn_on/turn_off/set_temperature)."""
    key = _find_device(device)
    if key is None:
        return f"Không tìm thấy thiết bị '{device}'."
    if temperature is not None:
        return set_temperature(key, temperature)
    if state is None:
        return "Cần cho biết bật hay tắt thiết bị."
    s = str(state).strip().lower()
    if s in ("on", "bat", "mo", "true", "1"):
        return turn_on_device(key)
    if s in ("off", "tat", "dong", "false", "0"):
        return turn_off_device(key)
    return f"Trạng thái '{state}' không hợp lệ (chỉ 'on' hoặc 'off')."


def get_status():
    """Trang thai thiet bi + chi so moi truong, gop mot lan (gop get_home_state/get_environment).

    Ket qua noi thang cho chu nha (get_status nam trong DIRECT_REPLY_TOOLS) nen viet de doc.
    """
    return f"Thiết bị trong nhà: {get_home_state()}. Môi trường: {get_environment()}."


def remember(info):
    """Ghi nho thong tin ve chu nha/ngoi nha (gop remember_preference/remember_fact)."""
    return memory.add_fact(info)


_REGISTRY = {
    "control_device": control_device,
    "get_status": get_status,
    "search_knowledge": search_knowledge,
    "remember": remember,
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
        "name": "control_device",
        "description": "Dieu khien thiet bi trong nha (den, quat, dieu hoa): bat, tat, hoac dat nhiet do.",
        "parameters": {"type": "object", "properties": {
            "device": {"type": "string", "description": "Ten thiet bi, vi du 'den phong khach'"},
            "state": {"type": "string", "enum": ["on", "off"], "description": "Bat (on) hay tat (off)"},
            "temperature": {"type": "integer", "description": "Nhiet do do C (chi cho dieu hoa)"},
        }, "required": ["device"]}}},
    {"type": "function", "function": {
        "name": "get_status",
        "description": "Xem tinh trang hien tai trong nha: thiet bi nao dang bat/tat, nhiet do dieu hoa, "
                       "va chi so moi truong (nhiet do, do am, khong khi, do sang). GOI khi chu nha hoi "
                       "ve tinh trang thiet bi hoac moi truong; lay du lieu that, dung doan.",
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
        "name": "remember",
        "description": "Ghi nho khi chu nha BAY TO so thich/thoi quen hoac yeu cau nho. Kich hoat boi "
                       "cac cau nhu 'toi thich...', 'toi thuong...', 'nho giup toi...', 'nho la...', "
                       "'lan sau...'. Vi du 'toi thich de dieu hoa 25 do ban dem' -> remember(info='thich "
                       "de dieu hoa 25 do ban dem'). Day la GHI NHO, KHONG phai dieu khien thiet bi hay tra cuu.",
        "parameters": {"type": "object", "properties": {
            "info": {"type": "string", "description": "Noi dung so thich/thong tin can ghi nho"},
        }, "required": ["info"]}}},
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
