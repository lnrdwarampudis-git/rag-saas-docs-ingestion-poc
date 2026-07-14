from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4
import json
import shutil

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

    @property
    def uploaded_parts(self) -> list[int]:
        return sorted(
            int(path.stem)
            for path in _session_dir(self.upload_session_id).glob("*.part")
            if path.stem.isdigit()
        )


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
    )


def save_upload_part(upload_session_id: UUID, part_number: int, file: UploadFile) -> UploadSession:
    if part_number < 1:
        raise HTTPException(status_code=422, detail="part_number must be greater than zero")
    session = get_upload_session(upload_session_id)
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
            with (_session_dir(upload_session_id) / f"{part_number:08d}.part").open("rb") as part:
                shutil.copyfileobj(part, output, length=PART_COPY_CHUNK_SIZE)
    return session, target


def _uploaded_bytes(upload_session_id: UUID) -> int:
    return sum(path.stat().st_size for path in _session_dir(upload_session_id).glob("*.part"))


def _session_dir(upload_session_id: UUID) -> Path:
    return Path(get_settings().upload_dir) / "sessions" / str(upload_session_id)


def _manifest_path(upload_session_id: UUID) -> Path:
    return _session_dir(upload_session_id) / "manifest.json"
