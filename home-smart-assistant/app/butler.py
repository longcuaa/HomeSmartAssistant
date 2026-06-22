"""Quan gia thong minh Home Smart Assistant.

Tro chuyen, goi y, dieu khien thiet bi bang tool calling, tra cuu tai lieu, va nho
so thich cua chu nha de ca nhan hoa goi y.

Hai che do:
- chat(): khong stream, dung cho API.
- chat_stream(): stream tung doan chu, dung cho dong lenh va san sang noi TTS sau nay.

Toi uu toc do: hoi xac nhan chi voi hanh dong he trong, con lenh dieu khien thi noi
thang ket qua khong ton them mot luot model.

Chay thu: python -m app.butler. Can model ho tro tool calling, vi du qwen3.
"""
import json
import re
import random
import hashlib
from datetime import datetime
import config
from app import llm, tools, memory

# Thu trong tuan bang tieng Viet ASCII, index theo datetime.weekday() (0 = thu hai).
_WEEKDAYS = ["Thu hai", "Thu ba", "Thu tu", "Thu nam", "Thu sau", "Thu bay", "Chu nhat"]

# Tinh cach (dau an rieng) viet co dau de model hieu va the hien dung giong. Day la chi thi cho
# model, khong phai chuoi hien cho nguoi dung, nen cho phep co dau.
SYSTEM_PROMPT = (
    "Bạn là quản gia AI RIÊNG của ngôi nhà này — thân thiện, ấm áp và CÓ CÁ TÍNH: trò chuyện tự nhiên, "
    "gần gũi như một người bạn đồng hành thật sự hiểu ý chủ nhân, đôi khi pha chút hóm hỉnh duyên dáng; "
    "không máy móc, không khách sáo cứng nhắc.\n"
    "QUY TẮC NGÔN NGỮ (BẮT BUỘC): chỉ trả lời bằng TIẾNG VIỆT. TUYỆT ĐỐI không dùng chữ Trung "
    "Quốc, Nhật, Hàn hay bất kỳ ngoại ngữ nào, kể cả một chữ.\n"
    "Chỉ điều khiển được đèn, quạt, điều hòa có trong nhà. Thiết bị khác (máy giặt, cửa, tivi...) "
    "thì nói thật là chưa điều khiển được, KHÔNG giả vờ đã làm. Không bịa thiết bị không có.\n"
    "Bạn hiểu rõ chủ nhân: người ngày đêm cày dự án AI và code, hay quên nghỉ ngơi và ăn uống thất thường. "
    "Dựa vào 'Sở thích đã biết' để chăm đúng ý và chủ động quan tâm (nhắc nghỉ, gợi ý cho dễ chịu) — nhẹ nhàng, không gò ép.\n"
    "Luôn trả lời NGẮN GỌN 1-3 câu, ấm áp và đúng trọng tâm; không bịa, không dài dòng. "
    "Lời chào hay trò chuyện thường ngày thì đáp NGAY, không gọi công cụ.\n"
    "Khi cần dữ liệu thật thì GỌI công cụ rồi trả lời theo kết quả (đừng chỉ nói ý định):\n"
    "- get_status: tình trạng thiết bị (bật/tắt, nhiệt độ) và chỉ số môi trường trong nhà.\n"
    "- search_knowledge: cách làm, khắc phục sự cố (mạng/router, thiết bị hỏng), kiến thức, tin tức.\n"
    "- get_weather: thời tiết ngoài trời. get_calendar / add_event: xem hoặc thêm lịch.\n"
    "- control_device: bật/tắt hoặc chỉnh nhiệt độ thiết bị.\n"
    "- remember: ghi nhớ khi chủ nhân BÀY TỎ sở thích/thói quen ('tôi thích...', 'nhớ giúp tôi...'); "
    "đừng nhầm với ra lệnh ('bật...', 'tắt...').\n"
    "Khi nói về thiết bị/trạng thái: chỉ nêu ĐÚNG dữ liệu get_status trả về — KHÔNG bịa thêm thiết bị, "
    "không tự đổi bật/tắt.\n"
    "Câu kiến thức chung không liên quan ngôi nhà thì trả lời thẳng, không gọi công cụ. Khi hợp lý, "
    "chủ động quan tâm chủ nhân (nhắc nghỉ ngơi, đi ngủ sớm, gợi ý bật quạt khi nóng) bằng giọng ấm áp, thân thiện."
)

MAX_STEPS = 5
# Lenh dieu khien tra ve cau xac nhan san, noi thang duoc, khong can model dien dat lai.
# Cong cu co ket qua ĐÃ la cau tra loi tu nhien -> tra thang, bo luot goi model thu 2
# (nhanh gap doi cho cau hoi do, va tranh model nho dien dat sai du lieu).
DIRECT_REPLY_TOOLS = {"control_device", "get_calendar", "get_weather", "get_status"}

# Model bat che do suy nghi (vi du qwen3) sinh ra khoi <think>...</think>. Quan gia khong duoc
# noi phan suy nghi noi bo ra cho chu nha, nen ta loc bo truoc khi tra ve.
_THINK_OPEN, _THINK_CLOSE = "<think>", "</think>"
_THINK_RE = re.compile(re.escape(_THINK_OPEN) + r".*?" + re.escape(_THINK_CLOSE), re.S)


def _strip_think(text):
    """Bo het khoi suy nghi khoi mot chuoi hoan chinh (dung cho ban khong stream)."""
    text = _THINK_RE.sub("", text or "")
    # Bo ca khoi <think> CHUA dong (model suy nghi dai bi cat ngang vi het token).
    i = text.find(_THINK_OPEN)
    if i != -1:
        text = text[:i]
    return text.strip()


class _ThinkFilter:
    """Loc khoi <think>...</think> ra khoi luong token stream, xu ly ca khi the bi cat ngang chunk.

    feed(text) tra ve phan van ban an toan de hien ngay; phan co the la dau the bi cat duoc giu lai
    cho lan sau. flush() goi cuoi moi luot de phat not phan con lai (neu khong dang trong think).
    """

    def __init__(self):
        self.in_think = False
        self.pending = ""

    def feed(self, text):
        self.pending += text
        out = []
        while self.pending:
            if self.in_think:
                i = self.pending.find(_THINK_CLOSE)
                if i == -1:
                    # Chua thay the dong: bo phan suy nghi, chi giu lai duoi cung phong khi the bi cat.
                    keep = len(_THINK_CLOSE) - 1
                    self.pending = self.pending[-keep:] if len(self.pending) > keep else self.pending
                    break
                self.pending = self.pending[i + len(_THINK_CLOSE):]
                self.in_think = False
            else:
                i = self.pending.find(_THINK_OPEN)
                if i == -1:
                    keep = len(_THINK_OPEN) - 1
                    if len(self.pending) > keep:
                        out.append(self.pending[:-keep])
                        self.pending = self.pending[-keep:]
                    break
                out.append(self.pending[:i])
                self.pending = self.pending[i + len(_THINK_OPEN):]
                self.in_think = True
        return "".join(out)

    def flush(self):
        tail = "" if self.in_think else self.pending
        self.pending = ""
        return tail


def _now_text():
    """Thoi gian hien tai dang 'Thu X, ngay dd/mm/yyyy, HH:MM'."""
    n = datetime.now()
    return f"{_WEEKDAYS[n.weekday()]}, ngay {n:%d/%m/%Y}, {n:%H:%M}"


def _system():
    """Phan system TINH (khong doi giua cac luot) de model cache lai prefix, prefill nhanh hon.

    Thoi gian va so thich (thay doi theo luot) khong de o day ma chen sat cau hoi (_runtime_context).
    """
    prompt = SYSTEM_PROMPT
    if not config.ENABLE_THINKING:
        prompt += " /no_think"  # tat suy nghi cua qwen3 de tra loi nhanh hon
    return prompt


def _runtime_context():
    """Ngu canh thay doi theo luot: thoi gian thuc + so thich da biet. Dat sat cau hoi de phan
    dau (system + tools) on dinh, giup model tai su dung cache va prefill nhanh hon."""
    text = f"Bay gio la {_now_text()}."
    prefs = memory.as_text()
    if prefs:
        text += f" So thich da biet cua chu nha: {prefs}. Hay luu y khi tra loi va goi y."
    return text


def _build_messages(user_message, history):
    """Ghep messages: system tinh o dau, lich su, roi ngu canh dong ngay truoc cau hoi."""
    return (
        [{"role": "system", "content": _system()}]
        + (history or [])
        + [{"role": "system", "content": _runtime_context()},
           {"role": "user", "content": user_message}]
    )


def _history_after(history, user_message, reply):
    return history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": reply},
    ]


def _knowledge_intent(message):
    """Cau hoi kien thuc / su co (cach lam, khac phuc, tai sao, tin tuc...) -> bat buoc dung RAG."""
    return bool(_KNOWLEDGE_RE.search(tools._norm(message)))


def _rag_context_messages(user_message, history):
    """Tra cuu tai lieu TRUOC, chen ket qua vao ngu canh roi de model chi viec DIEN DAT (goi
    KHONG kem tools de model khoi chon nham tool). Bao dam cau kien thuc/su co luon dung tai lieu."""
    rag = tools.search_knowledge(user_message)
    base = _build_messages(user_message, history)
    base.insert(-1, {"role": "system",
                     "content": "Thong tin tra cuu tu tai lieu trong nha (dung de tra loi; neu "
                                "khong lien quan thi noi chua co thong tin, KHONG bia):\n" + rag})
    return base


# --- Cache cau tra loi: cung 1 cau hoi + du lieu KHONG doi -> tra ngay, khong goi model.
# Chu ky (signature) gom HOME + SENSORS + bo nho + phut hien tai: bat ky thay doi nao cung lam
# cache het hieu luc (vi du bat/tat thiet bi doi HOME; sang phut moi cho cau hoi gio/thoi tiet).
_RESP_CACHE = {}
_RESP_CACHE_MAX = 256
# Cong cu LAM DOI trang thai -> khong cache de lenh luon thuc thi that.
_STATE_TOOLS = {"control_device", "remember"}


def _state_signature():
    blob = json.dumps([tools.HOME, tools.SENSORS, memory.load(),
                       datetime.now().strftime("%Y%m%d%H%M")],
                      ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()


def _cache_get(message):
    hit = _RESP_CACHE.get((message or "").strip().lower())
    return hit[1] if hit and hit[0] == _state_signature() else None


def _cache_put(message, reply, used_tools):
    key = (message or "").strip().lower()
    if not key or not reply or (used_tools & _STATE_TOOLS):
        return  # cau rong, tra loi rong, hoac lenh doi trang thai thi khong cache
    _RESP_CACHE[key] = (_state_signature(), reply)
    if len(_RESP_CACHE) > _RESP_CACHE_MAX:
        _RESP_CACHE.pop(next(iter(_RESP_CACHE)))  # bo muc cu nhat


# --- Duong tat (fast-path): y dinh thiet bi RO RANG -> tra loi TUC THI, KHONG goi LLM.
# Du lieu thiet bi nam san trong HOME nen khong can model -> phan hoi gan nhu 0ms cho voice.
_ON_RE = re.compile(r"\b(bat|mo|khoi dong)\b")
_OFF_RE = re.compile(r"\b(tat|ngat)\b")
_STATUS_RE = re.compile(r"(thiet bi gi|bao nhieu thiet bi|co thiet bi|nhung thiet bi|"
                        r"liet ke thiet bi|trang thai thiet bi|trang thai nha|trang thai trong nha)")
_ENV_RE = re.compile(r"(nhiet do trong nha|do am trong nha|khong khi trong nha|"
                     r"do sang trong nha|chi so moi truong)")

# Hoi nhiet do cua dieu hoa ('phong ngu de bao nhieu do', 'dieu hoa may do').
_ASK_TEMP_RE = re.compile(r"bao nhieu do|may do|de bao nhieu")
# Hoi trang thai bat/tat cua MOT thiet bi cu the (khong phai dem so).
_DEV_STATUS_RE = re.compile(r"bat hay tat|tat hay bat|dang (bat|tat|sang|chay|hoat dong)|"
                            r"co (dang )?(bat|sang|chay)|sang khong|the nao")
# Hoi thoi tiet ngoai troi -> goi get_weather thang (tranh model chon nham tool).
_WEATHER_RE = re.compile(r"thoi tiet|ngoai troi|co mua|troi mua|du bao|"
                         r"nong khong|lanh khong|mang ao mua|mang du|troi the nao")
# Bat/tat TOAN BO (he trong) -> phai hoi xac nhan ro pham vi.
_ALL_ON_RE = re.compile(r"\b(bat|mo)\b.*(het|tat ca|toan bo|moi thu)|"
                        r"(tat ca|toan bo|moi thu)\b.*\b(bat|mo)\b")
_ALL_OFF_RE = re.compile(r"tat (het|sach|toan bo|tat ca|moi thu)|"
                         r"(het|toan bo|moi thu)\b.*\btat\b")
# Cau hoi KIEN THUC / SU CO -> bat buoc tra cuu tai lieu (search_knowledge), khong de model
# tu bia hoac chon nham tool (loi tung gap: wifi -> get_status, tin tuc -> get_weather).
_KNOWLEDGE_RE = re.compile(
    r"lam sao|lam the nao|cach (nao|de|reset|khac|sua|xu|lam|kiem|cai|ket|tang|giam)|khac phuc|"
    r"xu ly the nao|xu ly nhu the nao|tai sao|vi sao|nguyen nhan|do dau|la do|"
    r"tin tuc|huong dan|bi treo|bi hong|bi loi|bi nhap nhay|bi cham|cham qua|reset|"
    r"khong vao duoc|khong ket noi|mat mang|mat wifi")

# Chu nha BAY TO so thich/thoi quen -> de LLM + cong cu remember xu ly (KHONG coi la lenh thiet bi).
_PREF_RE = re.compile(r"toi thich|toi khong thich|toi thuong|toi hay|nho giup|nho gium|nho la|"
                      r"lan sau|tu gio|tu nay|moi khi|moi lan")

# Chu Trung/Nhat/Han (CJK). Model 7B doi khi chen tieng nuoc ngoai -> ta cat bo.
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯＀-￯]")


def _strip_foreign(text):
    """Cat bo phan chu Trung/Nhat/Han (model doi khi chen) -> giu lai phan tieng Viet o truoc.

    Vi du 'Ban co muon de ngu dễ入睡吗？...' -> 'Ban co muon de ngu de'. Neu CA cau la chu
    nuoc ngoai thi tra ve chuoi rong (caller se dung cau xin loi mac dinh)."""
    if not text:
        return text
    mt = _CJK_RE.search(text)
    if mt:
        text = text[:mt.start()]
    return text.strip(" \n，,。．、；;:-")

# --- Cau hoi ngay/thu/gio -> tra ngay tu dong ho he thong (KHONG goi LLM).
# Phai xet TRUOC nhanh dem so vi 'thu may'/'ngay bao nhieu' chua tu khoa 'may'/'bao nhieu',
# neu khong cau hoi ngay/gio se bi hieu nham la 'dem thiet bi' -> tra ve danh sach thiet bi.
_ASK_TIME_RE = re.compile(r"\b(may gio|gio roi)\b")
_ASK_WEEKDAY_RE = re.compile(r"\b(thu may|thu gi)\b")
_ASK_DATE_RE = re.compile(r"\b(ngay may|ngay bao nhieu|ngay gi)\b|hom nay la ngay")
# Thu trong tuan CO DAU de noi/hien cho chu nha (khac _WEEKDAYS ASCII danh cho prompt model).
_WEEKDAYS_VN = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]

# --- Tro chuyen xa giao + cau hoi nang luc/danh tinh -> tra ngay (KHONG goi LLM) cho nhanh.
# Day la nhung cau lap lai nhieu nhat; tra san giup cau dau tien ~0s thay vi cho prefill LLM.
# Tra loi van am ap, co cha chut quan tam de giu dung giong quan gia.
_GREET_RE = re.compile(r"^(xin chao|chao ban|chao buoi (sang|trua|chieu|toi)|chao|hello|hi|hey|alo)\b")
_THANKS_RE = re.compile(r"^(cam on|cang on|thank|thanks|thank you)\b")
_BYE_RE = re.compile(r"^(tam biet|hen gap lai|bye|goodbye|chao tam biet|di ngu day)\b")
_CAPABILITY_RE = re.compile(r"ban (co the )?lam (duoc )?(gi|nhung gi)|ban giup (duoc )?(gi|nhung gi)|"
                            r"ban biet (lam )?gi|ban co (nhung )?chuc nang gi|giup toi (duoc )?gi")
_WHOAMI_RE = re.compile(r"\bban la ai\b|gioi thieu (ve )?ban than|\bban ten (la )?gi\b")

_GREET_REPLIES = [
    "Chào bạn! Hôm nay bạn thế nào? Cần tôi giúp gì cho ngôi nhà không?",
    "Chào bạn! Tôi luôn ở đây, bạn cần gì cứ nói nhé.",
    "Chào bạn! Nhớ nghỉ ngơi và uống đủ nước giữa lúc làm việc nhé. Tôi giúp được gì cho bạn?",
]
_THANKS_REPLIES = ["Không có gì đâu, tôi luôn sẵn lòng!", "Rất vui được giúp bạn. Cần gì cứ gọi tôi nhé!"]
_BYE_REPLIES = ["Tạm biệt bạn, nhớ giữ sức khỏe nhé!", "Hẹn gặp lại! Bạn nghỉ ngơi cho khỏe nhé."]
_CAP_REPLY = ("Tôi có thể bật/tắt và chỉnh nhiệt độ đèn, quạt, điều hòa; cho biết tình trạng thiết bị "
              "và môi trường trong nhà; xem thời tiết, lịch và nhắc lịch; tra cứu tài liệu, tin tức; "
              "và ghi nhớ sở thích của bạn. Bạn cần tôi giúp gì nào?")
_WHOAMI_REPLY = ("Tôi là quản gia AI của ngôi nhà, luôn sẵn sàng chăm lo nhà cửa và đồng hành cùng bạn. "
                 "Bạn cần gì cứ nói nhé!")


# Tu xac nhan / tu choi (da bo dau). Tranh 'dung' vi 'dung'(dung roi) lan 'dung'(dung lam).
_CONFIRM_RE = re.compile(r"\b(co|u|um|uh|ok|oke|okay|vang|chuan|dong y|duoc|dung roi)\b")
_DENY_RE = re.compile(r"\b(khong|thoi|khoi|huy|khoan)\b")
# Trang thai cho xac nhan (CLI 1 nguoi dung). API nhieu phien thi can tach theo phien.
# action: 'on' | 'off' | ('temp', do) | ('all', 'on'/'off'). scope: danh sach thiet bi cho lenh 'all'.
_PENDING = {"action": None, "device": None, "candidates": None, "scope": None}


def _clear_pending():
    _PENDING.update(action=None, device=None, candidates=None, scope=None)


def _match_devices(words):
    """Cac thiet bi khop voi tu nguoi dung noi (bo 'phong'); tat ca tu da noi nam trong ten."""
    keyw = {k: set(w for w in tools._norm(k).split() if w != "phong") for k in tools.HOME}
    all_dev = set().union(*keyw.values()) if keyw else set()
    said = words & all_dev
    if not said:
        return []
    return [k for k, kw in keyw.items() if said <= kw]


def _confirm_phrase(act, device):
    """Cau hoi xac nhan cho mot lenh (bat/tat/dat nhiet do) tren 1 thiet bi."""
    if isinstance(act, tuple) and act[0] == "temp":
        t = act[1]
        warn = " Nhiet do nay hoi cuc doan, ban chac chu?" if (t < 18 or t > 30) else ""
        return f"Bạn có chắc muốn đặt {device} ở {t} độ không?{warn}"
    verb = "bật" if act == "on" else "tắt"
    return f"Bạn có chắc muốn {verb} {device} không?"


def _choose_phrase(act, devices):
    """Cau hoi chon thiet bi khi lenh con mo ho (nhieu thiet bi khop)."""
    if isinstance(act, tuple) and act[0] == "temp":
        return f"Bạn muốn đặt thiết bị nào ở {act[1]} độ: {', '.join(devices)}?"
    verb = "bật" if act == "on" else "tắt"
    return f"Bạn muốn {verb} thiết bị nào: {', '.join(devices)}?"


def _apply_action(act, device, scope=None):
    """Thuc thi lenh sau khi chu nha xac nhan. Tra ve cau ket qua de noi thang."""
    if isinstance(act, tuple) and act[0] == "all":      # bat/tat toan bo
        sub = act[1]
        targets = scope or list(tools.HOME)
        for k in targets:
            tools.control_device(k, sub)
        verb = "bật" if sub == "on" else "tắt"
        return f"Đã {verb} toàn bộ {len(targets)} thiết bị."
    if isinstance(act, tuple) and act[0] == "temp":     # dat nhiet do
        return tools.control_device(device, temperature=act[1])
    return tools.control_device(device, act)            # bat/tat 1 thiet bi


def _devices_status_text(devices):
    """Trang thai bat/tat (kem nhiet do neu co) cua mot so thiet bi cu the."""
    parts = []
    for k in devices:
        st = tools.HOME.get(k)
        if isinstance(st, dict):
            s = "đang bật" if st.get("on") else "đang tắt"
            if "temp" in st:
                s += f", {st['temp']} độ"
        else:
            s = str(st)
        parts.append(f"{k} {s}")
    return "; ".join(parts) + "."


def _fast_path(message):
    """Tra loi tuc thi (KHONG goi LLM) cho y dinh thiet bi. Tra None -> de LLM xu ly.

    Lenh bat/tat LUON hoi xac nhan truoc khi lam:
    - Ro rang 1 thiet bi -> 'Ban co chac muon bat/tat X khong?' -> 'co' moi lam.
    - Mo ho nhieu thiet bi -> 'Ban muon ... thiet bi nao: ...?' -> chon ten -> lam.
    """
    m = tools._norm(message)
    if not m:
        return None
    # Tach tu BO dau cau (vd 'den?' -> 'den') de khop ten thiet bi du nguoi dung co go '?,.!'.
    words = set(re.findall(r"[a-z0-9]+", m))

    # 1) Dang cho phan hoi cho mot lenh truoc do?
    if _PENDING["action"]:
        act = _PENDING["action"]
        if _PENDING["candidates"]:                       # cho chon thiet bi (lenh mo ho)
            matched = [k for k in _PENDING["candidates"] if k in set(_match_devices(words))]
            if len(matched) == 1:                        # da ro -> hoi xac nhan lan cuoi
                _PENDING.update(action=act, device=matched[0], candidates=None)
                return _confirm_phrase(act, matched[0])
            if matched:                                  # van con nhieu -> hoi lai trong so do
                _PENDING["candidates"] = matched
                return _choose_phrase(act, matched)
        else:                                            # cho xac nhan co/khong
            if _DENY_RE.search(m):
                _clear_pending()
                return "Đã hủy, không thực hiện."
            if _CONFIRM_RE.search(m):
                dev, scope = _PENDING["device"], _PENDING["scope"]
                _clear_pending()
                return _apply_action(act, dev, scope)
        _clear_pending()                                 # noi gi khac -> bo cho, xu ly nhu lenh moi

    # 1b) Cau kien thuc/su co hoac cau BAY TO so thich -> tra None de chat() dung RAG / remember,
    # tranh fast-path bat nham (vd 'xu ly the nao' thanh trang thai, 'toi thich 26 do' thanh lenh).
    if _KNOWLEDGE_RE.search(m) or _PREF_RE.search(m):
        return None

    # 2) CAU HOI ngay/thu/gio -> tra ngay tu dong ho he thong (KHONG goi LLM).
    # Dat TRUOC nhanh dem so vi 'thu may'/'ngay bao nhieu' chua tu khoa 'may'/'bao nhieu'.
    now = datetime.now()
    if _ASK_TIME_RE.search(m):
        return f"Bây giờ là {now:%H:%M}."
    if _ASK_WEEKDAY_RE.search(m) or _ASK_DATE_RE.search(m):
        return f"Hôm nay là {_WEEKDAYS_VN[now.weekday()]}, ngày {now:%d/%m/%Y}."

    # 3) Tro chuyen xa giao + cau hoi nang luc/danh tinh -> tra san, KHONG goi LLM (nhanh ~0s).
    if _GREET_RE.search(m):
        return random.choice(_GREET_REPLIES)
    if _THANKS_RE.search(m):
        return random.choice(_THANKS_REPLIES)
    if _BYE_RE.search(m):
        return random.choice(_BYE_REPLIES)
    if _CAPABILITY_RE.search(m):
        return _CAP_REPLY
    if _WHOAMI_RE.search(m):
        return _WHOAMI_REPLY

    # 4) CAU HOI ve moi truong / trang thai / so luong thiet bi.
    # Chi coi la cau hoi thiet bi khi co NHAC den thiet bi (ten thiet bi hoac chu 'thiet bi'),
    # de 'bao nhieu'/'may' o cau khac (2+2=may?, gia bitcoin bao nhieu?) khong bi nham la dem thiet bi.
    if _ENV_RE.search(m):                               # 'nhiet do trong nha' -> chi so moi truong
        return tools.get_environment()

    cands = _match_devices(words)
    mentions_device = bool(cands) or "thiet bi" in m
    asking_count = bool(re.search(r"\b(may|bao nhieu)\b", m))

    # 4a) Hoi nhiet do dieu hoa cua phong/thiet bi cu the ('phong ngu de bao nhieu do?').
    if _ASK_TEMP_RE.search(m) and cands:
        acs = [k for k in cands if isinstance(tools.HOME[k], dict) and "temp" in tools.HOME[k]]
        if acs:
            parts = [f"{k} đang đặt {tools.HOME[k]['temp']} độ"
                     + ("" if tools.HOME[k].get("on") else " (đang tắt)") for k in acs]
            return "; ".join(parts) + "."

    # 4b) Hoi trang thai bat/tat cua thiet bi cu the (KHONG phai cau dem) -> tra trang thai that.
    if cands and not asking_count and _DEV_STATUS_RE.search(m):
        return _devices_status_text(cands)

    # 4c) Dem / liet ke thiet bi: CHI khi co nhac den thiet bi.
    asking_on = "dang bat" in m
    asking_off = "dang tat" in m
    if (asking_count or asking_on or asking_off) and mentions_device:
        pool = cands if cands else list(tools.HOME)
        if asking_on:                              # 'may cai den dang bat' -> dem cai DANG BAT
            lst = [k for k in pool if isinstance(tools.HOME[k], dict) and tools.HOME[k].get("on")]
            return f"Có {len(lst)} thiết bị đang bật" + (f": {', '.join(lst)}." if lst else ".")
        if asking_off:
            lst = [k for k in pool if not (isinstance(tools.HOME[k], dict) and tools.HOME[k].get("on"))]
            return f"Có {len(lst)} thiết bị đang tắt" + (f": {', '.join(lst)}." if lst else ".")
        if cands:                                  # 'may dieu hoa', 'bao nhieu den' -> dem theo loai
            return f"Trong nhà có {len(cands)} thiết bị: {', '.join(cands)}."
        return tools.get_status()                  # 'bao nhieu thiet bi' chung chung

    if _STATUS_RE.search(m):
        return tools.get_status()

    # 5) Thoi tiet ngoai troi -> goi get_weather thang (tranh model chon nham tool).
    if _WEATHER_RE.search(m):
        return tools.get_weather()

    # 6) LENH dieu khien -> hoi xac nhan truoc khi lam.
    num_m = re.search(r"\b(\d{1,2})\b", m)
    # 6a) Bat/tat TOAN BO (he trong): hoi xac nhan ro pham vi truoc khi lam.
    all_on, all_off = bool(_ALL_ON_RE.search(m)), bool(_ALL_OFF_RE.search(m))
    if (all_on ^ all_off) and not num_m:
        sub = "on" if all_on else "off"
        verb = "bật" if all_on else "tắt"
        scope = cands if cands else list(tools.HOME)   # 'tat het den' -> chi cac den
        _PENDING.update(action=("all", sub), device=None, candidates=None, scope=scope)
        return f"Bạn có chắc muốn {verb} toàn bộ {len(scope)} thiết bị không?"

    # 6b) Dat nhiet do dieu hoa: co so do + thiet bi co 'temp'.
    if num_m and cands:
        acs = [k for k in cands if isinstance(tools.HOME[k], dict) and "temp" in tools.HOME[k]]
        if acs:
            act = ("temp", int(num_m.group(1)))
            if len(acs) == 1:
                _PENDING.update(action=act, device=acs[0], candidates=None, scope=None)
                return _confirm_phrase(act, acs[0])
            _PENDING.update(action=act, device=None, candidates=acs, scope=None)
            return _choose_phrase(act, acs)

    # 6c) Bat/tat 1 thiet bi (khong co so).
    on, off = bool(_ON_RE.search(m)), bool(_OFF_RE.search(m))
    if (on ^ off) and not num_m:
        act = "on" if on else "off"
        if len(cands) == 1:
            _PENDING.update(action=act, device=cands[0], candidates=None, scope=None)
            return _confirm_phrase(act, cands[0])
        if len(cands) > 1:
            _PENDING.update(action=act, device=None, candidates=cands, scope=None)
            return _choose_phrase(act, cands)
    return None


def _stream_pieces(text):
    """Cat chuoi CO SAN (vd ket qua cong cu tra thang) thanh tung tu de stream ra dan,
    cho cam giac real-time thay vi hien nguyen cuc mot lan."""
    buf = ""
    for ch in text:
        buf += ch
        if ch in " \n":
            yield buf
            buf = ""
    if buf:
        yield buf


# Dau ket cau de tach cau cho TTS (gom ca ';' de doc danh sach thiet bi ngat tung muc).
_SENT_END_RE = re.compile(r"[.!?;\n]+")


def stream_sentences(pieces):
    """Gom luong token (tu chat_stream) thanh tung CAU hoan chinh roi yield ngay.

    Dung cho text-to-speech: TTS doc cau dau ngay khi xong, trong khi model con dang sinh cau
    sau -> 'tieng noi dau tien' phat ra som nhat. Vi du:
        for cau in butler.stream_sentences(butler.chat_stream(q, history)):
            tts_noi(cau)
    """
    buf = ""
    for p in pieces:
        buf += p
        while True:
            m = _SENT_END_RE.search(buf)
            if not m:
                break
            sent = buf[:m.end()].strip()
            buf = buf[m.end():]
            if sent:
                yield sent
    if buf.strip():
        yield buf.strip()


def chat(user_message, history=None):
    """Mot luot, khong stream. Tra ve (cau_tra_loi, lich_su_moi). Dung cho API."""
    history = history or []
    cached = _cache_get(user_message)
    if cached is not None:
        return cached, _history_after(history, user_message, cached)  # du lieu khong doi -> tra ngay
    fast = _fast_path(user_message)
    if fast is not None:
        return fast, _history_after(history, user_message, fast)  # y dinh ro rang -> tra ngay, khong goi LLM
    if _knowledge_intent(user_message):
        # Cau kien thuc/su co: tra cuu tai lieu roi de model dien dat (1 luot, khong chon nham tool).
        messages = _rag_context_messages(user_message, history)
        try:
            msg = llm.chat(messages, tools=None).choices[0].message
        except Exception:
            return "Xin lỗi, hệ thống đang phản hồi chậm, anh chị thử lại sau giây lát.", history
        reply = _strip_foreign(_strip_think(msg.content)) or "Xin lỗi, tôi chưa tìm thấy thông tin phù hợp trong tài liệu."
        _cache_put(user_message, reply, {"search_knowledge"})
        return reply, _history_after(history, user_message, reply)
    messages = _build_messages(user_message, history)
    used = set()

    for step in range(MAX_STEPS):
        # Chi gui tools o luot DAU (de model chon cong cu). Cac luot sau chi dien dat tu ket qua
        # cong cu -> bo tools cho prefill nhe hon, nhanh hon (nhat la duong search_knowledge 2 luot).
        use_tools = tools.TOOLS if step == 0 else None
        try:
            msg = llm.chat(messages, tools=use_tools).choices[0].message
        except Exception:
            return "Xin lỗi, hệ thống đang phản hồi chậm, anh chị thử lại sau giây lát.", history

        if not msg.tool_calls:
            reply = _strip_foreign(_strip_think(msg.content))
            if not reply:
                # Model chi sinh phan suy nghi (bi cat vi het token) ma chua kip tra loi.
                reply = "Xin lỗi, anh chị hỏi lại giúp tôi được không ạ?"
            _cache_put(user_message, reply, used)
            return reply, _history_after(history, user_message, reply)

        messages.append({
            "role": "assistant",
            "content": _strip_think(msg.content),
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
        })
        results = []
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            used.add(tc.function.name)
            result = tools.execute(tc.function.name, args)
            results.append((tc.function.name, result))
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        if results and all(name in DIRECT_REPLY_TOOLS for name, _ in results):
            reply = " ".join(r for _, r in results)
            _cache_put(user_message, reply, used)
            return reply, _history_after(history, user_message, reply)

    return "Xin lỗi, tôi chưa xử lý được yêu cầu này.", history


def chat_stream(user_message, history=None):
    """Mot luot, stream tung doan chu. Yield cac chuoi. Caller tu gom de luu lich su."""
    history = history or []
    cached = _cache_get(user_message)
    if cached is not None:
        for piece in _stream_pieces(cached):
            yield piece  # du lieu khong doi -> tra cache ngay, van stream tung tu cho dong nhat
        return
    fast = _fast_path(user_message)
    if fast is not None:
        for piece in _stream_pieces(fast):
            yield piece  # y dinh ro rang -> tra ngay, khong goi LLM
        return
    if _knowledge_intent(user_message):
        # Cau kien thuc/su co: tra cuu tai lieu roi de model dien dat (khong chon nham tool).
        kmsgs = _rag_context_messages(user_message, history)
        kans = []
        tf = _ThinkFilter()
        try:
            for chunk in llm.chat(kmsgs, tools=None, stream=True):
                vis = tf.feed(getattr(chunk.choices[0].delta, "content", None) or "")
                clean = _strip_foreign(vis)
                if clean:
                    kans.append(clean)
                    yield clean
        except Exception:
            yield "Xin lỗi, hệ thống đang phản hồi chậm, anh chị thử lại sau giây lát."
            return
        tail = _strip_foreign(tf.flush())
        if tail:
            kans.append(tail)
            yield tail
        if kans:
            _cache_put(user_message, "".join(kans), {"search_knowledge"})
        else:
            yield "Xin lỗi, tôi chưa tìm thấy thông tin phù hợp trong tài liệu."
        return
    messages = _build_messages(user_message, history)
    used = set()
    answer = []  # gom van ban tra loi cuoi de cache lai

    for step in range(MAX_STEPS):
        use_tools = tools.TOOLS if step == 0 else None  # tools chi o luot dau -> luot sau prefill nhe
        content_parts = []
        calls = {}
        tf = _ThinkFilter()
        produced = False  # da phat duoc chu nao cho chu nha chua (de khong im lang hoan toan)
        try:
            for chunk in llm.chat(messages, tools=use_tools, stream=True):
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    content_parts.append(delta.content)
                    visible = _strip_foreign(tf.feed(delta.content))
                    if visible:
                        produced = True
                        answer.append(visible)
                        yield visible
                for tcd in (delta.tool_calls or []):
                    idx = tcd.index if tcd.index is not None else 0
                    e = calls.setdefault(idx, {"id": None, "name": "", "args": ""})
                    if tcd.id:
                        e["id"] = tcd.id
                    if tcd.function and tcd.function.name:
                        e["name"] += tcd.function.name
                    if tcd.function and tcd.function.arguments:
                        e["args"] += tcd.function.arguments
        except Exception:
            yield "Xin lỗi, hệ thống đang phản hồi chậm, anh chị thử lại sau giây lát."
            return

        tail = _strip_foreign(tf.flush())
        if tail:
            produced = True
            answer.append(tail)
            yield tail

        if not calls:
            if not produced:
                # Model chi sinh phan suy nghi (bi cat vi het token) ma chua kip tra loi.
                yield "Xin lỗi, anh chị hỏi lại giúp tôi được không ạ?"
            else:
                _cache_put(user_message, "".join(answer), used)
            return  # da stream xong cau tra loi cuoi

        payload = []
        for i, c in enumerate(calls.values()):
            c["id"] = c["id"] or f"call_{i}"
            payload.append({"id": c["id"], "type": "function",
                            "function": {"name": c["name"], "arguments": c["args"] or "{}"}})
        messages.append({"role": "assistant", "content": _strip_think("".join(content_parts)), "tool_calls": payload})

        results = []
        for c in calls.values():
            try:
                args = json.loads(c["args"] or "{}")
            except json.JSONDecodeError:
                args = {}
            used.add(c["name"])
            result = tools.execute(c["name"], args)
            results.append((c["name"], result))
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})

        if results and all(name in DIRECT_REPLY_TOOLS for name, _ in results):
            reply = " ".join(r for _, r in results)
            _cache_put(user_message, reply, used)
            for piece in _stream_pieces(reply):
                yield piece  # stream tung tu de hien dan, khong hien nguyen cuc
            return
        # nguoc lai: vong sau se stream cau tra loi dien dat tu ket qua cong cu

    yield "Xin lỗi, tôi chưa xử lý được yêu cầu này."


def warm_up():
    """Lam nong luc khoi dong: goi MOT luot that (du system + tools) de Ollama vua nap model VUA
    cache san prefix [system + tools]. Nho vay cau hoi DAU TIEN cua nguoi dung khong ton ~5s
    prefill prompt lon tren GPU yeu. Khong bao gio nem loi."""
    try:
        llm.chat(_build_messages("xin chao", []), tools=tools.TOOLS)
    except Exception:
        pass
    try:
        llm.embed("xin chao")  # nap luon model embedding cho search_knowledge dau tien
    except Exception:
        pass
    try:
        tools.get_status()  # cham broker MQTT 1 lan (cache che do gia lap) -> lenh thiet bi dau khong tre
    except Exception:
        pass


def main():
    print("Dang khoi dong, nap model va lam nong prompt...", flush=True)
    warm_up()  # nap model + cache prefix de cau hoi dau tien khong bi tre
    print("Quan gia Home Smart Assistant. Go 'exit' de thoat.\n")
    history = []
    while True:
        q = input("Chu nha: ").strip()
        if q.lower() in ("exit", "quit", "thoat"):
            break
        if not q:
            continue
        print("Quan gia: ", end="", flush=True)
        parts = []
        for piece in chat_stream(q, history):
            parts.append(piece)
            print(piece, end="", flush=True)
        print("\n")
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": "".join(parts)}]


if __name__ == "__main__":
    main()
