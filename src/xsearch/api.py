"""検索 API と、ポータルの検索窓を模した 1 枚の画面。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from xsearch import __version__
from xsearch.attachments import AttachmentStore, DropboxAttachmentStore, LocalAttachmentStore
from xsearch.config import Settings
from xsearch.embed import Embedding, pick_embedding
from xsearch.models import Hit
from xsearch.pipeline import ingest, load_state
from xsearch.store import SearchStore

STATIC = Path(__file__).parent / "static"


def create_app(
    settings: Settings | None = None,
    *,
    store: SearchStore | None = None,
    embedding: Embedding | None = None,
    attachments: AttachmentStore | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or SearchStore(settings.data_dir)
    embedding = embedding or pick_embedding(settings.ollama_base_url, settings.embed_model)
    if attachments is None:
        attachments = (
            DropboxAttachmentStore(settings.dropbox_access_token, settings.dropbox_root_path)
            if settings.dropbox_access_token
            else LocalAttachmentStore(settings.data_dir / "attachments")
        )

    app = FastAPI(title="cross-source-search", version=__version__)
    app.state.store = store

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/healthz")
    def healthz() -> dict:
        log = settings.data_dir / "ingest_log.jsonl"
        last = None
        if log.exists():
            lines = log.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
        return {
            "status": "ok",
            "version": __version__,
            "documents": store.count(),
            "embedding": embedding.mode,
            "sources": settings.sources,
            "last_ingest": last,
            "state_keys": sorted(load_state(settings.data_dir / "state.json").keys()),
        }

    @app.get("/search", response_model=list[Hit])
    def search(
        q: str = Query(min_length=1, max_length=200),
        n: int = Query(10, ge=1, le=50),
        source: str | None = None,
    ) -> list[Hit]:
        vec = embedding.embed([q])[0]
        return store.search(q, vec, n=n, source=source)

    @app.post("/ingest")
    def run_ingest(full: bool = False) -> dict:
        report = ingest(settings, full=full, store=store, embedding=embedding)
        return report.__dict__

    @app.post("/attachments")
    async def upload(
        app_id: str = Form(...), record_id: str = Form(...), file: UploadFile = File(...)
    ) -> JSONResponse:
        data = await file.read()
        if len(data) > 50 * 1024 * 1024:
            return JSONResponse({"error": "50MB を超えるファイルは受け付けません"}, status_code=413)
        saved = attachments.save(app_id, record_id, file.filename or "file", data)
        return JSONResponse({"ok": True, **saved, "size": len(data)})

    return app


app = create_app()
