"""Client goi model qua endpoint tuong thich OpenAI.

Cung cap chat (co the kem cong cu de tool calling) va embedding. Local dung Ollama,
production doi LLM_BASE_URL sang vLLM, code khong sua.
"""
import sys
import time
from openai import OpenAI
import config

# timeout va max_retries de mot luot goi cham/treo bi cat sau LLM_TIMEOUT thay vi cho rat lau.
_client = OpenAI(
    base_url=config.LLM_BASE_URL,
    api_key=config.LLM_API_KEY,
    timeout=config.LLM_TIMEOUT,
    max_retries=1,
)


def _ollama_extra(num_ctx=False):
    """Tham so rieng cua Ollama gui kem qua extra_body. Tat khi chay vLLM (OLLAMA_TUNING=false).

    keep_alive giu model nam san trong VRAM; num_ctx dat cua so ngu canh cho ban chat.
    """
    if not config.OLLAMA_TUNING:
        return None
    extra = {"keep_alive": config.OLLAMA_KEEP_ALIVE}
    if num_ctx:
        extra["options"] = {"num_ctx": config.OLLAMA_NUM_CTX}
    return extra


def warm_up(embed_too=True):
    """Goi truoc mot luot rat ngan de Ollama nap model vao VRAM, tranh tre o cau hoi dau tien.

    Goi luc khoi dong CLI/API. Khong bao gio nem loi (chi la buoc lam nong, hong thi bo qua).
    """
    kwargs = {"model": config.CHAT_MODEL,
              "messages": [{"role": "user", "content": "hi"}],
              "max_tokens": 1}
    extra = _ollama_extra(num_ctx=True)
    if extra:
        kwargs["extra_body"] = extra
    try:
        _client.chat.completions.create(**kwargs)
    except Exception:
        pass
    if embed_too:
        try:
            embed("hi")  # nap luon model embedding cho lan search_knowledge dau
        except Exception:
            pass


def embed(text):
    """Tra ve vector embedding cho mot doan van ban."""
    kwargs = {"model": config.EMBED_MODEL, "input": text}
    extra = _ollama_extra()
    if extra:
        kwargs["extra_body"] = extra
    resp = _client.embeddings.create(**kwargs)
    return resp.data[0].embedding


def chat(messages, tools=None, stream=False, temperature=None):
    """Goi model chat. Truyen tools de bat tool calling, stream de sinh dan.

    Gioi han max_tokens de cau tra loi ngan gon va nhanh hon (xem config.MAX_TOKENS).
    Nhiet do: mac dinh THAP (TOOL_TEMPERATURE) khi co gui cong cu de tool calling dang tin cay;
    cao hon (TEMPERATURE) cho luot tro chuyen thuan de giu ca tinh. Co the ep bang tham so.
    """
    if temperature is None:
        temperature = config.TOOL_TEMPERATURE if tools else config.TEMPERATURE
    kwargs = {
        "model": config.CHAT_MODEL,
        "messages": messages,
        "stream": stream,
        "max_tokens": config.MAX_TOKENS,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools
    extra = _ollama_extra(num_ctx=True)
    if extra:
        kwargs["extra_body"] = extra

    if not config.LLM_DEBUG:
        return _client.chat.completions.create(**kwargs)
    t0 = time.perf_counter()
    resp = _client.chat.completions.create(**kwargs)
    dt = (time.perf_counter() - t0) * 1000
    # Khi stream, day la thoi gian den token dau (TTFT); khi khong stream la tong thoi gian.
    print(f"[llm] chat {'TTFT' if stream else 'tong'}={dt:.0f}ms", file=sys.stderr)
    return resp
