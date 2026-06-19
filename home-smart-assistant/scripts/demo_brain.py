"""Trinh dien "bo nao" cua quan gia bang mot kich ban dung san.

Chay tu thu muc goc:  python scripts/demo_brain.py
Them --reset de xoa tri nho truoc khi chay, demo lai tu trang thai sach.

Yeu cau: Ollama dang chay voi qwen3:8b va nomic-embed-text, va da nap du lieu mau
(python scripts/ingest_once.py). Khong can MQTT: thiet bi tu chuyen sang che do gia lap,
cau xac nhan se co hau to '(gia lap)'.

Kich ban di qua 7 nang luc: tro chuyen, dieu khien tuc thi, xac nhan hanh dong he trong,
tra cuu tai lieu (RAG), tri nho dai han, hoc tu cau hoi, va an suy nghi noi bo.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import butler, memory, vector_store
import config


def _hr(title):
    """In tieu de mot phan cho de doc."""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def say(history, msg):
    """Gui mot luot cho quan gia, in ra, kiem tra khong lo suy nghi noi bo, tra ve lich su moi."""
    print(f"\nChu nha: {msg}")
    reply, history = butler.chat(msg, history)
    print(f"Quan gia: {reply}")
    # Quan gia khong duoc lo khoi <think> noi bo ra cho chu nha.
    assert "<think>" not in reply and "</think>" not in reply, "Lo suy nghi noi bo trong cau tra loi!"
    return history


def dump_brain():
    """In trang thai bo nho de thay no thay doi giua cac phan."""
    data = memory.load()
    print("\n-- Trang thai bo nao (data/memory.json) --")
    print(f"   So thich     : {data['preferences']}")
    print(f"   Thong tin nha: {data['facts']}")
    print(f"   Chu de (dem) : {data['topics']}")
    print(f"   Quan tam     : {memory.interests()}  (nguong = {config.INTEREST_THRESHOLD})")
    txt = memory.as_text()
    if txt:
        print(f"   Chen vao prompt: {txt}")


def main():
    reset = "--reset" in sys.argv
    if reset:
        memory.clear()
        print("Da xoa tri nho de demo tu trang thai sach.")

    # Kiem tra kho kien thuc da co du lieu chua.
    chunks = vector_store.count()
    if chunks == 0:
        print("Kho kien thuc dang trong. Hay chay truoc:  python scripts/ingest_once.py")
        return
    print(f"Kho kien thuc: {chunks} doan. Bat dau demo.\n")

    history = []

    _hr("Buoc 1: Tro chuyen tu nhien (persona quan gia)")
    try:
        history = say(history, "Chao buoi sang. Goi y giup toi mot meo tiet kiem dien trong nha.")
    except Exception as e:
        print(f"\nLoi khi goi model: {e}")
        print("Hay chac chan Ollama dang chay (qwen3:8b) va co the truy cap tu may nay.")
        return

    _hr("Buoc 2: Dieu khien thiet bi tuc thi (toi uu toc do)")
    print("Lenh don gian: noi thang ket qua, bo qua mot luot model. Khong co MQTT -> (gia lap).")
    history = say(history, "Bat den phong khach giup toi.")

    _hr("Buoc 3: Xac nhan hanh dong he trong truoc khi lam")
    print("Lenh anh huong lon: quan gia hoi lai truoc khi thuc thi.")
    history = say(history, "Tat het thiet bi trong nha di.")
    history = say(history, "Dung, tat het giup toi.")

    _hr("Buoc 4: Tra cuu tai lieu cua nha (RAG)")
    print("Cau tra loi bam vao data/articles/sample.txt thay vi doan.")
    history = say(history, "Router bi loi mang thi xu ly the nao?")

    _hr("Buoc 5: Tri nho dai han (so thich + thong tin nha)")
    history = say(history, "Toi thich de dieu hoa 25 do vao ban dem.")
    history = say(history, "Tien the nho giup: phong ngu chinh nha toi o tang 2.")
    dump_brain()

    _hr("Buoc 6: Hoc tu cau hoi (chu de hoi nhieu lan thanh quan tam)")
    print(f"Hoi cung mot cau {config.INTEREST_THRESHOLD} lan; moi lan search_knowledge dem them mot.")
    q = "Cam bien bao mat trong nha hoat dong the nao?"
    for i in range(config.INTEREST_THRESHOLD):
        print(f"\n[Lan hoi {i + 1}/{config.INTEREST_THRESHOLD}]")
        history = say(history, q)
        dump_brain()

    _hr("Buoc 7: An suy nghi noi bo")
    print("Moi cau 'Quan gia:' o tren da qua kiem tra: khong he chua <think>.")
    print("Co che: app/butler.py -> _strip_think / _ThinkFilter loc khoi <think>...</think>.")

    print("\nXong demo. Xem DEMO.md de lam thu cong, hoac chay lai voi --reset de sach tri nho.")


if __name__ == "__main__":
    main()
