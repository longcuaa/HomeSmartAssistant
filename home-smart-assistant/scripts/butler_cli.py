"""Tro chuyen voi quan gia qua dong lenh.

Chay: python scripts/butler_cli.py  (tu thu muc goc cua project)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import butler

if __name__ == "__main__":
    butler.main()
