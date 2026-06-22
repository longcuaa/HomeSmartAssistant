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
    "không máy móc, không khách sáo cứng nhắc. Luôn dùng tiếng Việt (không chêm ngoại ngữ).\n"
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


# Tu xac nhan / tu choi (da bo dau). Tranh 'dung' vi 'dung'(dung roi) lan 'dung'(dung lam).
_CONFIRM_RE = re.compile(r"\b(co|u|um|uh|ok|oke|okay|vang|chuan|dong y|duoc|dung roi)\b")
_DENY_RE = re.compile(r"\b(khong|thoi|khoi|huy|khoan)\b")
# Trang thai cho xac nhan (CLI 1 nguoi dung). API nhieu phien thi can tach theo phien.
_PENDING = {"action": None, "device": None, "candidates": None}


def _clear_pending():
    _PENDING.update(action=None, device=None, candidates=None)


def _match_devices(words):
    """Cac thiet bi khop voi tu nguoi dung noi (bo 'phong'); tat ca tu da noi nam trong ten."""
    keyw = {k: set(w for w in tools._norm(k).split() if w != "phong") for k in tools.HOME}
    all_dev = set().union(*keyw.values()) if keyw else set()
    said = words & all_dev
    if not said:
        return []
    return [k for k, kw in keyw.items() if said <= kw]


def _fast_path(message):
    """Tra loi tuc thi (KHONG goi LLM) cho y dinh thiet bi. Tra None -> de LLM xu ly.

    Lenh bat/tat LUON hoi xac nhan truoc khi lam:
    - Ro rang 1 thiet bi -> 'Ban co chac muon bat/tat X khong?' -> 'co' moi lam.
    - Mo ho nhieu thiet bi -> 'Ban muon ... thiet bi nao: ...?' -> chon ten -> lam.
    """
    m = tools._norm(message)
    if not m:
        return None
    words = set(m.split())

    # 1) Dang cho phan hoi cho mot lenh truoc do?
    if _PENDING["action"]:
        act = _PENDING["action"]
        if _PENDING["candidates"]:                       # cho chon thiet bi (lenh mo ho)
            matched = [k for k in _PENDING["candidates"] if k in set(_match_devices(words))]
            verb = "bật" if act == "on" else "tắt"
            if len(matched) == 1:                        # da ro -> hoi xac nhan lan cuoi
                _PENDING.update(action=act, device=matched[0], candidates=None)
                return f"Bạn có chắc muốn {verb} {matched[0]} không?"
            if matched:                                  # van con nhieu -> hoi lai trong so do
                _PENDING["candidates"] = matched
                return f"Bạn muốn {verb} thiết bị nào: {', '.join(matched)}?"
        else:                                            # cho xac nhan co/khong
            if _DENY_RE.search(m):
                _clear_pending()
                return "Đã hủy, không thực hiện."
            if _CONFIRM_RE.search(m):
                dev = _PENDING["device"]
                _clear_pending()
                return tools.control_device(dev, act)
        _clear_pending()                                 # noi gi khac -> bo cho, xu ly nhu lenh moi

    # 2) CAU HOI ve so luong / trang thai -> tra ngay, KHONG coi la lenh (du cau co tu 'bat/tat').
    # Phai xet TRUOC phan dieu khien de 'may cai den dang bat' khong bi hieu nham la lenh bat.
    asking_count = bool(re.search(r"\b(may|bao nhieu)\b", m))
    asking_on = "dang bat" in m
    asking_off = "dang tat" in m
    if asking_count or asking_on or asking_off:
        cands = _match_devices(words)
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
    if _ENV_RE.search(m):
        return tools.get_environment()

    # 3) LENH dieu khien (chi khi KHONG phai cau hoi) -> hoi xac nhan truoc khi lam
    on, off = bool(_ON_RE.search(m)), bool(_OFF_RE.search(m))
    if (on ^ off) and not re.search(r"\d", m):
        cands = _match_devices(words)
        act = "on" if on else "off"
        verb = "bật" if on else "tắt"
        if len(cands) == 1:
            _PENDING.update(action=act, device=cands[0], candidates=None)
            return f"Bạn có chắc muốn {verb} {cands[0]} không?"
        if len(cands) > 1:
            _PENDING.update(action=act, device=None, candidates=cands)
            return f"Bạn muốn {verb} thiết bị nào: {', '.join(cands)}?"
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
            reply = _strip_think(msg.content)
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
                    visible = tf.feed(delta.content)
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

        tail = tf.flush()
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
