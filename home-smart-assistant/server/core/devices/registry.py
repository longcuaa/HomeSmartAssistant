"""So dang ky thiet bi / phong / nhom / scene, nap tu cac file YAML.

Cung cap khop ten linh hoat (alias, dong nghia, bo dau) va loc theo phong. Day la nguon su
that ve 'nha co gi', dung cho ca Tier 1 (FST) lan Tier 3 (LLM, de dung danh sach thiet bi).
"""
import re
import yaml
from server.core import text_norm as tn

# Tu KHONG mang tinh phan biet khi khop thiet bi (de 'den phong khach' va 'den khach' deu khop).
_STOP = {"phong", "cai", "chiec", "may", "bo", "o"}


class Device:
    def __init__(self, d):
        self.id = d["id"]
        self.type = d.get("type", "")
        self.name = d.get("name", self.id)
        self.alias = d.get("alias", []) or []
        self.room = d.get("room")
        self.capabilities = d.get("capabilities", []) or []
        self.mqtt_topic = d.get("mqtt_topic")
        self.groups = d.get("groups", []) or []
        # Trang thai mo phong (khi chua co MQTT that). 'on' mac dinh tat.
        self.state = {"on": False}
        if "temperature" in self.capabilities:
            self.state["temperature"] = 26
        # Tap tu khoa de khop: gop tu 'name' + moi alias, bo tu chung va tu phong.
        self.keywords = self._build_keywords()

    def _build_keywords(self):
        kw = set()
        for text in [self.name] + self.alias:
            kw |= {w for w in tn.tokens(text) if w not in _STOP}
        return kw

    def can(self, capability):
        return capability in self.capabilities

    def to_brief(self):
        """Dong mo ta ngan cho LLM prompt: id, ten, phong, nang luc."""
        return f"{self.id} | {self.name} | phong={self.room} | {','.join(self.capabilities)}"


class Registry:
    def __init__(self, devices, groups, rooms, scenes):
        self.devices = {d.id: d for d in devices}
        self.groups = groups or {}
        self.rooms = rooms or {}
        self.scenes = scenes or {}
        # Token alias phong -> room_id, va token loai thiet bi de nhan dien.
        self._room_alias = self._index_room_aliases()
        # Tu vung thiet bi: gop tu khoa cua moi thiet bi. Dung de LOC bo tu khong-phai-thiet-bi
        # (dong tu 'bat'/'tat', so, tu noi) truoc khi xet phep tap-con.
        self._vocab = set().union(*[d.keywords for d in self.devices.values()]) \
            if self.devices else set()

    # --- nap tu file ---
    @classmethod
    def from_files(cls, devices_path, rooms_path, scenes_path):
        with open(devices_path, "r", encoding="utf-8") as f:
            ddata = yaml.safe_load(f) or {}
        with open(rooms_path, "r", encoding="utf-8") as f:
            rdata = yaml.safe_load(f) or {}
        with open(scenes_path, "r", encoding="utf-8") as f:
            sdata = yaml.safe_load(f) or {}
        devices = [Device(d) for d in ddata.get("devices", [])]
        return cls(devices, ddata.get("groups", {}), rdata.get("rooms", {}), sdata.get("scenes", {}))

    def _index_room_aliases(self):
        idx = {}
        for rid, r in self.rooms.items():
            for a in [r.get("name", rid)] + (r.get("alias", []) or []):
                idx[tn.norm(a)] = rid
        return idx

    # --- truy van ---
    def get(self, device_id):
        return self.devices.get(device_id)

    def room_in_text(self, text):
        """Tra ve room_id neu cau noi co nhac toi mot phong, nguoc lai None."""
        t = tn.norm(text)
        # Uu tien cum dai (vd 'phong ngu chinh') -> sap theo do dai giam dan.
        for alias in sorted(self._room_alias, key=len, reverse=True):
            if alias and re.search(rf"\b{re.escape(alias)}\b", t):
                return self._room_alias[alias]
        return None

    def find_devices(self, text, room=None):
        """Cac thiet bi khop voi cau noi. Quy tac: tu thiet bi noi ra phai la TAP CON tu khoa
        cua thiet bi (vd 'den khach' khop 'Den phong khach'). Neu co phong (noi ra hoac ngu canh
        bot) thi loc theo phong."""
        # Chi giu cac tu CO trong tu vung thiet bi -> bo dong tu ('bat'/'tat'), so, tu noi.
        said = {w for w in tn.tokens(text) if w not in _STOP} & self._vocab
        if not said:
            return []
        matches = [d for d in self.devices.values()
                   if d.keywords and said <= d.keywords]
        # Loc theo phong: uu tien phong noi trong cau, neu khong thi ngu canh bot.
        room_hint = self.room_in_text(text) or room
        if room_hint and len(matches) > 1:
            in_room = [d for d in matches if d.room == room_hint]
            if in_room:
                return in_room
        return matches

    def expand_group(self, name):
        """Tra ve danh sach Device cua mot nhom. '*' = toan bo."""
        members = self.groups.get(name)
        if members is None:
            return []
        if members == ["*"]:
            return list(self.devices.values())
        return [self.devices[i] for i in members if i in self.devices]

    def group_for_type(self, device_type):
        """Cac thiet bi cung loai (vd tat ca 'light') cho lenh nhom theo loai."""
        return [d for d in self.devices.values() if d.type == device_type]

    def match_scene(self, text):
        """Tra ve (scene_id, scene_dict) neu cau noi khop mot trigger phrase, nguoc lai None."""
        t = tn.norm(text)
        for sid, s in self.scenes.items():
            for phrase in s.get("trigger_phrases", []):
                p = tn.norm(phrase)
                if p and p in t:
                    return sid, s
        return None

    def device_list_text(self):
        """Danh sach thiet bi cho LLM prompt."""
        return "\n".join(d.to_brief() for d in self.devices.values())

    def group_list_text(self):
        names = list(self.groups.keys())
        return ", ".join(names)
