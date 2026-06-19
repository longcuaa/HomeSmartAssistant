"""Doc file thanh van ban va cat thanh doan nho."""
from pypdf import PdfReader
import config


def load_text(path):
    """Doc noi dung text tu .txt, .md hoac .pdf."""
    if path.lower().endswith(".pdf"):
        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def chunk(text, size=None, overlap=None):
    """Cat van ban thanh cac doan co goi dau de giu ngu canh."""
    size = size or config.CHUNK_SIZE
    overlap = overlap or config.CHUNK_OVERLAP
    text = " ".join(text.split())
    out = []
    start = 0
    while start < len(text):
        out.append(text[start:start + size])
        start += size - overlap
    return [c for c in out if c.strip()]
