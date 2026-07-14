from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone
import json
import shutil
import tempfile

from fastapi import HTTPException, UploadFile

from app.config import get_settings


PART_COPY_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class UploadSession:
    upload_session_id: UUID
    tenant_id: UUID
    uploaded_by: str
    file_name: str
    byte_size: int
    visibility: str
    allowed_role_names: list[str]
    force_ocr: bool
    uploaded_parts_manifest: list[int]

    @property
    def uploaded_parts(self) -> list[int]:
        if _storage_backend() == "minio":
            return sorted(self.uploaded_parts_manifest)
        return sorted(
            int(path.stem)
            for path in _session_dir(self.upload_session_id).glob("*.part")
            if path.stem.isdigit()
        )


@dataclass(frozen=True)
class UploadSessionCleanupResult:
    sessions_removed: int = 0
    parts_removed: int = 0
    bytes_removed: int = 0


def create_upload_session(
    *,
    tenant_id: UUID,
    uploaded_by: str,
    file_name: str,
    byte_size: int,
    visibility: str,
    allowed_role_names: list[str],
    force_ocr: bool,
) -> UploadSession:
    settings = get_settings()
    if byte_size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded file exceeds the {settings.max_upload_bytes} byte limit",
        )
    session = UploadSession(
        upload_session_id=uuid4(),
        tenant_id=tenant_id,
        uploaded_by=uploaded_by,
        file_name=Path(file_name).name,
        byte_size=byte_size,
        visibility=visibility,
        allowed_role_names=allowed_role_names if visibility == "role" else [],
        force_ocr=force_ocr,
        uploaded_parts_manifest=[],
    )
    session_dir = _session_dir(session.upload_session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    _manifest_path(session.upload_session_id).write_text(
        json.dumps(
            {
                "upload_session_id": str(session.upload_session_id),
                "tenant_id": str(session.tenant_id),
                "uploaded_by": session.uploaded_by,
                "file_name": session.file_name,
                "byte_size": session.byte_size,
                "visibility": session.visibility,
                "allowed_role_names": session.allowed_role_names,
                "force_ocr": session.force_ocr,
                "uploaded_parts": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    return session


def get_upload_session(upload_session_id: UUID) -> UploadSession:
    manifest = _manifest_path(upload_session_id)
    if not manifest.exists():
        raise HTTPException(status_code=404, detail="Upload session not found")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return UploadSession(
        upload_session_id=UUID(data["upload_session_id"]),
        tenant_id=UUID(data["tenant_id"]),
        uploaded_by=data["uploaded_by"],
        file_name=data["file_name"],
        byte_size=int(data["byte_size"]),
        visibility=data["visibility"],
        allowed_role_names=list(data.get("allowed_role_names", [])),
        force_ocr=bool(data.get("force_ocr", False)),
        uploaded_parts_manifest=list(data.get("uploaded_parts", [])),
    )


def delete_upload_session(upload_session_id: UUID) -> UploadSessionCleanupResult:
    return _delete_session(get_upload_session(upload_session_id))


def cleanup_stale_upload_sessions(max_age_hours: int | None = None) -> UploadSessionCleanupResult:
    settings = get_settings()
    max_age = max_age_hours if max_age_hours is not None else settings.upload_session_cleanup_max_age_hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, max_age))
    sessions_root = Path(settings.upload_dir) / "sessions"
    if not sessions_root.exists():
        return UploadSessionCleanupResult()

    total = UploadSessionCleanupResult()
    for manifest in sessions_root.glob("*/manifest.json"):
        try:
            upload_session_id = UUID(manifest.parent.name)
            if _session_created_at(manifest) > cutoff:
                continue
            result = delete_upload_session(upload_session_id)
        except (HTTPException, OSError, ValueError, json.JSONDecodeError):
            continue
        total = UploadSessionCleanupResult(
            sessions_removed=total.sessions_removed + result.sessions_removed,
            parts_removed=total.parts_removed + result.parts_removed,
            bytes_removed=total.bytes_removed + result.bytes_removed,
        )
    return total


def save_upload_part(upload_session_id: UUID, part_number: int, file: UploadFile) -> UploadSession:
    if part_number < 1:
        raise HTTPException(status_code=422, detail="part_number must be greater than zero")
    session = get_upload_session(upload_session_id)
    if _storage_backend() == "minio":
        bytes_written = _save_minio_part(session, part_number, file)
        if bytes_written == 0:
            raise HTTPException(status_code=422, detail="Upload part cannot be empty")
        _record_uploaded_part(session, part_number)
        if _uploaded_bytes(upload_session_id) > session.byte_size:
            _remove_minio_part(session, part_number)
            _remove_uploaded_part(get_upload_session(upload_session_id), part_number)
            raise HTTPException(status_code=413, detail="Uploaded parts exceed declared file size")
        return get_upload_session(upload_session_id)

    target = _session_dir(upload_session_id) / f"{part_number:08d}.part"
    tmp_target = target.with_suffix(".tmp")
    bytes_written = 0
    with tmp_target.open("wb") as output:
        while chunk := file.file.read(PART_COPY_CHUNK_SIZE):
            bytes_written += len(chunk)
            output.write(chunk)
    if bytes_written == 0:
        tmp_target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Upload part cannot be empty")
    tmp_target.replace(target)
    if _uploaded_bytes(upload_session_id) > session.byte_size:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail="Uploaded parts exceed declared file size")
    return session


def presign_upload_part(upload_session_id: UUID, part_number: int) -> str:
    if part_number < 1:
        raise HTTPException(status_code=422, detail="part_number must be greater than zero")
    if _storage_backend() != "minio":
        raise HTTPException(status_code=409, detail="Presigned part uploads require MinIO storage")
    session = get_upload_session(upload_session_id)
    _ensure_minio_bucket()
    return _minio_presign_client().presigned_put_object(
        get_settings().upload_session_bucket,
        _part_object_name(session, part_number),
        expires=timedelta(seconds=get_settings().upload_session_presign_expiry_seconds),
    )


def mark_presigned_upload_part(upload_session_id: UUID, part_number: int) -> UploadSession:
    if _storage_backend() != "minio":
        raise HTTPException(status_code=409, detail="Presigned part completion requires MinIO storage")
    session = get_upload_session(upload_session_id)
    stat = _minio_client().stat_object(
        get_settings().upload_session_bucket,
        _part_object_name(session, part_number),
    )
    if stat.size <= 0:
        raise HTTPException(status_code=422, detail="Upload part cannot be empty")
    _record_uploaded_part(session, part_number)
    if _uploaded_bytes(upload_session_id) > session.byte_size:
        _remove_minio_part(session, part_number)
        _remove_uploaded_part(get_upload_session(upload_session_id), part_number)
        raise HTTPException(status_code=413, detail="Uploaded parts exceed declared file size")
    return get_upload_session(upload_session_id)


def assemble_upload_session(upload_session_id: UUID) -> tuple[UploadSession, Path]:
    session = get_upload_session(upload_session_id)
    if _uploaded_bytes(upload_session_id) != session.byte_size:
        raise HTTPException(status_code=409, detail="Upload session is missing bytes")
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{upload_session_id}-{session.file_name}"
    with target.open("wb") as output:
        for part_number in session.uploaded_parts:
            if _storage_backend() == "minio":
                response = _minio_client().get_object(
                    settings.upload_session_bucket,
                    _part_object_name(session, part_number),
                )
                try:
                    shutil.copyfileobj(response, output, length=PART_COPY_CHUNK_SIZE)
                finally:
                    response.close()
                    response.release_conn()
            else:
                with (_session_dir(upload_session_id) / f"{part_number:08d}.part").open("rb") as part:
                    shutil.copyfileobj(part, output, length=PART_COPY_CHUNK_SIZE)
    delete_upload_session(upload_session_id)
    return session, target


def _delete_session(session: UploadSession) -> UploadSessionCleanupResult:
    if _storage_backend() == "minio":
        parts_removed = 0
        bytes_removed = 0
        client = _minio_client()
        bucket = get_settings().upload_session_bucket
        for item in _minio_session_objects(session):
            bytes_removed += int(getattr(item, "size", 0) or 0)
            client.remove_object(bucket, item.object_name)
            parts_removed += 1
    else:
        part_paths = list(_session_dir(session.upload_session_id).glob("*.part"))
        parts_removed = len(part_paths)
        bytes_removed = sum(path.stat().st_size for path in part_paths)
    shutil.rmtree(_session_dir(session.upload_session_id), ignore_errors=True)
    return UploadSessionCleanupResult(
        sessions_removed=1,
        parts_removed=parts_removed,
        bytes_removed=bytes_removed,
    )


def _uploaded_bytes(upload_session_id: UUID) -> int:
    if _storage_backend() == "minio":
        session = get_upload_session(upload_session_id)
        client = _minio_client()
        total = 0
        for part_number in session.uploaded_parts:
            total += client.stat_object(
                get_settings().upload_session_bucket,
                _part_object_name(session, part_number),
            ).size
        return total
    return sum(path.stat().st_size for path in _session_dir(upload_session_id).glob("*.part"))


def _session_dir(upload_session_id: UUID) -> Path:
    return Path(get_settings().upload_dir) / "sessions" / str(upload_session_id)


def _manifest_path(upload_session_id: UUID) -> Path:
    return _session_dir(upload_session_id) / "manifest.json"


def _session_created_at(manifest: Path) -> datetime:
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        raw_created_at = data.get("created_at")
        if isinstance(raw_created_at, str):
            return datetime.fromisoformat(raw_created_at)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return datetime.fromtimestamp(manifest.stat().st_mtime, timezone.utc)


def _storage_backend() -> str:
    return get_settings().upload_session_storage_backend.lower()


def _save_minio_part(session: UploadSession, part_number: int, file: UploadFile) -> int:
    client = _minio_client()
    with tempfile.NamedTemporaryFile() as tmp:
        bytes_written = 0
        while chunk := file.file.read(PART_COPY_CHUNK_SIZE):
            bytes_written += len(chunk)
            tmp.write(chunk)
        tmp.flush()
        tmp.seek(0)
        _ensure_minio_bucket()
        client.put_object(
            get_settings().upload_session_bucket,
            _part_object_name(session, part_number),
            tmp,
            length=bytes_written,
        )
        return bytes_written


def _record_uploaded_part(session: UploadSession, part_number: int) -> None:
    parts = sorted({*session.uploaded_parts_manifest, part_number})
    _update_manifest(session.upload_session_id, {"uploaded_parts": parts})


def _remove_uploaded_part(session: UploadSession, part_number: int) -> None:
    parts = [part for part in session.uploaded_parts_manifest if part != part_number]
    _update_manifest(session.upload_session_id, {"uploaded_parts": parts})


def _update_manifest(upload_session_id: UUID, updates: dict) -> None:
    manifest = _manifest_path(upload_session_id)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data.update(updates)
    manifest.write_text(json.dumps(data), encoding="utf-8")


def _part_object_name(session: UploadSession, part_number: int) -> str:
    return f"{session.tenant_id}/{session.upload_session_id}/parts/{part_number:08d}.part"


def _session_object_prefix(session: UploadSession) -> str:
    return f"{session.tenant_id}/{session.upload_session_id}/"


def _minio_session_objects(session: UploadSession):
    return _minio_client().list_objects(
        get_settings().upload_session_bucket,
        prefix=_session_object_prefix(session),
        recursive=True,
    )


def _remove_minio_part(session: UploadSession, part_number: int) -> None:
    _minio_client().remove_object(get_settings().upload_session_bucket, _part_object_name(session, part_number))


def _ensure_minio_bucket() -> None:
    client = _minio_client()
    bucket = get_settings().upload_session_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def _minio_client():
    return _build_minio_client(get_settings().minio_endpoint)


def _minio_presign_client():
    settings = get_settings()
    return _build_minio_client(settings.minio_public_endpoint or settings.minio_endpoint)


def _build_minio_client(endpoint_url: str):
    try:
        from minio import Minio
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="MinIO SDK is not installed") from exc

    settings = get_settings()
    secure = endpoint_url.startswith("https://")
    endpoint = endpoint_url.removeprefix("http://").removeprefix("https://")
    return Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure if endpoint_url.startswith(("http://", "https://")) else settings.minio_secure,
    )
