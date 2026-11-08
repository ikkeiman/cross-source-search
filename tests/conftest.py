from pathlib import Path

import pytest

from xsearch.embed import HashEmbedding
from xsearch.store import SearchStore
from xsearch.summarize import ExcerptSummarizer

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample_data" / "kintone_records.json"


@pytest.fixture
def store(tmp_path):
    return SearchStore(tmp_path / "data")


@pytest.fixture
def embedding():
    return HashEmbedding()


@pytest.fixture
def summarizer():
    return ExcerptSummarizer()
