import httpx

from xsearch.embed import HashEmbedding, OllamaEmbedding
from xsearch.extract import extract_text
from xsearch.summarize import ExcerptSummarizer, OllamaSummarizer


def test_extract_docx_and_md(tmp_path):
    import docx

    d = docx.Document()
    d.add_paragraph("段落の本文")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "項目", "値"
    p = tmp_path / "x.docx"
    d.save(p)
    text = extract_text(p)
    assert "段落の本文" in text and "項目 | 値" in text
    md = tmp_path / "y.md"
    md.write_text("# 見出し\n本文", encoding="utf-8")
    assert extract_text(md) == "# 見出し\n本文"
    assert extract_text(tmp_path / "z.xyz", b"...") == ""


def test_excerpt_summarizer_collapses_whitespace_and_truncates():
    s = ExcerptSummarizer(max_chars=10)
    assert s.summarize("t", "あ  い\n\nう" * 10) == "あ い うあ い う…"
    assert s.summarize("タイトルだけ", "   ") == "タイトルだけ"


def test_ollama_summarizer_falls_back_on_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    s = OllamaSummarizer(
        "http://ollama", "m", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert s.summarize("T", "本文です") == "本文です"


def test_ollama_summarizer_uses_model_output():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": " 要約 "}})

    s = OllamaSummarizer(
        "http://ollama", "m", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert s.summarize("T", "本文") == "要約"


def test_hash_embedding_is_deterministic_and_normalized():
    e = HashEmbedding(dim=64)
    a, b = e.embed(["経費精算の締め日", "経費精算の締め日"])
    assert a == b and abs(sum(x * x for x in a) - 1.0) < 1e-6
    c = e.embed(["全く別の文章"])[0]
    dot_same = sum(x * y for x, y in zip(a, b, strict=True))
    dot_diff = sum(x * y for x, y in zip(a, c, strict=True))
    assert dot_same > dot_diff


def test_ollama_embedding_batches_and_sets_dim():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(req.content)
        seen.append(len(body["input"]))
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]] * len(body["input"])})

    e = OllamaEmbedding(
        "http://ollama", "bge-m3", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    out = e.embed([f"t{i}" for i in range(20)])
    assert len(out) == 20 and e.dim == 3 and seen == [16, 4]
