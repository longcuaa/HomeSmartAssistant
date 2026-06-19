"""Cap nhat tai lieu tu cac nguon bao theo lich moi sang.

Doc danh sach URL trong data/sources.txt, crawl va nap vao Vector DB.
Chay rieng: python -m app.scheduler  (chay nen, tu fire moi sang)
Hoac duoc nhung san vao API qua start_background().
"""
import os
import config
from app import crawler, ingest


def load_sources():
    """Doc danh sach URL nguon, bo qua dong trong va dong bat dau bang dau thang."""
    if not os.path.exists(config.SOURCES_PATH):
        return []
    urls = []
    with open(config.SOURCES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def daily_update():
    """Crawl tat ca nguon roi nap vao kho. Goi boi lich hoac thu cong."""
    urls = load_sources()
    if not urls:
        print("Khong co nguon nao trong sources.txt, bo qua cap nhat.")
        return
    print(f"Cap nhat {len(urls)} nguon bao...")
    saved = crawler.crawl_urls(urls)
    if saved:
        ingest.ingest_dir()
    print(f"Xong, da cap nhat {len(saved)} trang.")


def start_blocking():
    """Chay bo lich dang blocking (cho tien trinh rieng)."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    sched = BlockingScheduler()
    sched.add_job(daily_update, "cron", hour=config.DAILY_UPDATE_HOUR, minute=config.DAILY_UPDATE_MINUTE)
    print(f"Lich cap nhat moi ngay luc {config.DAILY_UPDATE_HOUR:02d}:{config.DAILY_UPDATE_MINUTE:02d}. Ctrl+C de dung.")
    sched.start()


def start_background():
    """Chay bo lich dang nen, dung khi nhung vao FastAPI. Tra ve scheduler."""
    from apscheduler.schedulers.background import BackgroundScheduler
    sched = BackgroundScheduler()
    sched.add_job(daily_update, "cron", hour=config.DAILY_UPDATE_HOUR, minute=config.DAILY_UPDATE_MINUTE)
    sched.start()
    return sched


if __name__ == "__main__":
    start_blocking()
