"""Dropbox API v2 からファイルを差分取り込みする。

差分: `files/list_folder` が返す cursor を state に保存し、次回は `files/list_folder/continue` で
変更分（追加・更新・削除）だけを受け取る。削除は `.tag == "deleted"` で届く。
本文は `files/download` で取得して extract_text に渡す。

注意: このソースは実アカウントで動作確認していない。HTTP の形は公式ドキュメントに合わせ、
カーソルの扱いは MockTransport によるテストで固定している。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import PurePosixPath

import httpx

from xsearch.extract import extract_text
from xsearch.models import Change, Item
from xsearch.sources.local_folder import SUPPORTED

API = "https://api.dropboxapi.com/2"
CONTENT = "https://content.dropboxapi.com/2"
MAX_DOWNLOAD = 20 * 1024 * 1024  # 20MB より大きいファイルは本文を読まずファイル名だけ


class DropboxSource:
    name = "dropbox"

    def __init__(
        self, access_token: str, root_path: str, client: httpx.Client | None = None
    ) -> None:
        self.token = access_token
        self.root = root_path if root_path != "/" else ""
        self._client = client or httpx.Client(timeout=60.0)

    def _post(self, url: str, body: dict) -> dict:
        r = self._client.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()

    def _download(self, path: str) -> bytes:
        r = self._client.post(
            f"{CONTENT}/files/download",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Dropbox-API-Arg": json.dumps({"path": path}),
            },
        )
        r.raise_for_status()
        return r.content

    def _entries(self, state: dict, full: bool) -> tuple[list[dict], str]:
        cursor = None if full else state.get("cursor")
        entries: list[dict] = []
        if cursor:
            data = self._post(f"{API}/files/list_folder/continue", {"cursor": cursor})
        else:
            data = self._post(
                f"{API}/files/list_folder",
                {"path": self.root, "recursive": True, "include_deleted": False},
            )
        entries.extend(data.get("entries", []))
        while data.get("has_more"):
            data = self._post(f"{API}/files/list_folder/continue", {"cursor": data["cursor"]})
            entries.extend(data.get("entries", []))
        return entries, data["cursor"]

    def fetch_changes(self, state: dict, *, full: bool = False) -> tuple[list[Change], dict]:
        entries, cursor = self._entries(state, full)
        changes: list[Change] = []
        for e in entries:
            tag = e.get(".tag")
            path = e.get("path_lower") or e.get("path_display", "")
            if tag == "deleted":
                changes.append(Change.delete(f"{self.name}:{path}"))
                continue
            if tag != "file":
                continue
            p = PurePosixPath(path)
            if p.suffix.lower() not in SUPPORTED:
                continue
            size = int(e.get("size", 0))
            text = ""
            if size <= MAX_DOWNLOAD:
                text = extract_text(p, self._download(e.get("id") or path))  # type: ignore[arg-type]
            updated = datetime.fromisoformat(e["server_modified"].replace("Z", "+00:00"))
            changes.append(
                Change.upsert(
                    Item(
                        id=f"{self.name}:{path}",
                        source=self.name,
                        source_id=path,
                        title=p.stem,
                        text=text,
                        url=f"https://www.dropbox.com/home{e.get('path_display', path)}",
                        updated_at=updated,
                        kind="file",
                        extra={"ext": p.suffix.lower().lstrip("."), "size": str(size)},
                    )
                )
            )
        return changes, {"cursor": cursor}
