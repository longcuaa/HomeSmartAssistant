"""Boc Chroma: them, xoa theo nguon, truy hoi. Khoi tao lazy (lan dung dau)."""
import chromadb
import config

_col = None


def _collection():
    global _col
    if _col is None:
        db = chromadb.PersistentClient(path=config.CHROMA_DIR)
        _col = db.get_or_create_collection(config.COLLECTION)
    return _col


def delete_source(source):
    """Xoa moi doan thuoc ve mot file nguon."""
    _collection().delete(where={"source": source})


def add_chunks(source, chunks, embeddings):
    """Them cac doan cua mot file vao kho kem metadata nguon."""
    ids = [f"{source}::{i}" for i in range(len(chunks))]
    metas = [{"source": source, "chunk": i} for i in range(len(chunks))]
    _collection().add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metas)


def query(embedding, k=None):
    """Tra ve (documents, metadatas) cua k doan gan nhat."""
    k = k or config.TOP_K
    res = _collection().query(query_embeddings=[embedding], n_results=k)
    docs = res["documents"][0] if res["documents"] else []
    metas = res["metadatas"][0] if res["metadatas"] else []
    return docs, metas


def count():
    """So doan dang co trong kho."""
    return _collection().count()
