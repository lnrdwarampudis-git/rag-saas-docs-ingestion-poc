from pathlib import Path
from uuid import UUID

from app.config import get_settings
from app.rag import jobs


class FakeRedis:
    def __init__(self) -> None:
        self.pushed: list[tuple[str, str]] = []
        self.polled: list[str] | None = None

    def rpush(self, queue_name: str, job_id: str) -> None:
        self.pushed.append((queue_name, job_id))

    def blpop(self, queue_names: list[str], timeout: int):
        self.polled = queue_names
        return None


def test_processing_jobs_route_force_ocr_to_dedicated_queue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "processing_queue_name", "test:jobs")
    monkeypatch.setattr(settings, "ocr_processing_queue_name", "test:jobs:ocr")
    fake_redis = FakeRedis()
    monkeypatch.setattr(jobs, "_redis_client", lambda: fake_redis)

    normal_job = jobs.create_processing_job(
        path=_source_file(tmp_path, "normal.txt"),
        file_name="normal.txt",
        tenant_id=UUID("00000000-0000-4000-8000-000000000031"),
        uploaded_by="subject",
        uploaded_by_user_id=None,
        visibility="tenant",
        allowed_role_names=[],
        force_ocr=False,
    )
    ocr_job = jobs.create_processing_job(
        path=_source_file(tmp_path, "ocr.txt"),
        file_name="ocr.txt",
        tenant_id=UUID("00000000-0000-4000-8000-000000000031"),
        uploaded_by="subject",
        uploaded_by_user_id=None,
        visibility="tenant",
        allowed_role_names=[],
        force_ocr=True,
    )

    jobs.enqueue_processing_job(normal_job.job_id)
    jobs.enqueue_processing_job(ocr_job.job_id)

    assert fake_redis.pushed == [
        ("test:jobs", str(normal_job.job_id)),
        ("test:jobs:ocr", str(ocr_job.job_id)),
    ]


def test_worker_polls_configured_queue_names(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "worker_queue_names", "test:jobs:ocr,test:jobs:priority")
    fake_redis = FakeRedis()
    monkeypatch.setattr(jobs, "_redis_client", lambda: fake_redis)

    result = jobs.process_next_queued_job(timeout_seconds=1)

    assert result is None
    assert fake_redis.polled == ["test:jobs:ocr", "test:jobs:priority"]


def _source_file(tmp_path: Path, file_name: str) -> Path:
    source = tmp_path / file_name
    source.write_text("Queue routing test", encoding="utf-8")
    return source
