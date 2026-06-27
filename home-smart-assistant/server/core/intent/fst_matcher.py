"""Tier 1 — khop mau nhanh (vai chuc ms), khong goi AI.

Day la 'duong tat' cho cac lenh thiet bi pho bien: bat/tat, dat nhiet do, am luong, lenh nhom,
kich hoat scene, hoi trang thai. Ke thua y tuong fast-path cua app/butler.py (du an cu) nhung
xuat ra Intent chuan thay vi chuoi.

Tra ve Intent neu khop chac chan; None neu khong -> de cac tang sau (embedding/LLM) xu ly.
flashtext duoc dung neu co cai (loc tu khoa nhanh hon), nhung khong bat buoc.
"""
import re
import yaml
from server.core import text_norm as tn
from server.models.intent import Intent
from server.core.intent.phrasing import Phraser


def _num(text):
    m = re.search(r"\b(\d{1,2})\b", text)
    return int(m.group(1)) if m else None


class FstMatcher:
    def __init__(self, cfg, registry, patterns_path):
        self.cfg = cfg
        self.reg = registry
        self.ph = Phraser(cfg)
        with open(patterns_path, "r", encoding="utf-8") as f:
            p = yaml.safe_load(f) or {}
        self.on_verbs = set(p.get("verbs", {}).get("ON", []))
        self.off_verbs = set(p.get("verbs", {}).get("OFF", []))
        self.temp_verbs = set(p.get("set_temp", {}).get("verbs", []))
        self.temp_triggers = set(p.get("set_temp", {}).get("triggers", []))
        self.vol_up = set(p.get("volume", {}).get("up", []))
        self.vol_down = set(p.get("volume", {}).get("down", []))
        self.vol_triggers = set(p.get("volume", {}).get("triggers", []))
        self.scope_words = [tn.norm(w) for w in p.get("group", {}).get("scope_words", [])]
        self.query_triggers = [tn.norm(w) for w in p.get("query", {}).get("triggers", [])]
        self.learned = {tn.norm_device(k): v for k, v in (p.get("learned") or {}).items()} \
            if isinstance(p.get("learned"), dict) else {}
        # Tu hanh dong de TACH khoi cau truoc khi tim thiet bi: tranh tu lenh trung voi ten thiet bi
        # (vd dong tu 'chinh' trung voi 'chinh' trong 'phong ngu chinh').
        self._action_words = (self.on_verbs | self.off_verbs | self.temp_verbs
                              | self.vol_up | self.vol_down)

    def _dev_text(self, text):
        """Bo tu hanh dong (bat/tat/chinh...) khoi cau de tim thiet bi cho sach."""
        t = tn.norm_device(text)
        for w in self._action_words:
            t = re.sub(rf"\b{re.escape(w)}\b", " ", t)
        return t

    def _has_word(self, t, words):
        return any(re.search(rf"\b{re.escape(w)}\b", t) for w in words)

    def _has_phrase(self, t, phrases):
        return any(ph and ph in t for ph in phrases)

    def match(self, text, room=None):
        """Phan giai cau noi o Tier 1. Tra ve Intent hoac None."""
        t = tn.norm_device(text)
        if not t:
            return None

        # 0) Cau da hoc (tu Tier 3 thang len) khop tuyet doi.
        if t in self.learned:
            data = dict(self.learned[t])
            return Intent(**data)

        # 1) Scene: khop trigger phrase.
        scene = self.reg.match_scene(text)
        if scene:
            sid, s = scene
            targets = [dict(a) for a in s.get("actions", [])]
            return Intent(intent="SCENE", action="SCENE", device_id=sid,
                          parameters={"scene": sid}, targets=targets,
                          response_vi=s.get("response_vi", "Dạ, tôi đã thực hiện ạ."),
                          confidence=0.97)

        on = self._has_word(t, self.on_verbs)
        off = self._has_word(t, self.off_verbs)
        num = _num(t)

        # 2) Lenh NHOM: co tu pham vi ('het', 'tat ca'...) + bat/tat.
        if (on or off) and self._has_phrase(t, self.scope_words):
            devs = self._scope_devices(text)
            action = "GROUP_ON" if on else "GROUP_OFF"
            sub = "ON" if on else "OFF"
            targets = [{"device_id": d.id, "action": sub} for d in devs]
            return Intent(intent="GROUP", action=action, device_type="group",
                          parameters={"count": len(devs)}, targets=targets,
                          response_vi=self.ph.confirm_group(action, len(devs)), confidence=0.95)

        # 3) Dat nhiet do: co so + tu chi nhiet do + thiet bi chinh duoc nhiet.
        if num is not None and self._has_word(t, self.temp_triggers):
            ac = [d for d in self.reg.find_devices(self._dev_text(text), room) if d.can("temperature")]
            if len(ac) == 1:
                temp = max(16, min(30, num))
                d = ac[0]
                return Intent(intent="CONTROL", action="SET", device_type=d.type,
                              device_id=d.id, room=d.room,
                              parameters={"temperature": temp},
                              response_vi=self.ph.confirm_temp(d.name, temp), confidence=0.95)
            if len(ac) > 1:
                return self._ask_room("SET", "điều hòa", ac)

        # 4) Am luong: tang/giam + tu chi am luong.
        if self._has_word(t, self.vol_triggers):
            up = self._has_word(t, self.vol_up)
            down = self._has_word(t, self.vol_down)
            if up ^ down:
                tvs = [d for d in self.reg.find_devices(self._dev_text(text), room) if d.can("volume")] \
                    or [d for d in self.reg.group_for_type("tv")]
                if len(tvs) == 1:
                    d = tvs[0]
                    direction = "up" if up else "down"
                    step = num if num is not None else 10
                    return Intent(intent="CONTROL", action="SET", device_type=d.type,
                                  device_id=d.id, room=d.room,
                                  parameters={"volume_dir": direction, "step": step},
                                  response_vi=self.ph.confirm_volume(direction, d.name),
                                  confidence=0.9)

        # 5) Hoi trang thai (QUERY).
        if self._has_phrase(t, self.query_triggers) and not (on or off):
            devs = self.reg.find_devices(self._dev_text(text), room)
            if len(devs) == 1:
                d = devs[0]
                temp = d.state.get("temperature")
                return Intent(intent="QUERY", action="GET", device_type=d.type,
                              device_id=d.id, room=d.room, parameters={},
                              response_vi=self.ph.status(d.name, d.state.get("on"), temp),
                              confidence=0.9)

        # 6) Bat/tat thiet bi cu the.
        if on ^ off:
            action = "ON" if on else "OFF"
            devs = self.reg.find_devices(self._dev_text(text), room)
            if len(devs) == 1:
                d = devs[0]
                return Intent(intent="CONTROL", action=action, device_type=d.type,
                              device_id=d.id, room=d.room, parameters={},
                              response_vi=self.ph.confirm_control(action, d.name),
                              confidence=0.96)
            if len(devs) > 1:
                # Nhieu thiet bi cung loai, khong ro phong -> hoi lai (van la Tier 1, khong can LLM).
                word = self._device_word(devs)
                return self._ask_room(action, word, devs)

        # Khong chac -> de tang sau xu ly.
        return None

    # --- ho tro ---
    def _scope_devices(self, text):
        """Voi lenh nhom: neu co nhac loai thiet bi (den/quat...) thi gioi han theo loai,
        nguoc lai ('het', 'thiet bi', 'trong nha') lay toan bo nha."""
        t = tn.norm_device(text)
        # Bo tu pham vi + tu CHUNG CHUNG ('thiet bi', 'trong nha') de khong khop nham mot phong.
        for w in self.scope_words + ["thiet bi", "trong nha", "trong", "nha"]:
            t = re.sub(rf"\b{re.escape(w)}\b", " ", t)
        typed = self.reg.find_devices(t)
        if typed:
            # Gom theo loai cua thiet bi khop (vd 'tat het den' -> tat ca den).
            types = {d.type for d in typed}
            return [d for d in self.reg.devices.values() if d.type in types]
        return list(self.reg.devices.values())

    def _device_word(self, devs):
        types = {d.type for d in devs}
        names = {"light": "đèn", "fan": "quạt", "ac": "điều hòa", "tv": "tivi"}
        if len(types) == 1:
            return names.get(next(iter(types)), "thiết bị")
        return "thiết bị"

    def _ask_room(self, action, word, devs):
        rooms = []
        for d in devs:
            r = self.reg.rooms.get(d.room, {})
            rooms.append(r.get("name", d.room))
        return Intent(intent="UNKNOWN", action=None, device_type="light" if word == "đèn" else None,
                      parameters={"candidates": [d.id for d in devs]},
                      response_vi=self.ph.ask_room(action, word, ", ".join(dict.fromkeys(rooms))),
                      confidence=0.5)
