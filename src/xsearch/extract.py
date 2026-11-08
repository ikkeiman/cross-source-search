"""ファイルから本文テキストを取り出す。

対応: .txt .md .csv .docx .pdf。他は空文字（ファイル名だけで検索対象にする）。
"""

from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = {".txt", ".md", ".csv", ".log"}
MAX_CHARS = 20_000  # 要約に渡す上限。長い文書は先頭だけ


def extract_text(path: Path, data: bytes | None = None) -> str:
    suffix = path.suffix.lower()
    raw = data if data is not None else path.read_bytes()
    try:
        if suffix in TEXT_SUFFIXES:
            text = raw.decode("utf-8", errors="replace")
        elif suffix == ".docx":
            text = _docx(raw)
        elif suffix == ".pdf":
            text = _pdf(raw)
        else:
            text = ""
    except Exception as e:  # 壊れたファイルで取り込み全体を止めない
        text = f"（本文を読めませんでした: {type(e).__name__}）"
    return text[:MAX_CHARS]


def _docx(raw: bytes) -> str:
    import io

    import docx

    d = docx.Document(io.BytesIO(raw))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _pdf(raw: bytes) -> str:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((page.extract_text() or "") for page in reader.pages)
