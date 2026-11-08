"""コマンド。

python -m xsearch fake-kintone          偽 kintone サーバーを起動（:8002）
python -m xsearch ingest [--full]       差分取り込み（--full は全件＋削除の突き合わせ）
python -m xsearch search "検索語"        コマンドラインで検索
python -m xsearch serve                 検索 API と画面を起動（:8000）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xsearch.config import Settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="xsearch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_fake = sub.add_parser("fake-kintone")
    p_fake.add_argument("--port", type=int, default=8002)
    p_fake.add_argument("--host", default="127.0.0.1")
    p_fake.add_argument("--data", default="sample_data/kintone_records.json")
    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--full", action="store_true")
    p_s = sub.add_parser("search")
    p_s.add_argument("query")
    p_s.add_argument("-n", type=int, default=5)
    p_s.add_argument("--source")
    p_srv = sub.add_parser("serve")
    p_srv.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    settings = Settings.from_env()

    if args.cmd == "fake-kintone":
        import uvicorn

        from xsearch.sources.fake_kintone import create_fake_kintone

        uvicorn.run(create_fake_kintone(Path(args.data)), host=args.host, port=args.port)
        return 0
    if args.cmd == "ingest":
        from xsearch.pipeline import ingest

        report = ingest(settings, full=args.full)
        print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
        return 1 if report.errors else 0
    if args.cmd == "search":
        from xsearch.embed import pick_embedding
        from xsearch.store import SearchStore

        store = SearchStore(settings.data_dir)
        emb = pick_embedding(settings.ollama_base_url, settings.embed_model)
        vec = emb.embed([args.query])[0]
        for h in store.search(args.query, vec, n=args.n, source=args.source):
            flag = " [語一致]" if h.keyword_match else ""
            print(f"{h.score:.3f} {h.source:12s} {h.title}{flag}")
            print(f"      {h.summary[:90]}")
            print(f"      {h.url}")
        return 0
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("xsearch.api:app", host="0.0.0.0", port=args.port)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
