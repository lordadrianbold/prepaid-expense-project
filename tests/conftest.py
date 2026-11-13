import pytest


@pytest.fixture(autouse=True)
def _no_disk_cache(monkeypatch, tmp_path):
    """Tests must never read or write the real .llm_cache."""
    monkeypatch.setenv("P6_NO_CACHE", "1")




    