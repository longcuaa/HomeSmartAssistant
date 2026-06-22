"""Chay bo cau hoi danh gia qua quan gia, do do tre va xem dinh tuyen (fast-path/LLM).

Muc dich: KIEM THU + CAI THIEN bot. Chay xong, soi cau nao tra loi sai/cham hoac chon
sai tool, roi chinh system prompt / fast-path / mo ta tool cho tot hon. Model off-the-shelf
khong fine-tune, nen "huan luyen" o day la vong lap: chay -> soi -> sua prompt -> chay lai.

Cach dung:
    python scripts/eval.py                 # chay het, in ket qua
    python scripts/eval.py --group C L     # chi chay nhom C va L
    python scripts/eval.py --no-llm        # chi chay cau di duong fast-path (khong can Ollama)
    python scripts/eval.py --out kq.md     # luu ket qua ra file Markdown

Can Ollama dang chay (tru khi --no-llm). Bo du lieu: data/eval/bo_cau_hoi.json.
"""
import os
import sys
import json
import time
import argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # console Windows hien tieng Viet
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from app import butler, llm

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "eval", "bo_cau_hoi.json")


def _route_of(question):
    """Doan duong di MA KHONG goi LLM: fast-path/cache tra duoc -> 'fastpath', con lai 'llm'."""
    if butler._cache_get(question) is not None:
        return "cache"
    if butler._fast_path(question) is not None:
        return "fastpath"
    return "llm"


def _run_turn(question, history):
    """Chay mot luot, tra ve (reply, history_moi, do_tre_giay)."""
    t = time.perf_counter()
    reply, history = butler.chat(question, history)
    return reply, history, time.perf_counter() - t


def _short(text, n=160):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + "..."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", nargs="*", help="Chi chay cac nhom theo id, vd: C L R")
    ap.add_argument("--no-llm", action="store_true", help="Chi chay cau di fast-path, bo cau can LLM")
    ap.add_argument("--out", help="Luu ket qua ra file Markdown")
    args = ap.parse_args()

    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    groups = data["groups"]
    if args.group:
        want = {g.upper() for g in args.group}
        groups = [g for g in groups if g["id"].upper() in want]

    lines = []  # gom de luu ra file neu can

    def emit(s=""):
        print(s)
        lines.append(s)

    emit(f"# Ket qua danh gia  (model={config.CHAT_MODEL}, thinking={config.ENABLE_THINKING})")
    emit("")
    if not args.no_llm:
        t = time.perf_counter()
        llm.warm_up()
        emit(f"_Lam nong model: {time.perf_counter() - t:.1f}s_\n")

    n_total = n_fast = 0
    slow = []  # (do_tre, nhom, cau) cho cau LLM cham de soi sau

    for g in groups:
        emit(f"## [{g['id']}] {g['name']}")
        emit(f"_{g.get('muc_tieu', '')}_\n")
        for item in g["items"]:
            turns = item.get("turns") or [item["q"]]
            # Cau di fast-path se duoc danh dau; cau LLM bi bo qua khi --no-llm.
            first_route = _route_of(turns[0])
            if args.no_llm and first_route == "llm":
                emit(f"- (bo qua, can LLM) {turns[0]!r}")
                continue

            history = []
            for i, q in enumerate(turns):
                route = _route_of(q)
                reply, history, dt = _run_turn(q, history)
                n_total += 1
                if route in ("fastpath", "cache"):
                    n_fast += 1
                elif dt > 4.0:
                    slow.append((dt, g["id"], q))
                tag = {"fastpath": "FAST", "cache": "CACHE", "llm": "LLM "}[route]
                prefix = f"  - luot {i+1}: " if len(turns) > 1 else "- "
                emit(f"{prefix}[{tag} {dt:4.1f}s] {q!r}")
                emit(f"    -> {_short(reply)}")
            if item.get("expect"):
                emit(f"    (ky vong: {item['expect']})")
        emit("")

    emit("## Tong ket")
    emit(f"- Tong so luot: {n_total}")
    emit(f"- Tra qua fast-path/cache (~0s): {n_fast}")
    emit(f"- Qua LLM: {n_total - n_fast}")
    if slow:
        emit(f"- Cau LLM cham (>4s) can xem lai: {len(slow)}")
        for dt, gid, q in sorted(slow, reverse=True)[:10]:
            emit(f"    [{gid}] {dt:4.1f}s  {q!r}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"\nDa luu ket qua vao {args.out}")


if __name__ == "__main__":
    main()
