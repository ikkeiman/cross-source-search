"""kintone REST API からレコードを差分取り込みする。

差分の取り方: アプリごとに「前回見た最大の更新日時」を state に持ち、
`更新日時 > "..."` の条件で、更新日時の昇順に 500 件ずつ取る。
削除されたレコードは API からは分からないので、full=True のときに全 ID を突き合わせて削除を出す。

同じクライアントが同梱の偽 kintone サーバー（fake_kintone.py）にもそのまま使える。
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from xsearch.models import Change, Item

PAGE = 500
SKIP_FIELD_TYPES = {"FILE", "SUBTABLE", "GROUP", "SPACER", "LABEL", "HR", "REFERENCE_TABLE"}


def _value_to_text(field: dict) -> str:
    t = field.get("type")
    v = field.get("value")
    if v in (None, "", []):
        return ""
    if t in ("CREATOR", "MODIFIER"):
        return str(v.get("name", "")) if isinstance(v, dict) else str(v)
    if t in ("USER_SELECT", "ORGANIZATION_SELECT", "GROUP_SELECT"):
        return ", ".join(str(x.get("name", "")) for x in v if isinstance(x, dict))
    if t in ("CHECK_BOX", "MULTI_SELECT", "CATEGORY"):
        return ", ".join(map(str, v))
    return str(v)


class KintoneSource:
    name = "kintone"

    def __init__(
        self,
        base_url: str,
        tokens: dict[str, str],
        app_ids: list[str],
        client: httpx.Client | None = None,
        source_name: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.tokens = tokens
        self.app_ids = app_ids
        self._client = client or httpx.Client(timeout=30.0)
        if source_name:
            self.name = source_name

    def _headers(self, app_id: str) -> dict[str, str]:
        token = self.tokens.get(app_id, "")
        return {"X-Cybozu-API-Token": token} if token else {}

    def _get(self, path: str, params: dict, app_id: str) -> dict:
        r = self._client.get(f"{self.base_url}{path}", params=params, headers=self._headers(app_id))
        r.raise_for_status()
        return r.json()

    def _app_name(self, app_id: str) -> str:
        try:
            return self._get("/k/v1/app.json", {"id": app_id}, app_id).get("name", f"app {app_id}")
        except httpx.HTTPError:
            return f"app {app_id}"

    def _records(self, app_id: str, query: str) -> list[dict]:
        out: list[dict] = []
        offset = 0
        while True:
            q = f"{query} order by 更新日時 asc limit {PAGE} offset {offset}".strip()
            data = self._get("/k/v1/records.json", {"app": app_id, "query": q}, app_id)
            records = data.get("records", [])
            out.extend(records)
            if len(records) < PAGE:
                return out
            offset += PAGE
            if (
                offset >= 10_000
            ):  # kintone の offset 上限。超えるアプリはカーソル API に切り替える必要がある
                return out

    def _to_item(self, app_id: str, app_name: str, rec: dict) -> Item:
        rid = str(rec["$id"]["value"])
        updated = datetime.fromisoformat(rec["更新日時"]["value"].replace("Z", "+00:00"))
        lines: list[str] = []
        title = ""
        for code, field in rec.items():
            if (
                code in ("$id", "$revision", "更新日時", "作成日時")
                or field.get("type") in SKIP_FIELD_TYPES
            ):
                continue
            text = _value_to_text(field)
            if not text:
                continue
            if not title and field.get("type") in ("SINGLE_LINE_TEXT", "RICH_TEXT"):
                title = text[:60]
            lines.append(f"{code}: {text}")
        return Item(
            id=f"{self.name}:{app_id}:{rid}",
            source=self.name,
            source_id=f"{app_id}:{rid}",
            title=title or f"{app_name} #{rid}",
            text="\n".join(lines),
            url=f"{self.base_url}/k/{app_id}/show#record={rid}",
            updated_at=updated,
            kind="record",
            extra={"app": app_name, "app_id": app_id},
        )

    def fetch_changes(self, state: dict, *, full: bool = False) -> tuple[list[Change], dict]:
        new_state = dict(state)
        changes: list[Change] = []
        for app_id in self.app_ids:
            app_name = self._app_name(app_id)
            since = None if full else state.get(f"since:{app_id}")
            query = f'更新日時 > "{since}"' if since else ""
            records = self._records(app_id, query)
            seen_ids: set[str] = set()
            max_updated = since
            for rec in records:
                item = self._to_item(app_id, app_name, rec)
                changes.append(Change.upsert(item))
                seen_ids.add(item.id)
                iso = item.updated_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                if max_updated is None or iso > max_updated:
                    max_updated = iso
            if full:
                # 全件取得のときだけ、前回までに見た ID で今回無いものを削除として出す
                previous = set(state.get(f"ids:{app_id}", []))
                for gone in previous - seen_ids:
                    changes.append(Change.delete(gone))
                new_state[f"ids:{app_id}"] = sorted(seen_ids)
            else:
                known = set(state.get(f"ids:{app_id}", [])) | seen_ids
                new_state[f"ids:{app_id}"] = sorted(known)
            if max_updated:
                new_state[f"since:{app_id}"] = max_updated
        return changes, new_state
