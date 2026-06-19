"""Cau hinh tap trung cho Home Smart Assistant."""
import os
from dotenv import load_dotenv

load_dotenv()

# Model va endpoint (tuong thich OpenAI: Ollama o local, vLLM tren AWS)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen3:8b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

# Toc do phan hoi (latency)
# ENABLE_THINKING=false tat che do suy nghi cua qwen3 (/no_think) -> tra loi nhanh hon nhieu,
# danh doi mot chut chieu sau suy luan. Dat true neu uu tien chat luong hon toc do.
ENABLE_THINKING = os.getenv("ENABLE_THINKING", "false").lower() in ("1", "true", "yes")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))  # gioi han do dai cau tra loi cho nhanh va gon
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))  # giay; tranh treo lau khi model phan hoi cham

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
