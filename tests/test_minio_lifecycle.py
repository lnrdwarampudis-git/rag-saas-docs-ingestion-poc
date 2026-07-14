import sys
import types

from app.config import get_settings
from app.rag import minio_lifecycle


def test_upload_session_lifecycle_skips_filesystem_backend(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_session_storage_backend", "filesystem")

    result = minio_lifecycle.apply_upload_session_lifecycle(expiration_days=3)

    assert result.applied is False
    assert result.expiration_days == 3


def test_upload_session_lifecycle_applies_minio_policy(monkeypatch) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.lifecycle = None

        def set_bucket_lifecycle(self, bucket, config) -> None:
            assert bucket == "rag-upload-sessions"
            self.lifecycle = config

    class FakeExpiration:
        def __init__(self, days):
            self.days = days

    class FakeRule:
        def __init__(self, status, rule_id, expiration):
            self.status = status
            self.rule_id = rule_id
            self.expiration = expiration

    class FakeLifecycleConfig:
        def __init__(self, rules):
            self.rules = rules

    fake_client = FakeClient()
    lifecycle_module = types.ModuleType("minio.lifecycleconfig")
    lifecycle_module.Expiration = FakeExpiration
    lifecycle_module.Rule = FakeRule
    lifecycle_module.LifecycleConfig = FakeLifecycleConfig
    common_module = types.ModuleType("minio.commonconfig")
    common_module.ENABLED = "Enabled"
    minio_module = types.ModuleType("minio")
    monkeypatch.setitem(sys.modules, "minio", minio_module)
    monkeypatch.setitem(sys.modules, "minio.commonconfig", common_module)
    monkeypatch.setitem(sys.modules, "minio.lifecycleconfig", lifecycle_module)
    monkeypatch.setattr(minio_lifecycle, "_ensure_minio_bucket", lambda: None)
    monkeypatch.setattr(minio_lifecycle, "_minio_client", lambda: fake_client)
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_session_storage_backend", "minio")

    result = minio_lifecycle.apply_upload_session_lifecycle(expiration_days=5)

    assert result.applied is True
    assert fake_client.lifecycle.rules[0].expiration.days == 5
