"""埋め込み。Ollama の多言語モデル（既定 bge-m3）を使う。

Ollama が無い環境（CI、テスト）では、文字 2-gram をハッシュで固定次元に落とす
決定的な埋め込みで代替する。
意味は捉えないが、同じ語を含む文書は近くなるので、パイプラインの動作確認には足りる。
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Protocol

import httpx


class Embedding(Protocol):
    mode: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedding:
    mode = "hash"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        t = text.replace("\n", " ")
        grams = [t[i : i + 2] for i in range(max(len(t) - 1, 0))] or [t]
        for g in grams:
            h = int.from_bytes(hashlib.blake2b(g.encode("utf-8"), digest_size=4).digest(), "big")
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OllamaEmbedding:
    mode = "ollama"

    def __init__(
        self, base_url: str, model: str, client: httpx.Client | None = None, dim: int = 0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim  # 初回の呼び出しで確定
        self._client = client or httpx.Client(timeout=120.0)
        self._reachable: bool | None = None
        self._checked = 0.0

    def reachable(self) -> bool:
        now = time.monotonic()
        if self._reachable is not None and now - self._checked < 30:
            return self._reachable
        try:
            self._reachable = (
                self._client.get(f"{self.base_url}/api/tags", timeout=2.0).status_code == 200
            )
        except httpx.HTTPError:
            self._reachable = False
        self._checked = now
        return self._reachable

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 16):
            batch = texts[i : i + 16]
            r = self._client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": batch, "keep_alive": "10m"},
            )
            r.raise_for_status()
            vectors = r.json()["embeddings"]
            out.extend(vectors)
        if out and not self.dim:
            self.dim = len(out[0])
        return out


def pick_embedding(base_url: str, model: str) -> Embedding:
    e = OllamaEmbedding(base_url, model)
    return e if e.reachable() else HashEmbedding()
