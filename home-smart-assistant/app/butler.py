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
from datetime import datetime
import config
from app import llm, tools, memory

# Thu trong tuan bang tieng Viet ASCII, index theo datetime.weekday() (0 = thu hai).
_WEEKDAYS = ["Thu hai", "Thu ba", "Thu tu", "Thu nam", "Thu sau", "Thu bay", "Chu nhat"]

SYSTEM_PROMPT = (
    "Ban la Home Smart Assistant, quan gia AI than thien cua mot ngoi nha thong minh. "
    "Luon tra loi bang tieng Viet, tu nhien va am ap.\n"
    "Voi loi chao hay tro chuyen thuong ngay: tra loi ngay, ngan gon, khong goi cong cu. "
    "Voi cau hoi that: tra loi NGAN GON 1-3 cau, dua DUNG theo du lieu cong cu tra ve; khong bia, "
    "khong dai dong.\n"
    "QUAN TRONG khi tra loi ve thiet bi/trang thai nha: chi neu DUNG cac thiet bi va trang thai co "
    "trong ket qua get_status. TUYET DOI khong them thiet bi khac, khong tu doi bat/tat, khong them "
    "thong tin thiet bi khong duoc hoi.\n"
    "Khi can du lieu, hay GOI cong cu roi tra loi theo ket qua (dung chi noi y dinh roi dung lai):\n"
    "- get_status: tinh trang thiet bi (bat/tat, nhiet do) va chi so moi truong trong nha.\n"
    "- control_device: bat/tat hoac chinh nhiet do den, quat, dieu hoa.\n"
    "- search_knowledge: cach lam, khac phuc su co (mang/router, thiet bi hong), kien thuc va tin tuc.\n"
    "- get_weather: thoi tiet ngoai troi.\n"
    "- get_calendar / add_event: xem hoac them su kien lich.\n"
    "- remember: ghi nho so thich hoac thong tin co dinh ve nha khi chu nha noi ro.\n"
    "Cau kien thuc chung khong lien quan ngoi nha thi tra loi thang, khong goi cong cu.\n"
    "Chu dong goi y dieu huu ich dua tren so thich, thoi gian, thoi tiet va trang thai nha, nhung nhe nhang.\n"
    "An toan: lenh de dao nguoc (bat/tat den, quat) thi lam ngay roi xac nhan ngan; lenh lon hoac mo ho "
    "(tat toan bo, nhiet do qua cao/thap) thi hoi xac nhan truoc. Khi nong ma dieu hoa/quat dang tat, "
    "de xuat bat va hoi truoc roi moi bat."
)

MAX_STEPS = 5
# Lenh dieu khien tra ve cau xac nhan san, noi thang duoc, khong can model dien dat lai.
DIRECT_REPLY_TOOLS = {"control_device"}

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


def chat(user_message, history=None):
    """Mot luot, khong stream. Tra ve (cau_tra_loi, lich_su_moi). Dung cho API."""
    history = history or []
    messages = _build_messages(user_message, history)

    for _ in range(MAX_STEPS):
        try:
            msg = llm.chat(messages, tools=tools.TOOLS).choices[0].message
        except Exception:
            return "Xin loi, he thong dang phan hoi cham, anh chi thu lai sau giay lat.", history

        if not msg.tool_calls:
            reply = _strip_think(msg.content)
            if not reply:
                # Model chi sinh phan suy nghi (bi cat vi het token) ma chua kip tra loi.
                reply = "Xin loi, anh chi hoi lai giup toi duoc khong a?"
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
            result = tools.execute(tc.function.name, args)
            results.append((tc.function.name, result))
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        if results and all(name in DIRECT_REPLY_TOOLS for name, _ in results):
            reply = " ".join(r for _, r in results)
            return reply, _history_after(history, user_message, reply)

    return "Xin loi, toi chua xu ly duoc yeu cau nay.", history


def chat_stream(user_message, history=None):
    """Mot luot, stream tung doan chu. Yield cac chuoi. Caller tu gom de luu lich su."""
    history = history or []
    messages = _build_messages(user_message, history)

    for _ in range(MAX_STEPS):
        content_parts = []
        calls = {}
        tf = _ThinkFilter()
        produced = False  # da phat duoc chu nao cho chu nha chua (de khong im lang hoan toan)
        try:
            for chunk in llm.chat(messages, tools=tools.TOOLS, stream=True):
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    content_parts.append(delta.content)
                    visible = tf.feed(delta.content)
                    if visible:
                        produced = True
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
            yield "Xin loi, he thong dang phan hoi cham, anh chi thu lai sau giay lat."
            return

        tail = tf.flush()
        if tail:
            produced = True
            yield tail

        if not calls:
            if not produced:
                # Model chi sinh phan suy nghi (bi cat vi het token) ma chua kip tra loi.
                yield "Xin loi, anh chi hoi lai giup toi duoc khong a?"
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
            result = tools.execute(c["name"], args)
            results.append((c["name"], result))
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})

        if results and all(name in DIRECT_REPLY_TOOLS for name, _ in results):
            yield " ".join(r for _, r in results)
            return
        # nguoc lai: vong sau se stream cau tra loi dien dat tu ket qua cong cu

    yield "Xin loi, toi chua xu ly duoc yeu cau nay."


def main():
    print("Dang khoi dong, nap model vao bo nho...", flush=True)
    llm.warm_up()  # nap san model de cau hoi dau tien khong bi tre
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
