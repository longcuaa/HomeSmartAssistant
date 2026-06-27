"""Tier 0 — cache khop tuyet doi.

Dung Redis neu ket noi duoc; neu khong, tu dong chuyen sang cache TRONG BO NHO (dict) de
server van chay khi chua dung Redis. Khoa = SHA256 cua van ban DA CHUAN HOA.

Cung giu bo dem so lan dung moi cau (phuc vu tu hoc: dung du nhieu lan -> thang tang).
"""
import json
import hashlib
import time
from server.core import text_norm as tn

try:
    import redis as _redis
except ImportError:
    _redis = None


def _key(normalized):
    return "hsa:intent:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _use_key(normalized):
    return "hsa:use:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class CacheTier:
    def __init__(self, cfg):
        self.ttl = int(cfg.get("redis.cache_ttl_days", 30)) * 86400
        self._mem = {}                 # fallback: normalized_key -> (json, het_han)
        self._uses = {}                # fallback: normalized_key -> count
        self.client = None
        url = cfg.get("redis.url")
        if _redis and url:
            try:
                c = _redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1)
                c.ping()
                self.client = c
            except Exception:
                self.client = None     # khong co Redis -> dung bo nho

    @property
    def backend(self):
        return "redis" if self.client else "memory"

    def _norm(self, text, room=None):
        # Gop NGU CANH PHONG vao khoa: 'bat den' o bot phong ngu khac bot phong khach.
        return tn.norm_device(text) + "|room=" + (room or "")

    def get(self, text, room=None):
        """Tra ve dict intent da luu, hoac None."""
        n = self._norm(text, room)
        if self.client:
            raw = self.client.get(_key(n))
            return json.loads(raw) if raw else None
        item = self._mem.get(_key(n))
        if not item:
            return None
        raw, exp = item
        if exp and exp < time.monotonic():
            self._mem.pop(_key(n), None)
            return None
        return json.loads(raw)

    def put(self, text, intent_dict, room=None):
        n = self._norm(text, room)
        raw = json.dumps(intent_dict, ensure_ascii=False)
        if self.client:
            self.client.setex(_key(n), self.ttl, raw)
        else:
            self._mem[_key(n)] = (raw, time.monotonic() + self.ttl)

    def bump_usage(self, text, room=None):
        """Tang so lan dung cau nay len 1 va tra ve so moi (de quyet dinh thang tang)."""
        n = self._norm(text, room)
        if self.client:
            c = self.client.incr(_use_key(n))
            self.client.expire(_use_key(n), self.ttl)
            return int(c)
        self._uses[_use_key(n)] = self._uses.get(_use_key(n), 0) + 1
        return self._uses[_use_key(n)]

    def clear(self):
        """Xoa toan bo cache intent (khong dong toi bo dem dung)."""
        if self.client:
            for k in self.client.scan_iter("hsa:intent:*"):
                self.client.delete(k)
        else:
            self._mem.clear()
