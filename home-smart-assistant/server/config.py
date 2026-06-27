"""Doc config.yaml mot lan, cho truy cap theo duong dan co cham ('models.llm.model').

Bi mat (token/key/url) co the ghi de bang bien moi truong de khong hard-code trong file.
"""
import os
import yaml

# Goc project = thu muc cha cua 'server/'. config.yaml nam o goc.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.getenv("HSA_CONFIG", os.path.join(_ROOT, "config.yaml"))

# (duong dan trong yaml, ten bien moi truong) -> cho phep ghi de luc chay.
_ENV_OVERRIDES = {
    "models.llm.base_url": "OLLAMA_BASE_URL",
    "models.llm.model": "LLM_MODEL",
    "models.tts.fpt_api_key": "FPT_API_KEY",
    "redis.url": "REDIS_URL",
    "mqtt.broker": "MQTT_BROKER",
    "mqtt.password": "MQTT_PASSWORD",
    "home_assistant.url": "HA_URL",
    "home_assistant.token": "HA_TOKEN",
}


class Config:
    """Bao quanh dict cau hinh, truy cap bang get('a.b.c', default)."""

    def __init__(self, data):
        self._data = data

    def get(self, path, default=None):
        cur = self._data
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def resolve_path(self, path, default=None):
        """Lay duong dan file tu config va doi thanh duong dan tuyet doi tu goc project."""
        val = self.get(path, default)
        if val and not os.path.isabs(val):
            return os.path.join(_ROOT, val)
        return val

    @property
    def root(self):
        return _ROOT


def _apply_env(data):
    for path, env in _ENV_OVERRIDES.items():
        val = os.getenv(env)
        if val is None:
            continue
        parts = path.split(".")
        cur = data
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = val
    return data


def load():
    """Doc va tra ve Config. Thieu file -> dict rong (van chay duoc bang gia tri mac dinh)."""
    data = {}
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    return Config(_apply_env(data))


# Mot ban dung chung cho ca tien trinh.
cfg = load()
