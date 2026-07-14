from dataclasses import dataclass

from app.config import get_settings
from app.rag.upload_sessions import _ensure_minio_bucket, _minio_client


@dataclass(frozen=True)
class UploadSessionLifecycleResult:
    bucket: str
    expiration_days: int
    applied: bool
    message: str


def apply_upload_session_lifecycle(
    expiration_days: int | None = None,
) -> UploadSessionLifecycleResult:
    settings = get_settings()
    days = max(1, expiration_days or settings.upload_session_lifecycle_expiration_days)
    if settings.upload_session_storage_backend.lower() != "minio":
        return UploadSessionLifecycleResult(
            bucket=settings.upload_session_bucket,
            expiration_days=days,
            applied=False,
            message="Upload-session lifecycle applies only when storage backend is minio.",
        )

    try:
        from minio.commonconfig import ENABLED
        from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("MinIO SDK lifecycle support is not installed.") from exc

    _ensure_minio_bucket()
    client = _minio_client()
    config = LifecycleConfig(
        [
            Rule(
                ENABLED,
                rule_id="expire-upload-session-parts",
                expiration=Expiration(days=days),
            )
        ]
    )
    client.set_bucket_lifecycle(settings.upload_session_bucket, config)
    return UploadSessionLifecycleResult(
        bucket=settings.upload_session_bucket,
        expiration_days=days,
        applied=True,
        message=f"Applied upload-session object lifecycle expiration after {days} day(s).",
    )


if __name__ == "__main__":
    result = apply_upload_session_lifecycle()
    print(result.message)
