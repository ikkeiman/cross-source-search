"""ローカルフォルダを取り込み元にする。Dropbox の代わりに、鍵なしで動かすためのもの。

差分: state にファイルごとの更新時刻（mtime）とサイズを持ち、変わったものだけ upsert、
消えたものは delete。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from xsearch.extract import extract_text
from xsearch.models import Change, Item

SUPPORTED = {".txt", ".md", ".csv", ".log", ".docx", ".pdf"}


class LocalFolderSource:
    name = "local_folder"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def fetch_changes(self, state: dict, *, full: bool = False) -> tuple[list[Change], dict]:
        previous: dict[str, str] = {} if full else dict(state.get("files", {}))
        current: dict[str, str] = {}
        changes: list[Change] = []
        if self.root.exists():
            for path in sorted(p for p in self.root.rglob("*") if p.is_file()):
                if path.suffix.lower() not in SUPPORTED or path.name.startswith("."):
                    continue
                rel = path.relative_to(self.root).as_posix()
                st = path.stat()
                sig = f"{int(st.st_mtime)}:{st.st_size}"
                current[rel] = sig
                if previous.get(rel) == sig:
                    continue
                changes.append(
                    Change.upsert(
                        Item(
                            id=f"{self.name}:{rel}",
                            source=self.name,
                            source_id=rel,
                            title=path.stem,
                            text=extract_text(path),
                            url=path.resolve().as_uri(),
                            updated_at=datetime.fromtimestamp(st.st_mtime, tz=UTC),
                            kind="file",
                            extra={"ext": path.suffix.lower().lstrip(".")},
                        )
                    )
                )
        for rel in set(state.get("files", {})) - set(current):
            changes.append(Change.delete(f"{self.name}:{rel}"))
        return changes, {"files": current}
