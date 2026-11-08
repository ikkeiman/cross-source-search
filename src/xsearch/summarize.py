"""要約。ローカル LLM（Ollama）で 200 字前後の要約を作る。届かなければ先頭の抜粋で代替し、
どちらを使ったかを残す。

検索に載せるのは本文ではなく要約（と短い抜粋）なので、ベクトル DB 側に本文の全文を持たない。
"""

from __future__ import annotations

import re
import time
from typing import Protocol

import httpx

PROMPT = (
    "次の社内文書を、検索結果の一覧で内容が分かるように日本語で要約してください。"
    "200字以内。見出しや箇条書きは使わず、1〜3文で。固有名詞と数字は残してください。\n\n"
    "タイトル: {title}\n本文:\n{text}"
)

_WS = re.compile(r"\s+")


class Summarizer(Protocol):
    mode: str

    def summarize(self, title: str, text: str) -> str: ...


class ExcerptSummarizer:
    """LLM が使えないときの代替。本文の先頭を整形して返す。"""

    mode = "excerpt"

    def __init__(self, max_chars: int = 200) -> None:
        self.max_chars = max_chars

    def summarize(self, title: str, text: str) -> str:
        flat = _WS.sub(" ", text).strip()
        if not flat:
            return title
        return flat[: self.max_chars] + ("…" if len(flat) > self.max_chars else "")


class OllamaSummarizer:
    mode = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 60.0,
        max_input_chars: int = 6000,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds
        self.max_input_chars = max_input_chars
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._fallback = ExcerptSummarizer()
        self._reachable: bool | None = None
        self._checked = 0.0

    def reachable(self) -> bool:
        now = time.monotonic()
        if self._reachable is not None and now - self._checked < 30:
            return self._reachable
        try:
            self._reachable = (
                self._client.get(f"{self.base_url}/api/tags", timeout=2.0).status_code == 200
            )
        except httpx.HTTPError:
            self._reachable = False
        self._checked = now
        return self._reachable

    def summarize(self, title: str, text: str) -> str:
        if not text.strip():
            return title
        try:
            r = self._client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": PROMPT.format(
                                title=title, text=text[: self.max_input_chars]
                            ),
                        }
                    ],
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 220},
                    "keep_alive": "10m",
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            content = r.json().get("message", {}).get("content", "").strip()
            return content or self._fallback.summarize(title, text)
        except (httpx.HTTPError, ValueError):
            return self._fallback.summarize(title, text)


def pick_summarizer(base_url: str, model: str) -> Summarizer:
    s = OllamaSummarizer(base_url, model)
    return s if s.reachable() else ExcerptSummarizer()
