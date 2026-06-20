"""CLI cho tro ly giong noi: stream TUNG CAU ra NGAY khi co (khong doi het cau tra loi).

Chay: python scripts/voice_cli.py

Hien dang o che do TEST TEXT: in tung cau kem moc thoi gian de ban kiem tra noi dung va xac nhan
no stream that (moc giay tang dan = ra dan, dung doi het). Khi ung y, cam TTS vao ham speak().

Mau chot: xu ly NGAY TRONG vong lap stream_sentences(...) -> cau dau duoc phat ngay trong khi
model con dang sinh cau sau. KHONG dung butler.chat() (cho xong het), KHONG dung "".join(...).
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import butler, llm

# Bat/tat doc thanh tieng. De False khi chi test text; True khi da cam TTS vao speak().
TTS_ON = False


def speak(text):
    """Cam TTS that vao day (piper / edge-tts...). Hien de trong de chi test text."""
    if not TTS_ON:
        return
    # TODO: goi TTS doc 'text' o day, vi du: tts_engine.say(text); hoac phat file am thanh.
    pass


def main():
    print("Dang nap model...", flush=True)
    llm.warm_up()
    print("San sang. Go cau hoi ('thoat' de thoat).\n", flush=True)
    history = []
    while True:
        q = input("Ban: ").strip()
        if q.lower() in ("exit", "quit", "thoat"):
            break
        if not q:
            continue
        t0 = time.perf_counter()
        parts = []
        # stream_sentences yield tung CAU ngay khi hoan chinh -> xu ly lien, khong cho het.
        for cau in butler.stream_sentences(butler.chat_stream(q, history)):
            dt = time.perf_counter() - t0
            print(f"  [{dt:5.2f}s] {cau}", flush=True)  # TEST TEXT: xem noi dung + thoi diem moi cau
            speak(cau)                                   # TTS (bat bang TTS_ON o tren)
            parts.append(cau)
        history += [{"role": "user", "content": q},
                    {"role": "assistant", "content": " ".join(parts)}]
        print(flush=True)


if __name__ == "__main__":
    main()
