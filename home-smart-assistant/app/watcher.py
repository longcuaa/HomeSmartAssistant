"""Tu dong cap nhat Vector DB khi thu muc bai bao thay doi.

Chay: python -m app.watcher  (tu thu muc goc cua project)
"""
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import config
from app import ingest


class ArticleHandler(FileSystemEventHandler):
    def _ok(self, event):
        return (not event.is_directory) and event.src_path.lower().endswith(config.SUPPORTED_EXT)

    def on_created(self, event):
        if self._ok(event):
            print(f"[moi] {event.src_path}")
            ingest.ingest_file(event.src_path)

    def on_modified(self, event):
        if self._ok(event):
            print(f"[doi] {event.src_path}")
            ingest.ingest_file(event.src_path)

    def on_deleted(self, event):
        if self._ok(event):
            print(f"[xoa] {event.src_path}")
            ingest.remove_file(event.src_path)


def main():
    print(f"Nap lan dau va theo doi thu muc {config.ARTICLES_DIR}. Ctrl+C de dung.")
    ingest.ingest_dir()
    observer = Observer()
    observer.schedule(ArticleHandler(), config.ARTICLES_DIR, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
