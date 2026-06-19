"""Nap toan bo thu muc bai bao mot lan.

Chay: python scripts/ingest_once.py  (tu thu muc goc cua project)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import ingest

if __name__ == "__main__":
    total = ingest.ingest_dir()
    print(f"Xong. Tong cong {total} doan trong kho.")
