"""Tam thoi: xem cau hoi ve TRANG THAI thiet bi goi dung cong cu (mock DB) khong."""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from app import butler
import app.tools as tools

# Theo doi cong cu nao duoc goi
_called = []
_orig = tools.execute
def _traced(name, args):
    _called.append(name)
    return _orig(name, args)
tools.execute = _traced

print(f"CHAT_MODEL={config.CHAT_MODEL}\n")
for q in ["Nha minh co nhung thiet bi gi va dang bat hay tat?",
          "Den phong khach co dang bat khong?"]:
    _called.clear()
    reply, _ = butler.chat(q)
    print(f"Q: {q}")
    print(f"   -> cong cu goi: {_called}")
    print(f"   -> tra loi: {reply}\n")
