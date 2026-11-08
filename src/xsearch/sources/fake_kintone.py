"""kintone REST API の最小の偽物。鍵も契約も無しで、取り込みの流れを動かすためのもの。

対応するのは KintoneSource が使う 2 つだけ:
- GET /k/v1/app.json?id=
- GET /k/v1/records.json?app=&query=
  （`更新日時 > "..."` と `order by 更新日時 asc limit N offset M` だけ解釈）

データは sample_data/kintone_records.json（合成データ）。起動: python -m xsearch fake-kintone
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

_SINCE = re.compile(r'更新日時\s*>\s*"([^"]+)"')
_LIMIT = re.compile(r"limit\s+(\d+)")
_OFFSET = re.compile(r"offset\s+(\d+)")


def load_sample(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def create_fake_kintone(sample_path: Path, base_url: str = "http://127.0.0.1:8002") -> FastAPI:
    data = load_sample(sample_path)
    apps: dict[str, dict] = {a["appId"]: a for a in data["apps"]}
    app = FastAPI(title="fake-kintone")
    app.state.apps = apps

    @app.get("/k/v1/app.json")
    def get_app(id: str = Query(...)) -> dict:
        if id not in apps:
            raise HTTPException(404, "app not found")
        return {"appId": id, "name": apps[id]["name"]}

    @app.get("/k/v1/records.json")
    def get_records(app: str = Query(...), query: str = "") -> dict:
        if app not in apps:
            raise HTTPException(404, "app not found")
        records = list(apps[app]["records"])
        m = _SINCE.search(query)
        if m:
            since = m.group(1)
            records = [r for r in records if r["更新日時"]["value"] > since]
        records.sort(key=lambda r: r["更新日時"]["value"])
        limit = int(_LIMIT.search(query).group(1)) if _LIMIT.search(query) else 100
        offset = int(_OFFSET.search(query).group(1)) if _OFFSET.search(query) else 0
        return {"records": records[offset : offset + limit], "totalCount": str(len(records))}

    return app
