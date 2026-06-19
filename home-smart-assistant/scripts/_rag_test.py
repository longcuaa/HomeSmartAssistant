"""Tam thoi: xem RAG tra ve gi va quan gia tra loi the nao cho cau hoi ve thiet bi."""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from app import butler, tools, vector_store, llm

print(f"CHAT_MODEL={config.CHAT_MODEL}  so doan trong kho={vector_store.count()}\n")

q = "router wifi nha bi loi mang thi xu ly sao"
print("=== RAG tra ve cho cau hoi nay ===")
print(tools.search_knowledge(q))

print("\n=== Quan gia tra loi (qua butler.chat) ===")
reply, _ = butler.chat("Router wifi nha minh bi loi mang, xu ly the nao?")
print(reply)
