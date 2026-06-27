"""Bo kiem thu phan giai y dinh (Tier 0-3). Chay duoc ma KHONG can Ollama/Redis.

Cac cau Tier 0/1 la TAT DINH -> co kiem tra dung/sai. Cau can Tier 2/3 (embedding/LLM) chi
duoc IN ra de tham khao (bo qua khi backend chua san sang), khong tinh la that bai.

Chay: python scripts/test_intent.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.config import cfg
from server.core.devices.registry import Registry
from server.core.intent.resolver import Resolver

# (cau, room, ky vong). 'tier' la tang toi da chap nhan; 'intent'/'action'/'device' kiem tra neu co.
# Dat tier=1 nghia la PHAI giai quyet o Tier 0/1 (tat dinh, khong can AI).
CASES = [
    # --- Bat/tat 1 thiet bi ro rang (Tier 1) ---
    {"q": "bật đèn phòng khách", "tier": 1, "intent": "CONTROL", "action": "ON", "device": "light_living_01"},
    {"q": "tắt tivi", "tier": 1, "intent": "CONTROL", "action": "OFF", "device": "tv_living_01"},
    {"q": "bật quạt phòng khách", "tier": 1, "intent": "CONTROL", "action": "ON", "device": "fan_living_01"},
    {"q": "tắt đèn bếp", "tier": 1, "intent": "CONTROL", "action": "OFF", "device": "light_kitchen_01"},
    {"q": "mở đèn phòng ngủ", "tier": 1, "intent": "CONTROL", "action": "ON", "device": "light_bedroom_01"},

    # --- Ngu canh phong (bot dat trong phong) ---
    {"q": "bật đèn", "room": "bedroom_1", "tier": 1, "intent": "CONTROL", "action": "ON", "device": "light_bedroom_01"},
    {"q": "bật đèn", "room": None, "tier": 1, "intent": "UNKNOWN"},  # nhieu den, khong ro phong -> hoi lai

    # --- Dat nhiet do (gioi han 16-30) ---
    {"q": "chỉnh điều hòa phòng ngủ 25 độ", "tier": 1, "intent": "CONTROL", "action": "SET", "device": "ac_bedroom_01", "temp": 25},
    {"q": "để máy lạnh 18 độ", "tier": 1, "intent": "CONTROL", "action": "SET", "device": "ac_bedroom_01", "temp": 18},
    {"q": "đặt điều hòa 10 độ", "tier": 1, "intent": "CONTROL", "action": "SET", "device": "ac_bedroom_01", "temp": 16},  # clamp

    # --- Lenh nhom ---
    {"q": "tắt hết đèn", "tier": 1, "intent": "GROUP", "action": "GROUP_OFF", "targets": 3},
    {"q": "bật hết đèn", "tier": 1, "intent": "GROUP", "action": "GROUP_ON", "targets": 3},
    {"q": "tắt hết thiết bị trong nhà", "tier": 1, "intent": "GROUP", "action": "GROUP_OFF", "targets": 6},

    # --- Scene ---
    {"q": "tôi đi ngủ đây", "tier": 1, "intent": "SCENE", "device": "ngu"},
    {"q": "xem phim", "tier": 1, "intent": "SCENE", "device": "xem_phim"},
    {"q": "chào buổi sáng", "tier": 1, "intent": "SCENE", "device": "sang_day"},
    {"q": "tôi về rồi", "tier": 1, "intent": "SCENE", "device": "ve_nha"},

    # --- Hoi trang thai ---
    {"q": "đèn phòng khách thế nào", "tier": 1, "intent": "QUERY", "action": "GET", "device": "light_living_01"},

    # --- Am luong ---
    {"q": "tăng âm lượng tivi", "tier": 1, "intent": "CONTROL", "action": "SET", "device": "tv_living_01"},

    # --- Can AI (Tier 2/3) — chi tham khao, khong assert ---
    {"q": "nóng quá", "tier": 3},
    {"q": "trong phòng hơi tối", "tier": 3},
    {"q": "tôi muốn xem chút phim trên tivi", "tier": 3},
]


def check(it, c):
    """Tra ve (ok, ly_do). Cau tier<=1 moi bi rang buoc; cau tier 3 chi tham khao."""
    if c["tier"] >= 3:
        return None, ""  # khong assert
    if it.tier is None or it.tier > 1:
        return False, f"giai o tier {it.tier}, ky vong <=1"
    if "intent" in c and it.intent != c["intent"]:
        return False, f"intent {it.intent} != {c['intent']}"
    if "action" in c and it.action != c["action"]:
        return False, f"action {it.action} != {c['action']}"
    if "device" in c and it.device_id != c["device"]:
        return False, f"device {it.device_id} != {c['device']}"
    if "temp" in c and it.parameters.get("temperature") != c["temp"]:
        return False, f"temp {it.parameters.get('temperature')} != {c['temp']}"
    if "targets" in c and (it.targets is None or len(it.targets) != c["targets"]):
        n = len(it.targets) if it.targets else 0
        return False, f"targets {n} != {c['targets']}"
    return True, ""


def main():
    registry = Registry.from_files(
        cfg.resolve_path("data.devices"),
        cfg.resolve_path("data.rooms"),
        cfg.resolve_path("data.scenes"))
    resolver = Resolver(cfg, registry)

    print(f"cache backend = {resolver.cache.backend} | embedding backend = {resolver.embed.backend}\n")
    passed = failed = skipped = 0
    for c in CASES:
        it = resolver.resolve(c["q"], c.get("room"))
        ok, why = check(it, c)
        tag = "TIER" + str(it.tier)
        room = f" [phong={c['room']}]" if c.get("room") else ""
        if ok is None:
            skipped += 1
            print(f"  ~  [{tag} {it.latency_ms:5.1f}ms]{room} {c['q']!r}")
            print(f"       -> ({it.intent}) {it.response_vi}")
        elif ok:
            passed += 1
            print(f"  OK [{tag} {it.latency_ms:5.1f}ms]{room} {c['q']!r} -> {it.intent}/{it.action} {it.device_id or ''}")
        else:
            failed += 1
            print(f"  XX [{tag} {it.latency_ms:5.1f}ms]{room} {c['q']!r}  ({why})")
            print(f"       -> ({it.intent}/{it.action}) {it.response_vi}")

    # Demo cache: hoi lai cau dau -> phai trung Tier 0.
    print("\n-- Kiem tra cache (Tier 0) --")
    q = CASES[0]["q"]
    it = resolver.resolve(q, CASES[0].get("room"))
    cache_ok = it.tier == 0
    print(f"  {'OK' if cache_ok else 'XX'} hoi lai {q!r} -> tier {it.tier} (ky vong 0)")
    if not cache_ok:
        failed += 1
    else:
        passed += 1

    print(f"\nKet qua: {passed} dat, {failed} loi, {skipped} bo qua (can AI).")
    print("Metrics:", resolver.metrics())
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
