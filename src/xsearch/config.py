from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    sources: list[str] = field(default_factory=lambda: ["fake_kintone", "local_folder"])
    # kintone
    kintone_base_url: str = ""
    kintone_api_tokens: dict[str, str] = field(default_factory=dict)  # app_id -> token
    kintone_app_ids: list[str] = field(default_factory=list)
    # dropbox
    dropbox_access_token: str = ""
    dropbox_root_path: str = "/shared"
    # 鍵なしで動かすための代替
    fake_kintone_url: str = "http://127.0.0.1:8002"
    local_folder_path: Path = field(default_factory=lambda: Path("sample_data/files"))
    # LLM
    ollama_base_url: str = "http://localhost:11434"
    summary_model: str = "qwen2.5:7b-instruct"
    embed_model: str = "bge-m3"
    # 保存先
    data_dir: Path = field(default_factory=lambda: Path("data"))

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        tokens: dict[str, str] = {}
        for pair in filter(None, env("KINTONE_API_TOKENS", "").split(",")):
            app, _, token = pair.partition(":")
            if app and token:
                tokens[app.strip()] = token.strip()
        return cls(
            sources=[
                s.strip() for s in env("SOURCES", "fake_kintone,local_folder").split(",") if s
            ],
            kintone_base_url=env("KINTONE_BASE_URL", "").rstrip("/"),
            kintone_api_tokens=tokens,
            kintone_app_ids=[a.strip() for a in env("KINTONE_APP_IDS", "").split(",") if a.strip()],
            dropbox_access_token=env("DROPBOX_ACCESS_TOKEN", ""),
            dropbox_root_path=env("DROPBOX_ROOT_PATH", "/shared"),
            fake_kintone_url=env("FAKE_KINTONE_URL", "http://127.0.0.1:8002").rstrip("/"),
            local_folder_path=Path(env("LOCAL_FOLDER_PATH", "sample_data/files")),
            ollama_base_url=env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
            summary_model=env("SUMMARY_MODEL", "qwen2.5:7b-instruct"),
            embed_model=env("EMBED_MODEL", "bge-m3"),
            data_dir=Path(env("DATA_DIR", "data")),
        )
