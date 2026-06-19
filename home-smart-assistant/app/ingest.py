"""Luong nap du lieu vao Vector DB, cap nhat tang dan (incremental).

Dung manifest bam noi dung de bo qua file khong doi, va xoa roi nap lai file da doi.
"""
import os
import json
import hashlib
import config
from app import documents, llm, vector_store


def _load_manifest():
    if os.path.exists(config.MANIFEST_PATH):
        with open(config.MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_manifest(manifest):
    os.makedirs(os.path.dirname(config.MANIFEST_PATH), exist_ok=True)
    with open(config.MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def _hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def ingest_file(path, manifest=None):
    """Nap mot file. Bo qua neu noi dung khong doi. Tra ve so doan da nap."""
    save = manifest is None
    if manifest is None:
        manifest = _load_manifest()

    source = os.path.basename(path)
    text = documents.load_text(path)
    digest = _hash(text)

    if manifest.get(source) == digest:
        print(f"  = {source}: khong doi, bo qua")
        if save:
            _save_manifest(manifest)
        return 0

    vector_store.delete_source(source)
    chunks = documents.chunk(text)
    if chunks:
        vector_store.add_chunks(source, chunks, [llm.embed(c) for c in chunks])
    manifest[source] = digest

    if save:
        _save_manifest(manifest)
    print(f"  + {source}: {len(chunks)} doan")
    return len(chunks)


def remove_file(path, manifest=None):
    """Xoa du lieu cua mot file khoi Vector DB."""
    save = manifest is None
    if manifest is None:
        manifest = _load_manifest()
    source = os.path.basename(path)
    vector_store.delete_source(source)
    manifest.pop(source, None)
    if save:
        _save_manifest(manifest)
    print(f"  - {source}: da xoa khoi kho")


def ingest_dir(directory=None):
    """Nap toan bo thu muc, chi xu ly file moi hoac doi, va don file da bi xoa."""
    directory = directory or config.ARTICLES_DIR
    manifest = _load_manifest()
    total = 0
    seen = set()
    for root, _, files in os.walk(directory):
        for name in files:
            if name.lower().endswith(config.SUPPORTED_EXT):
                total += ingest_file(os.path.join(root, name), manifest)
                seen.add(name)
    for source in list(manifest.keys()):
        if source not in seen:
            vector_store.delete_source(source)
            manifest.pop(source, None)
            print(f"  - {source}: khong con trong thu muc, da xoa")
    _save_manifest(manifest)
    return total
