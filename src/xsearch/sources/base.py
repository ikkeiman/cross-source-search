"""取り込み元の共通インターフェース。

差分取り込みの肝は state。前回の実行で保存した state（更新日時、カーソル、ファイルの mtime など）を
渡すと、そこからの変更だけを Change の列で返し、次回のための新しい state を返す。
保管場所ごとの差分の取り方の違いは、この中に閉じ込める。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from xsearch.models import Change


@runtime_checkable
class Source(Protocol):
    name: str

    def fetch_changes(self, state: dict, *, full: bool = False) -> tuple[list[Change], dict]:
        """state から後の変更を返す。

        full=True なら全件を upsert として返す（削除の突き合わせにも使う）。
        """
        ...
