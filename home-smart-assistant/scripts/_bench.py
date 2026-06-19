"""Tam thoi: do tre va kiem tra ngon ngu tra loi. Xoa sau khi do xong."""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # console Windows hien tieng Viet
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from app import butler, llm

print(f"CHAT_MODEL={config.CHAT_MODEL} ENABLE_THINKING={config.ENABLE_THINKING} "
      f"MAX_TOKENS={config.MAX_TOKENS} KEEP_ALIVE={config.OLLAMA_KEEP_ALIVE}")

t = time.perf_counter()
llm.warm_up()
print(f"[warmup] {time.perf_counter() - t:.1f}s\n")

for q in ["xin chao", "xin chao", "may gio roi"]:
    t = time.perf_counter()
    reply, _ = butler.chat(q)
    print(f"Q: {q!r}  ->  {time.perf_counter() - t:.1f}s")
    print(f"A: {reply!r}\n")
