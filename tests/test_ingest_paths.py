from pathlib import Path

from app.api.documents import _resolve_ingest_path
from app.config import get_settings


def test_resolve_configured_host_file_url_to_container_mount(monkeypatch) -> None:
    monkeypatch.setenv("HOST_MOUNT_SOURCE_PREFIX", "/Users/example/Downloads")
    get_settings.cache_clear()

    resolved = _resolve_ingest_path(
        "file:///Users/example/Downloads/learning-path/books/AI_Russell_Norvig.pdf"
    )

    assert resolved == Path("/host-downloads/learning-path/books/AI_Russell_Norvig.pdf")
    get_settings.cache_clear()


def test_resolve_container_path_without_change() -> None:
    assert _resolve_ingest_path("/data/ingest/sample.pdf") == Path("/data/ingest/sample.pdf")
