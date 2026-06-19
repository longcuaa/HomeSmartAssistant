"""Chay bo lich cap nhat tai lieu moi sang.

Chay: python scripts/scheduler.py  (tu thu muc goc cua project)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import scheduler

if __name__ == "__main__":
    scheduler.start_blocking()
