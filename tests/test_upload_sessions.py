from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from uuid import UUID

from app.config import get_settings
from app.rag.upload_sessions import cleanup_stale_upload_sessions, create_upload_session, save_upload_part


class FakeUploadFile:
    def __init__(self, content: bytes) -> None:
        self.file = BytesIO(content)


def test_stale_filesystem_upload_sessions_are_removed(tmp_path, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "upload_session_storage_backend", "filesystem")
    session = create_upload_session(
        tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
        uploaded_by="subject",
        file_name="stale.txt",
        byte_size=5,
        visibility="tenant",
        allowed_role_names=[],
        force_ocr=False,
    )
    save_upload_part(session.upload_session_id, 1, FakeUploadFile(b"stale"))
    manifest = tmp_path / "sessions" / str(session.upload_session_id) / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    manifest.write_text(json.dumps(data), encoding="utf-8")

    result = cleanup_stale_upload_sessions(max_age_hours=1)

    assert result.sessions_removed == 1
    assert result.parts_removed == 1
    assert result.bytes_removed == 5
    assert not manifest.parent.exists()


def test_stale_minio_upload_sessions_remove_objects(tmp_path, monkeypatch) -> None:
    import app.rag.upload_sessions as upload_sessions

    class FakeObject:
        def __init__(self, object_name: str, size: int) -> None:
            self.object_name = object_name
            self.size = size

    class FakeMinioClient:
        def __init__(self) -> None:
            self.removed: list[str] = []

        def list_objects(self, bucket, prefix, recursive):
            assert bucket == "rag-upload-sessions"
            assert recursive is True
            return [FakeObject(f"{prefix}parts/00000001.part", 7)]

        def remove_object(self, bucket, object_name):
            assert bucket == "rag-upload-sessions"
            self.removed.append(object_name)

    fake_client = FakeMinioClient()
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "upload_session_storage_backend", "minio")
    monkeypatch.setattr(upload_sessions, "_minio_client", lambda: fake_client)
    session = create_upload_session(
        tenant_id=UUID("00000000-0000-4000-8000-000000000001"),
        uploaded_by="subject",
        file_name="stale.txt",
        byte_size=7,
        visibility="tenant",
        allowed_role_names=[],
        force_ocr=False,
    )
    manifest = tmp_path / "sessions" / str(session.upload_session_id) / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    data["uploaded_parts"] = [1]
    manifest.write_text(json.dumps(data), encoding="utf-8")

    result = cleanup_stale_upload_sessions(max_age_hours=1)

    assert result.sessions_removed == 1
    assert result.parts_removed == 1
    assert result.bytes_removed == 7
    assert fake_client.removed == [
        f"00000000-0000-4000-8000-000000000001/{session.upload_session_id}/parts/00000001.part"
    ]
