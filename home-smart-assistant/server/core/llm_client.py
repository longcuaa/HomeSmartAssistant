"""Client OpenAI-compatible dung chung (Ollama o local, vLLM o production).

Dung cho Tier 3 (chat) va Tier 2 fallback (embedding qua nomic-embed-text). Doc cau hinh tu
config.yaml (models.llm.*). Khong nem loi luc khoi tao; loi mang xay ra luc GOI va duoc bat o noi goi.
"""
from openai import OpenAI
from server.config import cfg as _cfg


def _build():
    base = _cfg.get("models.llm.base_url", "http://localhost:11434/v1")
    key = _cfg.get("models.llm.api_key", "ollama")
    timeout = _cfg.get("models.llm.timeout_s", 8)
    return OpenAI(base_url=base, api_key=key, timeout=timeout, max_retries=0)


client = _build()

CHAT_MODEL = _cfg.get("models.llm.model", "qwen2.5:3b")
EMBED_MODEL = _cfg.get("models.embedding.ollama_model", "nomic-embed-text")


def embed(text):
    """Vector embedding qua Ollama. Co the nem loi neu Ollama khong chay -> caller tu xu ly."""
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding


def chat(messages, stream=False):
    """Goi model chat. Tham so gon (max_tokens, temperature) lay tu config."""
    return client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        stream=stream,
        max_tokens=_cfg.get("models.llm.max_tokens", 256),
        temperature=_cfg.get("models.llm.temperature", 0.1),
    )
