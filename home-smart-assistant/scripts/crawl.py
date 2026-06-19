"""Crawl tai lieu tu web roi nap vao Vector DB.

Ba cach dung, deu chay tu thu muc goc cua project:

  Tu sources.txt (mac dinh khi khong truyen gi, hoac dung --sources):
      python scripts/crawl.py
      python scripts/crawl.py --sources

  Mot danh sach URL cu the:
      python scripts/crawl.py https://... https://...

  Ca mot site trong cung ten mien:
      python scripts/crawl.py --site https://example.com --max 30

Them --no-ingest neu chi muon crawl ma chua nap vao kho.
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from app import crawler, ingest, scheduler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*", help="Danh sach URL de crawl")
    ap.add_argument("--sources", action="store_true", help="Crawl cac URL trong sources.txt")
    ap.add_argument("--site", help="Crawl ca mot site tu URL goc nay")
    ap.add_argument("--max", type=int, default=20, help="So trang toi da khi crawl site")
    ap.add_argument("--no-ingest", action="store_true", help="Chi crawl, khong nap vao kho")
    args = ap.parse_args()

    if args.site:
        saved = crawler.crawl_site(args.site, max_pages=args.max)
    elif args.urls:
        saved = crawler.crawl_urls(args.urls)
    else:
        urls = scheduler.load_sources()
        if not urls:
            print(f"Khong co URL nao trong {config.SOURCES_PATH}.")
            print("Them URL bai bao vao file do, moi dong mot URL, roi chay lai.")
            return
        print(f"Crawl {len(urls)} URL tu {config.SOURCES_PATH}...")
        saved = crawler.crawl_urls(urls)

    print(f"\nDa luu {len(saved)} trang vao thu muc articles.")
    if saved and not args.no_ingest:
        print("Nap vao Vector DB...")
        ingest.ingest_dir()


if __name__ == "__main__":
    main()
