"""Kiem tra suc khoe he thong Home Smart Assistant.

Chay: python scripts/check.py  (tu thu muc goc cua project)
In tung muc OK/FAIL roi ket luan chung. Khong sua doi gi, chi doc trang thai.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from app import vector_store, llm, memory, scheduler, device as hub

_issues = []


def ok(label, detail=""):
    print(f"  [OK]   {label}" + (f": {detail}" if detail else ""))


def fail(label, detail=""):
    print(f"  [FAIL] {label}" + (f": {detail}" if detail else ""))
    _issues.append(label)


def _active_lines(path):
    """Doc cac dong active trong file (bo dong trong va dong bat dau bang dau thang)."""
    if not os.path.exists(path):
        return None
    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
    return lines


def check_workspace():
    print("Thu muc lam viec")
    missing = [d for d in ("data", "app", config.ARTICLES_DIR) if not os.path.isdir(d)]
    if missing:
        fail("Cau truc thu muc", "thieu " + ", ".join(missing))
    else:
        ok("Cau truc thu muc", "data, app, articles deu co")


def check_articles():
    print("Tai lieu trong thu muc articles")
    if not os.path.isdir(config.ARTICLES_DIR):
        fail("So file articles", "khong co thu muc")
        return
    n = 0
    for _, _, files in os.walk(config.ARTICLES_DIR):
        n += sum(1 for f in files if f.lower().endswith(config.SUPPORTED_EXT))
    ok("So file articles", str(n))


def check_ollama():
    print("Ollama (chat + embedding)")
    try:
        vec = llm.embed("kiem tra")
        ok("Embedding", f"{len(vec)} chieu qua {config.EMBED_MODEL}")
    except Exception as e:
        fail("Ollama", f"{config.LLM_BASE_URL} loi: {e}")


def check_store():
    print("Vector DB")
    try:
        ok("So chunk trong kho", str(vector_store.count()))
    except Exception as e:
        fail("Vector DB", str(e))


def check_mqtt():
    print("MQTT")
    addr = f"{config.MQTT_HOST}:{config.MQTT_PORT}"
    if hub.connected():
        ok("MQTT broker", addr)
    elif hub.simulated():
        fail("MQTT broker", f"{addr} khong ket noi duoc, dang chay GIA LAP")
    else:
        fail("MQTT broker", f"{addr} khong ket noi duoc")


def check_feeds():
    print("Feeds")
    lines = _active_lines(config.FEEDS_PATH)
    if lines is None:
        ok("feeds.txt", f"chua cau hinh ({config.FEEDS_PATH} khong co)")
    else:
        ok("feeds.txt", f"{len(lines)} feed active")
        for url in lines:
            print(f"         - {url}")


def check_sources():
    print("Sources")
    urls = scheduler.load_sources()
    ok("sources.txt", f"{len(urls)} URL active")


def check_schedule():
    print("Lich cap nhat")
    ok("Gio cap nhat moi ngay", f"{config.DAILY_UPDATE_HOUR:02d}:{config.DAILY_UPDATE_MINUTE:02d}")


def check_memory():
    print("Bo nho so thich")
    try:
        ok("So thich da luu", f"{len(memory.load())} muc")
    except Exception as e:
        fail("Bo nho so thich", str(e))


def main():
    print("Kiem tra suc khoe Home Smart Assistant\n")
    for fn in (check_workspace, check_articles, check_ollama, check_store, check_mqtt,
               check_feeds, check_sources, check_schedule, check_memory):
        fn()
    print()
    if _issues:
        print("Co diem can khac phuc:")
        for label in _issues:
            print(f"  - {label}")
    else:
        print("Moi thu on.")


if __name__ == "__main__":
    main()
