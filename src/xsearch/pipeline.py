"""取り込みパイプライン。各 Source の差分を取り、要約して埋め込み、ChromaDB に反映する。

state は data/state.json に保存し、次回の差分取り込みに使う。
実行ごとの件数と所要時間を返し、ログに残す。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from xsearch.config import Settings
from xsearch.embed import Embedding, pick_embedding
from xsearch.models import Change, Item
from xsearch.sources.base import Source
from xsearch.store import SearchStore
from xsearch.summarize import Summarizer, pick_summarizer

BATCH = 32


@dataclass
class IngestReport:
    started_at: str
    finished_at: str = ""
    full: bool = False
    summarizer: str = ""
    embedding: str = ""
    per_source: dict[str, dict] = field(default_factory=dict)
    upserted: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0


def load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_sources(settings: Settings) -> list[Source]:
    from xsearch.sources.dropbox import DropboxSource
    from xsearch.sources.kintone import KintoneSource
    from xsearch.sources.local_folder import LocalFolderSource

    out: list[Source] = []
    for name in settings.sources:
        if name == "fake_kintone":
            out.append(
                KintoneSource(
                    settings.fake_kintone_url, {}, ["1", "2", "3"], source_name="fake_kintone"
                )
            )
        elif name == "kintone":
            out.append(
                KintoneSource(
                    settings.kintone_base_url, settings.kintone_api_tokens, settings.kintone_app_ids
                )
            )
        elif name == "local_folder":
            out.append(LocalFolderSource(settings.local_folder_path))
        elif name == "dropbox":
            out.append(DropboxSource(settings.dropbox_access_token, settings.dropbox_root_path))
        else:
            raise ValueError(f"未知の取り込み元: {name}")
    return out


def ingest(
    settings: Settings,
    *,
    full: bool = False,
    sources: list[Source] | None = None,
    store: SearchStore | None = None,
    summarizer: Summarizer | None = None,
    embedding: Embedding | None = None,
) -> IngestReport:
    t0 = time.perf_counter()
    report = IngestReport(started_at=datetime.now(UTC).isoformat(timespec="seconds"), full=full)
    sources = sources if sources is not None else build_sources(settings)
    store = store or SearchStore(settings.data_dir)
    summarizer = summarizer or pick_summarizer(settings.ollama_base_url, settings.summary_model)
    embedding = embedding or pick_embedding(settings.ollama_base_url, settings.embed_model)
    report.summarizer, report.embedding = summarizer.mode, embedding.mode

    state_path = settings.data_dir / "state.json"
    state = load_state(state_path)

    for src in sources:
        ts = time.perf_counter()
        try:
            changes, new_state = src.fetch_changes(state.get(src.name, {}), full=full)
        except Exception as e:  # 1 つの取り込み元の失敗で他を止めない
            report.errors.append(f"{src.name}: {type(e).__name__}: {e}")
            continue
        ups = [c.item for c in changes if c.op == "upsert" and c.item is not None]
        dels = [c.id for c in changes if c.op == "delete" and c.id]
        _apply_upserts(store, summarizer, embedding, ups)
        store.delete(dels)
        state[src.name] = new_state
        save_state(state_path, state)  # 取り込み元ごとに保存。途中で落ちてもやり直しが最小で済む
        report.per_source[src.name] = {
            "upserted": len(ups),
            "deleted": len(dels),
            "seconds": round(time.perf_counter() - ts, 2),
        }
        report.upserted += len(ups)
        report.deleted += len(dels)

    report.seconds = round(time.perf_counter() - t0, 2)
    report.finished_at = datetime.now(UTC).isoformat(timespec="seconds")
    _append_log(settings.data_dir / "ingest_log.jsonl", report)
    return report


def _apply_upserts(
    store: SearchStore, summarizer: Summarizer, embedding: Embedding, items: list[Item]
) -> None:
    for i in range(0, len(items), BATCH):
        batch = items[i : i + BATCH]
        summaries = [summarizer.summarize(it.title, it.text) for it in batch]
        vectors = embedding.embed(
            [f"{it.title}\n{s}" for it, s in zip(batch, summaries, strict=True)]
        )
        store.upsert(batch, summaries, vectors)


def _append_log(path: Path, report: IngestReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report.__dict__, ensure_ascii=False) + "\n")


def apply_changes_for_test(
    store: SearchStore, changes: list[Change], summarizer: Summarizer, embedding: Embedding
) -> None:
    """テスト用の補助。Source を介さずに Change の列を反映する。"""
    ups = [c.item for c in changes if c.op == "upsert" and c.item is not None]
    _apply_upserts(store, summarizer, embedding, ups)
    store.delete([c.id for c in changes if c.op == "delete" and c.id])
