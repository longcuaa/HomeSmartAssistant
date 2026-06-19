"""Client goi model qua endpoint tuong thich OpenAI.

Cung cap chat (co the kem cong cu de tool calling) va embedding. Local dung Ollama,
production doi LLM_BASE_URL sang vLLM, code khong sua.
"""
from openai import OpenAI
import config

# timeout va max_retries de mot luot goi cham/treo bi cat sau LLM_TIMEOUT thay vi cho rat lau.
_client = OpenAI(
    base_url=config.LLM_BASE_URL,
    api_key=config.LLM_API_KEY,
    timeout=config.LLM_TIMEOUT,
    max_retries=1,
)


def embed(text):
    """Tra ve vector embedding cho mot doan van ban."""
    resp = _client.embeddings.create(model=config.EMBED_MODEL, input=text)
    return resp.data[0].embedding


def chat(messages, tools=None, stream=False):
    """Goi model chat. Truyen tools de bat tool calling, stream de sinh dan.

    Gioi han max_tokens de cau tra loi ngan gon va nhanh hon (xem config.MAX_TOKENS).
    """
    kwargs = {
        "model": config.CHAT_MODEL,
        "messages": messages,
        "stream": stream,
        "max_tokens": config.MAX_TOKENS,
    }
    if tools:
        kwargs["tools"] = tools
    return _client.chat.completions.create(**kwargs)
