"""Tier 3 — du phong bang LLM (Ollama) cho cau phuc tap/mo ho.

Bat model xuat JSON theo schema co dinh (xem SYSTEM_PROMPT). Phan tich JSON, kiem tra, gioi han
nhiet do 16-30 va am luong 0-100, ep confidence thap thanh UNKNOWN (hoi lai). Neu Ollama khong
chay/timeout: tra ve None de resolver tra cau xin loi nhe (giam cap muot ma).

response_vi do CHINH model sinh (giong quan gia, co dau).
"""
import json
from server.models.intent import Intent

# System prompt theo dung dac ta du an (co dau — day la chi thi cho model).
_SYSTEM_TEMPLATE = """Bạn là {name}, quản gia nhà thông minh người Việt. Bạn điều khiển các thiết bị thông qua lệnh JSON chính xác.

NHIỆM VỤ:
Phân tích lệnh của chủ nhà và trả về JSON hợp lệ duy nhất. Không giải thích. Không thêm văn bản.

CẤU TRÚC JSON ĐẦU RA:
{{
  "intent": "CONTROL|QUERY|GROUP|SCENE|UNKNOWN",
  "action": "ON|OFF|SET|GET|TOGGLE|GROUP_ON|GROUP_OFF",
  "device_type": "light|ac|fan|tv|sensor|group",
  "device_id": "device_id hoac null",
  "room": "room_id hoac null",
  "parameters": {{"key": "value"}},
  "response_vi": "cau tra loi tieng Viet ngan gon lich su",
  "confidence": 0.0
}}

THIẾT BỊ HIỆN CÓ:
{device_list}

NHÓM THIẾT BỊ:
{group_list}

QUY TẮC BẮT BUỘC:
- Chỉ xuất JSON thuần túy, không markdown, không giải thích
- response_vi phải lịch sự, xưng "tôi", gọi chủ nhân là "{addr}"
- Nếu lệnh mơ hồ: đặt intent="UNKNOWN", response_vi hỏi lại
- Nếu thiết bị không tồn tại: response_vi thông báo lịch sự
- confidence < 0.7: luôn đặt intent="UNKNOWN" và hỏi lại
- Nhiệt độ điều hòa: giới hạn 16-30 độ
- Âm lượng TV: giới hạn 0-100

VÍ DỤ:
Input: "bật đèn phòng khách"
Output: {{"intent":"CONTROL","action":"ON","device_type":"light","device_id":"light_living_01","room":"living_room","parameters":{{}},"response_vi":"Dạ, tôi sẽ bật đèn phòng khách ngay ạ.","confidence":0.98}}

Input: "mát quá"
Output: {{"intent":"UNKNOWN","action":null,"device_type":null,"device_id":null,"room":null,"parameters":{{}},"response_vi":"Dạ, {addr} muốn tôi bật quạt hay điều chỉnh điều hòa ạ?","confidence":0.3}}"""

# Cac khoa hop le cua schema -> loc bo khoa la model tu them.
_FIELDS = {"intent", "action", "device_type", "device_id", "room",
           "parameters", "response_vi", "confidence"}


def _extract_json(text):
    """Lay object JSON dau tien trong van ban (model doi khi boc markdown hoac them chu)."""
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except (json.JSONDecodeError, ValueError):
                    return None
    return None


class LlmTier:
    def __init__(self, cfg, registry):
        self.cfg = cfg
        self.reg = registry
        self.conf_min = float(cfg.get("intent.llm_confidence_min", 0.7))
        self.addr = cfg.get("butler.address_style", "ông/bà")
        self.name = cfg.get("butler.name", "Trợ Lý")

    def _system(self):
        return _SYSTEM_TEMPLATE.format(
            name=self.name, addr=self.addr,
            device_list=self.reg.device_list_text(),
            group_list=self.reg.group_list_text())

    def resolve(self, text, room=None):
        """Tra ve Intent, hoac None khi Ollama khong phan hoi duoc (timeout/khong chay)."""
        from server.core import llm_client
        user = text if not room else f"[Bot dat o phong: {room}] {text}"
        messages = [{"role": "system", "content": self._system()},
                    {"role": "user", "content": user}]
        try:
            resp = llm_client.chat(messages, stream=False)
            content = resp.choices[0].message.content or ""
        except Exception:
            return None     # Ollama down/timeout -> resolver xu ly nhe nhang

        data = _extract_json(content)
        if not isinstance(data, dict):
            return Intent(intent="UNKNOWN", confidence=0.3,
                          response_vi=f"Dạ, xin lỗi, {self.addr} có thể nói lại giúp tôi được không ạ?")
        clean = {k: v for k, v in data.items() if k in _FIELDS}
        clean = self._sanitize(clean)
        try:
            return Intent(**clean)
        except Exception:
            return Intent(intent="UNKNOWN", confidence=0.3,
                          response_vi=f"Dạ, xin lỗi, {self.addr} có thể nói lại giúp tôi được không ạ?")

    def _sanitize(self, d):
        """Gioi han gia tri va ep confidence thap thanh UNKNOWN."""
        params = d.get("parameters") or {}
        if not isinstance(params, dict):
            params = {}
        if "temperature" in params:
            try:
                params["temperature"] = max(16, min(30, int(params["temperature"])))
            except (TypeError, ValueError):
                params.pop("temperature", None)
        if "volume" in params:
            try:
                params["volume"] = max(0, min(100, int(params["volume"])))
            except (TypeError, ValueError):
                params.pop("volume", None)
        d["parameters"] = params
        try:
            conf = float(d.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        d["confidence"] = conf
        # Kiem tra device_id co that khong; neu model bia -> ha tin cay.
        did = d.get("device_id")
        if did and did not in self.reg.devices:
            d["device_id"] = None
            if d.get("intent") == "CONTROL":
                d["intent"] = "UNKNOWN"
                conf = min(conf, 0.5)
                d["confidence"] = conf
        if conf < self.conf_min and d.get("intent") != "SCENE":
            d["intent"] = "UNKNOWN"
            d["action"] = None
        if not d.get("response_vi"):
            d["response_vi"] = f"Dạ, {self.addr} muốn tôi làm gì giúp ạ?"
        return d
