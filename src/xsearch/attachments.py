"""kintone プラグインから呼ばれる添付ファイルの保存先。

利用者は kintone の画面でファイルを選ぶだけで、ファイルは Dropbox 側に保存され、
レコードにはその場所（パスと URL）が書き戻される。kintone 側に実体を置かないので、
容量を気にせず、Dropbox 側の検索・取り込みの対象にも自動で入る。

実装は2つ。LocalAttachmentStore はフォルダに保存する（開発・テスト用）。
DropboxAttachmentStore は Dropbox API の files/upload を使う（実アカウントでは未検証）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

import httpx

_SAFE = re.compile(r"[^\w.\-ぁ-んァ-ヶ一-龥ー（）()]+")


def safe_filename(name: str) -> str:
    name = Path(name).name
    name = _SAFE.sub("_", name).strip("._") or "file"
    return name[:120]


class AttachmentStore(Protocol):
    def save(self, app_id: str, record_id: str, filename: str, data: bytes) -> dict[str, str]: ...


class LocalAttachmentStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save(self, app_id: str, record_id: str, filename: str, data: bytes) -> dict[str, str]:
        folder = self.root / f"app-{app_id}" / f"record-{record_id}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe_filename(filename)
        path.write_bytes(data)
        rel = path.relative_to(self.root).as_posix()
        return {"path": rel, "url": path.resolve().as_uri(), "backend": "local"}


class DropboxAttachmentStore:
    def __init__(
        self, access_token: str, root_path: str, client: httpx.Client | None = None
    ) -> None:
        self.token = access_token
        self.root = root_path.rstrip("/")
        self._client = client or httpx.Client(timeout=120.0)

    def save(self, app_id: str, record_id: str, filename: str, data: bytes) -> dict[str, str]:
        path = f"{self.root}/app-{app_id}/record-{record_id}/{safe_filename(filename)}"
        r = self._client.post(
            "https://content.dropboxapi.com/2/files/upload",
            content=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/octet-stream",
                "Dropbox-API-Arg": json.dumps({"path": path, "mode": "add", "autorename": True}),
            },
        )
        r.raise_for_status()
        saved = r.json()
        return {
            "path": saved.get("path_display", path),
            "url": f"https://www.dropbox.com/home{saved.get('path_display', path)}",
            "backend": "dropbox",
        }
