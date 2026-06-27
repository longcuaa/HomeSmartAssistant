"""Tier 2 — khop theo do tuong dong ngu nghia (embedding).

Tao san mot bo cau vi du (tu thiet bi va scene trong registry) -> embed mot lan -> luu ma tran.
Cau moi: embed -> cosine -> neu diem cao nhat > nguong thi lay intent cua vi du do.

Backend (uu tien giam dan, tu chon theo cai dat thuc te):
  1. sentence-transformers (neu da pip install) — chay CPU, dung dung mo hinh trong spec.
  2. Ollama embedder (nomic-embed-text) — tan dung san model embedding cua du an.
  3. Khong co gi -> tang nay TU DONG TAT (resolver bo qua, xuong Tier 3).
"""
import numpy as np
from server.core import text_norm as tn
from server.models.intent import Intent


class EmbeddingTier:
    def __init__(self, cfg, registry):
        self.cfg = cfg
        self.reg = registry
        self.threshold = float(cfg.get("intent.embedding_threshold", 0.85))
        self.examples = self._build_examples()   # [(text, intent_template_dict)]
        self.backend = None
        self._st = None
        self._matrix = None                        # ma tran embedding cac vi du (lazy)
        self._select_backend()

    @property
    def enabled(self):
        return self.backend is not None

    def _build_examples(self):
        ex = []
        for d in self.reg.devices.values():
            phrases = [d.name] + d.alias
            for p in phrases[:3]:
                ex.append((f"bat {p}", {"intent": "CONTROL", "action": "ON",
                                        "device_type": d.type, "device_id": d.id, "room": d.room}))
                ex.append((f"tat {p}", {"intent": "CONTROL", "action": "OFF",
                                        "device_type": d.type, "device_id": d.id, "room": d.room}))
        for sid, s in self.reg.scenes.items():
            for ph in s.get("trigger_phrases", []):
                ex.append((ph, {"intent": "SCENE", "action": "SCENE", "device_id": sid,
                                "parameters": {"scene": sid},
                                "targets": [dict(a) for a in s.get("actions", [])],
                                "response_vi": s.get("response_vi", "")}))
        return ex

    def _select_backend(self):
        # 1) sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            self._st = SentenceTransformer(self.cfg.get(
                "models.embedding.st_model",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
            self.backend = "sentence-transformers"
            return
        except Exception:
            self._st = None
        # 2) Ollama embedder — thu mot phat de chac chan Ollama dang chay.
        try:
            from server.core import llm_client
            llm_client.embed("kiem tra")
            self.backend = "ollama"
        except Exception:
            self.backend = None

    def _embed_many(self, texts):
        if self.backend == "sentence-transformers":
            return np.asarray(self._st.encode(texts, normalize_embeddings=True), dtype=np.float32)
        from server.core import llm_client
        vecs = [llm_client.embed(t) for t in texts]
        arr = np.asarray(vecs, dtype=np.float32)
        return arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9)

    def _embed_one(self, text):
        return self._embed_many([text])[0]

    def _ensure_matrix(self):
        if self._matrix is None:
            self._matrix = self._embed_many([tn.norm_device(t) for t, _ in self.examples])

    def match(self, text):
        """Tra ve Intent (tier chua dien) hoac None."""
        if not self.enabled:
            return None
        try:
            self._ensure_matrix()
            q = self._embed_one(tn.norm_device(text))
        except Exception:
            return None
        sims = self._matrix @ q                     # da chuan hoa -> tich vo huong = cosine
        i = int(np.argmax(sims))
        score = float(sims[i])
        if score < self.threshold:
            return None
        tmpl = dict(self.examples[i][1])
        tmpl.setdefault("response_vi", self._default_response(tmpl))
        tmpl["confidence"] = round(score, 3)
        return Intent(**tmpl)

    def _default_response(self, tmpl):
        d = self.reg.get(tmpl.get("device_id"))
        name = d.name if d else "thiết bị"
        if tmpl.get("action") == "ON":
            return f"Dạ, tôi sẽ bật {name} ngay ạ."
        if tmpl.get("action") == "OFF":
            return f"Dạ, tôi sẽ tắt {name} ngay ạ."
        return "Dạ, tôi đã thực hiện ạ."
