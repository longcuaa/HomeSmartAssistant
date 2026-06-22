"""Cau hinh tap trung cho Home Smart Assistant."""
import os
from dotenv import load_dotenv

load_dotenv()

# Model va endpoint (tuong thich OpenAI: Ollama o local, vLLM tren AWS)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
# qwen2.5:7b-instruct: model instruct (KHONG co che do suy nghi) -> goi cong cu (tool calling)
# on dinh hon va nhanh hon qwen3:8b. qwen3 hay "ke ra" tool call dang van ban thay vi goi that.
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:7b-instruct")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

# Toc do phan hoi (latency)
# ENABLE_THINKING chi co tac dung voi model SUY NGHI (qwen3): false -> them /no_think de tra loi
# nhanh hon. Voi model instruct (qwen2.5) thi khong anh huong (xem butler._system).
ENABLE_THINKING = os.getenv("ENABLE_THINKING", "false").lower() in ("1", "true", "yes")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))  # gioi han do dai cau tra loi cho nhanh va gon
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))  # giay; tranh treo lau khi model phan hoi cham
# Nhiet do sinh cho luot TRO CHUYEN (khong kem cong cu): co the de cao hon de cau tra loi co
# CA TINH, tu nhien. Khong anh huong do tin cay tool calling vi luot do dung TOOL_TEMPERATURE.
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
# Nhiet do RIENG cho luot CO GUI CONG CU (tool calling). PHAI de THAP: nhiet do cao khien model
# hay "ke ra y dinh" (in control_device({...}) dang van ban) thay vi goi cong cu that -> thiet bi
# khong chay. Tach khoi TEMPERATURE de van giu duoc ca tinh cho cau tro chuyen ma khong hong tool.
TOOL_TEMPERATURE = float(os.getenv("TOOL_TEMPERATURE", "0.1"))

# Toi uu rieng cho Ollama (local). Khi chuyen sang vLLM tren AWS dat OLLAMA_TUNING=false
# de khong gui cac truong rieng cua Ollama (keep_alive, options) lam vLLM bao loi.
OLLAMA_TUNING = os.getenv("OLLAMA_TUNING", "true").lower() in ("1", "true", "yes")
# Giu model nam san trong VRAM giua cac luot, tranh tre vai giay khi nap lai. "-1" = giu mai.
# Hieu qua nhat khi dat o phia Ollama server: env OLLAMA_KEEP_ALIVE=-1.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "-1")
# Cua so ngu canh: du chua system + tools + lich su + ket qua RAG ma khong phi VRAM.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
# In do tre moi luot goi model ra stderr de chan doan toc do (TTFT khi stream, tong khi khong).
LLM_DEBUG = os.getenv("LLM_DEBUG", "false").lower() in ("1", "true", "yes")

# Duong dan
ARTICLES_DIR = os.getenv("ARTICLES_DIR", "data/articles")
CHROMA_DIR = os.getenv("CHROMA_DIR", "data/chroma_db")
MANIFEST_PATH = os.getenv("MANIFEST_PATH", "data/manifest.json")
MEMORY_PATH = os.getenv("MEMORY_PATH", "data/memory.json")
COLLECTION = os.getenv("COLLECTION", "articles")

# Cat doan va truy hoi
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
TOP_K = int(os.getenv("TOP_K", "4"))

# Bo nho dai han cua chu nha
INTEREST_THRESHOLD = int(os.getenv("INTEREST_THRESHOLD", "3"))  # hoi bao nhieu lan thi thanh "quan tam"
MEMORY_MAX_ITEMS = int(os.getenv("MEMORY_MAX_ITEMS", "20"))     # so so thich/thong tin nha giu lai
MEMORY_MAX_INTERESTS = int(os.getenv("MEMORY_MAX_INTERESTS", "5"))  # so quan tam chen vao prompt
MEMORY_MAX_TOPICS = int(os.getenv("MEMORY_MAX_TOPICS", "100"))  # tran chu de truoc khi tia bot

# Crawler
CRAWL_USER_AGENT = os.getenv("CRAWL_USER_AGENT", "home-smart-assistant-crawler/1.0")
CRAWL_DELAY = float(os.getenv("CRAWL_DELAY", "1.5"))
CRAWL_TIMEOUT = int(os.getenv("CRAWL_TIMEOUT", "20"))
CRAWL_MIN_CHARS = int(os.getenv("CRAWL_MIN_CHARS", "200"))

# Cap nhat tu nguon bao theo lich moi sang
SOURCES_PATH = os.getenv("SOURCES_PATH", "data/sources.txt")
FEEDS_PATH = os.getenv("FEEDS_PATH", "data/feeds.txt")
DAILY_UPDATE_HOUR = int(os.getenv("DAILY_UPDATE_HOUR", "6"))
DAILY_UPDATE_MINUTE = int(os.getenv("DAILY_UPDATE_MINUTE", "0"))

# Thoi tiet (Open-Meteo, khong can API key) va lich su kien
HOME_LAT = float(os.getenv("HOME_LAT", "21.0278"))    # mac dinh Ha Noi
HOME_LON = float(os.getenv("HOME_LON", "105.8342"))
WEATHER_TIMEOUT = int(os.getenv("WEATHER_TIMEOUT", "10"))
WEATHER_CACHE_SECS = int(os.getenv("WEATHER_CACHE_SECS", "900"))
WEATHER_USER_AGENT = os.getenv("WEATHER_USER_AGENT", "home-smart-assistant/1.0")
EVENTS_PATH = os.getenv("EVENTS_PATH", "data/events.json")

# MQTT (noi thiet bi va cam bien that qua Home Assistant / ESP32)
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TIMEOUT = int(os.getenv("MQTT_TIMEOUT", "5"))
MQTT_CONNECT_TIMEOUT = int(os.getenv("MQTT_CONNECT_TIMEOUT", "2"))  # giay; kiem tra broker truoc, tranh treo lau

# Topic cam bien moi truong
SENSOR_TOPIC_NHIET_DO = os.getenv("SENSOR_TOPIC_NHIET_DO", "home/sensors/nhiet_do")
SENSOR_TOPIC_DO_AM = os.getenv("SENSOR_TOPIC_DO_AM", "home/sensors/do_am")
SENSOR_TOPIC_KHONG_KHI = os.getenv("SENSOR_TOPIC_KHONG_KHI", "home/sensors/chat_luong_khong_khi")
SENSOR_TOPIC_DO_SANG = os.getenv("SENSOR_TOPIC_DO_SANG", "home/sensors/do_sang")

SUPPORTED_EXT = (".txt", ".md", ".pdf")
