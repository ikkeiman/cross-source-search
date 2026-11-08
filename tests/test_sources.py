"""取り込み元の差分ロジック。kintone は同梱の偽サーバー、Dropbox は MockTransport で固定する。"""

import json
import time
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient
from tests.conftest import SAMPLE

from xsearch.sources.dropbox import DropboxSource
from xsearch.sources.fake_kintone import create_fake_kintone
from xsearch.sources.kintone import KintoneSource
from xsearch.sources.local_folder import LocalFolderSource


def kintone_against_fake() -> KintoneSource:
    # TestClient は同期の httpx.Client なので、KintoneSource にそのまま渡せる
    client = TestClient(create_fake_kintone(SAMPLE))
    return KintoneSource(
        "http://testserver", {}, ["1", "2", "3"], client=client, source_name="fake_kintone"
    )


def test_kintone_full_then_differential_returns_nothing_new():
    src = kintone_against_fake()
    changes, state = src.fetch_changes({})
    ups = [c for c in changes if c.op == "upsert"]
    assert len(ups) == 90
    item = ups[0].item
    assert item.id.startswith("fake_kintone:") and item.kind == "record"
    assert item.url.endswith(f"#record={item.source_id.split(':')[1]}")
    assert (
        "件名:" in item.text and item.title
    )  # 本文はフィールド名付き、タイトルは最初のテキスト項目
    assert set(state) >= {"since:1", "ids:1", "since:2", "since:3"}

    changes2, state2 = src.fetch_changes(state)
    assert changes2 == []
    assert state2["since:1"] == state["since:1"]


def test_kintone_full_run_emits_deletes_for_records_that_disappeared():
    src = kintone_against_fake()
    _, state = src.fetch_changes({})
    # 前回は存在したことにした架空の ID を state に足す → full で削除として出る
    state["ids:1"] = state["ids:1"] + ["fake_kintone:1:999"]
    changes, _ = src.fetch_changes(state, full=True)
    dels = [c.id for c in changes if c.op == "delete"]
    assert dels == ["fake_kintone:1:999"]


def test_local_folder_detects_add_modify_delete(tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    (root / "a.md").write_text("# A\n手順", encoding="utf-8")
    (root / "b.txt").write_text("B の内容", encoding="utf-8")
    (root / "skip.bin").write_bytes(b"\x00\x01")
    src = LocalFolderSource(root)

    changes, state = src.fetch_changes({})
    assert sorted(c.item.source_id for c in changes) == ["a.md", "b.txt"]

    changes, state = src.fetch_changes(state)
    assert changes == []

    time.sleep(1.1)  # mtime の秒精度
    (root / "a.md").write_text("# A\n手順を変更", encoding="utf-8")
    (root / "b.txt").unlink()
    changes, state = src.fetch_changes(state)
    ops = sorted((c.op, c.item.source_id if c.item else c.id) for c in changes)
    assert ops == [("delete", "local_folder:b.txt"), ("upsert", "a.md")]
    assert changes[0].item.text.endswith("手順を変更") if changes[0].op == "upsert" else True


def test_dropbox_uses_cursor_and_handles_deleted_entries():
    calls: list[tuple[str, dict]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else {}
        calls.append((req.url.path, body))
        if req.url.path == "/2/files/list_folder":
            return httpx.Response(
                200,
                json={
                    "entries": [
                        {
                            ".tag": "file",
                            "id": "id:1",
                            "path_lower": "/shared/a.md",
                            "path_display": "/shared/a.md",
                            "size": 10,
                            "server_modified": "2026-10-01T00:00:00Z",
                        },
                        {".tag": "folder", "path_lower": "/shared/sub"},
                    ],
                    "cursor": "c1",
                    "has_more": True,
                },
            )
        if req.url.path == "/2/files/list_folder/continue":
            if body["cursor"] == "c1":
                return httpx.Response(
                    200,
                    json={
                        "entries": [{".tag": "deleted", "path_lower": "/shared/old.txt"}],
                        "cursor": "c2",
                        "has_more": False,
                    },
                )
            return httpx.Response(200, json={"entries": [], "cursor": "c3", "has_more": False})
        if req.url.path == "/2/files/download":
            return httpx.Response(200, content="# A\n本文".encode())
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    src = DropboxSource("token", "/shared", client=client)
    changes, state = src.fetch_changes({})
    ops = [(c.op, c.item.source_id if c.item else c.id) for c in changes]
    assert ops == [("upsert", "/shared/a.md"), ("delete", "dropbox:/shared/old.txt")]
    assert changes[0].item.text == "# A\n本文"
    assert state == {"cursor": "c2"}

    # 2回目は保存した cursor から continue だけを呼ぶ
    calls.clear()
    changes2, state2 = src.fetch_changes(state)
    assert changes2 == [] and state2 == {"cursor": "c3"}
    assert [p for p, _ in calls] == ["/2/files/list_folder/continue"]
    assert calls[0][1] == {"cursor": "c2"}


def test_item_updated_at_is_timezone_aware():
    src = kintone_against_fake()
    changes, _ = src.fetch_changes({})
    dt = changes[0].item.updated_at
    assert isinstance(dt, datetime) and dt.tzinfo is not None and dt.astimezone(UTC)
