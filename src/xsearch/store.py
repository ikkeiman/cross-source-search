"""ChromaDB への格納と検索。

1 件 1 ドキュメント。document には要約、metadata に出典（source・URL・更新日時・
種類）と短い抜粋を持つ。
本文の全文は持たない。埋め込みはこちらで計算して渡す
（埋め込みモデルの切り替えを DB 側に依存させないため）。
検索はベクトルの近さで取り、クエリ語をタイトルか要約に含むものを少し持ち上げる（意味検索とキーワードの併用）。
"""

from __future__ import annotations

from pathlib import Path

import chromadb

from xsearch.models import Hit, Item

EXCERPT_CHARS = 300


class SearchStore:
    def __init__(self, data_dir: Path, collection: str = "documents") -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(data_dir / "chroma"))
        self._col = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def count(self) -> int:
        return self._col.count()

    def upsert(
        self, items: list[Item], summaries: list[str], embeddings: list[list[float]]
    ) -> None:
        if not items:
            return
        self._col.upsert(
            ids=[it.id for it in items],
            documents=summaries,
            embeddings=embeddings,
            metadatas=[
                {
                    "source": it.source,
                    "title": it.title,
                    "url": it.url,
                    "updated_at": it.updated_at.isoformat(),
                    "kind": it.kind,
                    "excerpt": it.text[:EXCERPT_CHARS],
                    **{f"x_{k}": v for k, v in it.extra.items()},
                }
                for it in items
            ],
        )

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._col.delete(ids=ids)

    def search(
        self, query: str, query_embedding: list[float], n: int = 10, source: str | None = None
    ) -> list[Hit]:
        if self._col.count() == 0:
            return []
        where = {"source": source} if source else None
        res = self._col.query(
            query_embeddings=[query_embedding],
            n_results=min(max(n * 2, 10), self._col.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        terms = [t for t in query.replace("　", " ").split() if t]
        hits: list[Hit] = []
        for id_, doc, meta, dist in zip(
            res["ids"][0],
            res["documents"][0],
            res["metadatas"][0],
            res["distances"][0],
            strict=True,
        ):
            score = 1.0 - float(dist)  # cosine 距離 → 類似度
            hay = f"{meta.get('title', '')} {doc} {meta.get('excerpt', '')}"
            kw = bool(terms) and all(t in hay for t in terms)
            if kw:
                score += 0.15
            hits.append(
                Hit(
                    id=id_,
                    source=str(meta.get("source", "")),
                    title=str(meta.get("title", "")),
                    summary=doc or "",
                    url=str(meta.get("url", "")),
                    updated_at=str(meta.get("updated_at", "")),
                    kind=str(meta.get("kind", "")),
                    score=round(score, 4),
                    keyword_match=kw,
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:n]
