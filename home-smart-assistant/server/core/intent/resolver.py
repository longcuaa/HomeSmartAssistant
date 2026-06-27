"""Bo dieu phoi 3 tang (thuc ra 4: 0,1,2,3) — diem vao chinh cua phan giai y dinh.

Chay lan luot Tier 0 -> 1 -> 2 -> 3, dung o tang dau khop. Do do tre tung tang, dem ti le trung
cache, va tu hoc: cau di qua Tier 3 du tin cay + du nhieu lan -> day len Tier 0 (cache) de lan sau
nhanh hon.

Moi tang co the vang mat (Redis/Ollama/sentence-transformers chua co) -> tu dong bo qua, khong sap.
"""
import time
from server.core.intent.cache import CacheTier
from server.core.intent.fst_matcher import FstMatcher
from server.core.intent.embedding import EmbeddingTier
from server.core.intent.llm_fallback import LlmTier
from server.core.intent.phrasing import Phraser
from server.models.intent import Intent

# Khong cache/khong hoc ket qua duoi nguong nay (tranh 'hoc' phai cau doan mo ho).
_CACHE_MIN_CONF = 0.9


class Resolver:
    def __init__(self, cfg, registry):
        self.cfg = cfg
        self.reg = registry
        self.cache = CacheTier(cfg)
        self.fst = FstMatcher(cfg, registry, cfg.resolve_path("data.patterns"))
        self.embed = EmbeddingTier(cfg, registry)
        self.llm = LlmTier(cfg, registry)
        self.ph = Phraser(cfg)
        self.learn_uses = int(cfg.get("intent.learn_min_uses", 3))
        self.learn_conf = float(cfg.get("intent.learn_min_confidence", 0.9))
        # Do dac.
        self._counts = {0: 0, 1: 0, 2: 0, 3: 0}
        self._lat_sum = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}
        self._cache_hits = 0
        self._total = 0

    def resolve(self, text, room=None):
        """Phan giai mot cau noi -> Intent (da dien .tier va .latency_ms)."""
        t0 = time.perf_counter()
        text = (text or "").strip()
        if not text:
            return self._finish(Intent(intent="UNKNOWN", confidence=0.0,
                                       response_vi=self.ph.clarify()), 1, t0, text, room)

        # Tier 0 — cache.
        hit = self.cache.get(text, room)
        if hit:
            self._cache_hits += 1
            return self._finish(Intent(**hit), 0, t0, text, room)

        # Tier 1 — FST. UNKNOWN cua FST (vd hoi lai phong nao) van la tra loi hop le -> tra ngay,
        # nhung khong cache (phu thuoc ngu canh).
        it = self.fst.match(text, room)
        if it is not None:
            if it.intent != "UNKNOWN" and it.confidence >= _CACHE_MIN_CONF:
                self.cache.put(text, it.model_dump(), room)
            return self._finish(it, 1, t0, text, room)

        # Tier 2 — embedding.
        if self.embed.enabled:
            it = self.embed.match(text)
            if it is not None:
                if it.confidence >= _CACHE_MIN_CONF:
                    self.cache.put(text, it.model_dump(), room)
                return self._finish(it, 2, t0, text, room)

        # Tier 3 — LLM.
        it = self.llm.resolve(text, room)
        if it is None:
            # Ollama khong phan hoi -> xin loi nhe (giam cap muot ma).
            return self._finish(Intent(
                intent="UNKNOWN", confidence=0.0,
                response_vi="Dạ, xin lỗi, tôi đang xử lý hơi chậm. "
                            f"{self.ph.addr.capitalize()} thử lại giúp tôi được không ạ?"),
                3, t0, text, room)
        self._maybe_learn(text, room, it)
        return self._finish(it, 3, t0, text, room)

    # --- ho tro ---
    def _finish(self, intent, tier, t0, query, room):
        dt = (time.perf_counter() - t0) * 1000
        intent.tier = tier
        intent.latency_ms = round(dt, 1)
        if intent.room is None and room:
            intent.room = room
        self._counts[tier] += 1
        self._lat_sum[tier] += dt
        self._total += 1
        return intent

    def _maybe_learn(self, text, room, intent):
        """Tu hoc: dung du nhieu lan + tin cay cao -> day len cache (Tier 0)."""
        if intent.intent == "UNKNOWN" or intent.confidence < self.learn_conf:
            return
        uses = self.cache.bump_usage(text, room)
        if uses >= self.learn_uses:
            self.cache.put(text, intent.model_dump(), room)

    def metrics(self):
        avg = {f"tier{t}_avg_ms": round(self._lat_sum[t] / self._counts[t], 1)
               for t in self._counts if self._counts[t]}
        return {
            "total": self._total,
            "counts": {f"tier{t}": self._counts[t] for t in self._counts},
            "cache_hits": self._cache_hits,
            "cache_backend": self.cache.backend,
            "embedding_backend": self.embed.backend,
            **avg,
        }
