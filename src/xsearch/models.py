"""取り込みの共通データ型。どの保管場所から来ても Item に揃える。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Item(BaseModel):
    id: str  # "<source>:<source_id>"。ChromaDB の id になる
    source: str  # kintone / dropbox / local_folder / fake_kintone
    source_id: str
    title: str
    text: str  # 要約・抜粋の元になる本文
    url: str  # 元の場所へ戻るためのリンク（kintone のレコード URL、Dropbox のパスなど）
    updated_at: datetime
    kind: str = "document"  # record / file
    extra: dict[str, str] = Field(default_factory=dict)


class Change(BaseModel):
    op: Literal["upsert", "delete"]
    item: Item | None = None
    id: str | None = None

    @classmethod
    def upsert(cls, item: Item) -> Change:
        return cls(op="upsert", item=item)

    @classmethod
    def delete(cls, item_id: str) -> Change:
        return cls(op="delete", id=item_id)


class Hit(BaseModel):
    id: str
    source: str
    title: str
    summary: str
    url: str
    updated_at: str
    kind: str
    score: float
    keyword_match: bool = False
