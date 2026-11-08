from datetime import UTC, datetime

import httpx
import pytest

from xsearch.api import create_app
from xsearch.attachments import LocalAttachmentStore, safe_filename
from xsearch.config import Settings
from xsearch.models import Change, Item
from xsearch.pipeline import apply_changes_for_test, ingest
from xsearch.sources.local_folder import LocalFolderSource


def item(i: str, title: str, text: str, source="fake_kintone") -> Item:
    return Item(
        id=f"{source}:{i}",
        source=source,
        source_id=i,
        title=title,
        text=text,
        url=f"http://x/{i}",
        updated_at=datetime(2026, 10, 1, tzinfo=UTC),
        kind="record",
    )


def test_store_upsert_search_delete(store, embedding, summarizer):
    changes = [
        Change.upsert(item("1", "経費精算の締め日", "経費精算の締め日を月末に変更する")),
        Change.upsert(item("2", "会議室の予約", "会議室の予約ルールを見直す")),
        Change.upsert(item("f1", "在宅勤務 手順書", "在宅勤務の申請手順", source="local_folder")),
    ]
    apply_changes_for_test(store, changes, summarizer, embedding)
    assert store.count() == 3

    hits = store.search("経費精算 締め日", embedding.embed(["経費精算 締め日"])[0], n=3)
    assert hits[0].id == "fake_kintone:1" and hits[0].keyword_match is True
    assert "excerpt" not in hits[0].model_dump()  # 本文全文は返さない

    only_files = store.search("申請", embedding.embed(["申請"])[0], n=3, source="local_folder")
    assert [h.source for h in only_files] == ["local_folder"]

    store.delete(["fake_kintone:1"])
    assert store.count() == 2
    # 同じ id の upsert は置き換え
    apply_changes_for_test(
        store, [Change.upsert(item("2", "会議室の予約（改）", "新しい本文"))], summarizer, embedding
    )
    assert store.count() == 2
    assert (
        store.search("会議室", embedding.embed(["会議室"])[0], n=1)[0].title == "会議室の予約（改）"
    )


def test_pipeline_ingest_saves_state_and_log(tmp_path, store, embedding, summarizer):
    root = tmp_path / "files"
    root.mkdir()
    (root / "a.md").write_text("# 備品の棚卸し\n年1回にする", encoding="utf-8")
    settings = Settings(
        sources=["local_folder"], local_folder_path=root, data_dir=tmp_path / "data"
    )
    src = LocalFolderSource(root)

    r1 = ingest(settings, sources=[src], store=store, summarizer=summarizer, embedding=embedding)
    assert r1.upserted == 1 and r1.deleted == 0 and r1.errors == []
    assert r1.summarizer == "excerpt" and r1.embedding == "hash"
    assert (tmp_path / "data" / "state.json").exists()
    assert (tmp_path / "data" / "ingest_log.jsonl").read_text(encoding="utf-8").count("\n") == 1

    r2 = ingest(settings, sources=[src], store=store, summarizer=summarizer, embedding=embedding)
    assert r2.upserted == 0 and store.count() == 1


def test_pipeline_isolates_source_failures(tmp_path, store, embedding, summarizer):
    class Broken:
        name = "broken"

        def fetch_changes(self, state, *, full=False):
            raise RuntimeError("接続できない")

    root = tmp_path / "files"
    root.mkdir()
    (root / "a.txt").write_text("x", encoding="utf-8")
    settings = Settings(sources=[], data_dir=tmp_path / "data")
    r = ingest(
        settings,
        sources=[Broken(), LocalFolderSource(root)],
        store=store,
        summarizer=summarizer,
        embedding=embedding,
    )
    assert r.errors == ["broken: RuntimeError: 接続できない"]
    assert r.upserted == 1  # 壊れた取り込み元があっても他は進む


@pytest.fixture
async def client(tmp_path, store, embedding, summarizer):
    apply_changes_for_test(
        store,
        [
            Change.upsert(
                item("1", "複合機の更新", "複合機のリース更新に合わせてスキャン保存先を見直す")
            )
        ],
        summarizer,
        embedding,
    )
    settings = Settings(sources=["local_folder"], data_dir=tmp_path / "data")
    app = create_app(
        settings,
        store=store,
        embedding=embedding,
        attachments=LocalAttachmentStore(tmp_path / "att"),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_api_search_health_and_index(client):
    r = await client.get("/healthz")
    assert r.status_code == 200 and r.json()["documents"] == 1 and r.json()["embedding"] == "hash"
    r = await client.get("/search", params={"q": "複合機 スキャン"})
    hits = r.json()
    assert hits[0]["title"] == "複合機の更新" and hits[0]["keyword_match"] is True
    assert (await client.get("/search", params={"q": ""})).status_code == 422
    r = await client.get("/")
    assert r.status_code == 200 and "社内検索" in r.text


async def test_api_attachments_saves_file_and_returns_location(client, tmp_path):
    r = await client.post(
        "/attachments",
        data={"app_id": "3", "record_id": "7"},
        files={"file": ("見積書 2026-10.pdf", b"%PDF-1.4 ...", "application/pdf")},
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] and body["backend"] == "local"
    assert body["path"] == "app-3/record-7/見積書_2026-10.pdf"
    assert (tmp_path / "att" / body["path"]).read_bytes().startswith(b"%PDF")


def test_safe_filename_strips_paths_and_odd_characters():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("請求書（10月）.pdf") == "請求書（10月）.pdf"
    assert safe_filename("a b:c*d.txt") == "a_b_c_d.txt"
    assert safe_filename("dir/sub/名前.txt") == "名前.txt"
