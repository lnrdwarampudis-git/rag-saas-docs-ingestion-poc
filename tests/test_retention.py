from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, text

from app.config import Settings
from app.rag import analytics
from app.rag.retention import run_ops_history_retention


def test_ops_history_retention_deletes_old_rows(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _prepare_tables(engine)
    tenant_id = str(uuid4())
    old = (datetime.now(UTC) - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
    recent = (datetime.now(UTC) - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO query_events (tenant_id, cached, retrieval_ms, total_ms, created_at)
                VALUES (:tenant_id, 0, 1, 2, :old), (:tenant_id, 1, 1, 2, :recent)
                """
            ),
            {"tenant_id": tenant_id, "old": old, "recent": recent},
        )
        connection.execute(
            text(
                """
                INSERT INTO model_latency_events (
                  tenant_id, cached, retrieval_ms, total_ms, created_at
                )
                VALUES (:tenant_id, 0, 1, 2, :old), (:tenant_id, 1, 1, 2, :recent)
                """
            ),
            {"tenant_id": tenant_id, "old": old, "recent": recent},
        )
        connection.execute(
            text(
                """
                INSERT INTO processing_job_events (
                  tenant_id, job_id, document_id, event, status, attempts, metadata, created_at
                )
                VALUES (
                  :tenant_id, :job_id, :document_id, 'created', 'queued', 0, '{}', :old
                ), (
                  :tenant_id, :job_id, :document_id, 'completed', 'completed', 1, '{}', :recent
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "job_id": str(uuid4()),
                "document_id": str(uuid4()),
                "old": old,
                "recent": recent,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO evaluation_runs (
                  cases, passed, failed, context_precision, context_recall, answer_relevance,
                  answer_groundedness, report, created_at
                )
                VALUES
                  (1, 1, 0, 1, 1, 1, 1, '{}', :old),
                  (1, 1, 0, 1, 1, 1, 1, '{}', :recent)
                """
            ),
            {"old": old, "recent": recent},
        )

    _patch_engine(monkeypatch, engine)

    result = run_ops_history_retention(
        settings=Settings(_env_file=None, enable_db_persistence=True),
        query_events_days=30,
        model_latency_events_days=30,
        processing_job_events_days=30,
        evaluation_runs_days=30,
    )

    assert result.skipped is False
    assert result.total_matched == 4
    assert result.total_deleted == 4
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM query_events")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM model_latency_events")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM processing_job_events")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM evaluation_runs")).scalar_one() == 1


def test_ops_history_retention_dry_run_preserves_rows(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _prepare_tables(engine)
    old = (datetime.now(UTC) - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO evaluation_runs (
                  cases, passed, failed, context_precision, context_recall, answer_relevance,
                  answer_groundedness, report, created_at
                )
                VALUES (1, 1, 0, 1, 1, 1, 1, '{}', :old)
                """
            ),
            {"old": old},
        )

    _patch_engine(monkeypatch, engine)

    result = run_ops_history_retention(
        dry_run=True,
        settings=Settings(_env_file=None, enable_db_persistence=True),
        evaluation_runs_days=30,
    )

    assert result.total_matched == 1
    assert result.total_deleted == 0
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM evaluation_runs")).scalar_one() == 1


def test_ops_history_retention_skips_without_persistence() -> None:
    result = run_ops_history_retention(
        settings=Settings(_env_file=None, enable_db_persistence=False),
    )

    assert result.skipped is True
    assert result.reason == "ENABLE_DB_PERSISTENCE is false."


def _prepare_tables(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE query_events (
                  tenant_id TEXT NOT NULL,
                  cached BOOLEAN NOT NULL,
                  retrieval_ms FLOAT NOT NULL,
                  total_ms FLOAT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE model_latency_events (
                  tenant_id TEXT NOT NULL,
                  cached BOOLEAN NOT NULL,
                  retrieval_ms FLOAT NOT NULL,
                  total_ms FLOAT NOT NULL,
                  embedding_model TEXT,
                  answer_model TEXT,
                  vector_index_backend TEXT,
                  reranker_runtime TEXT,
                  created_at TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE processing_job_events (
                  tenant_id TEXT NOT NULL,
                  job_id TEXT NOT NULL,
                  document_id TEXT NOT NULL,
                  event TEXT NOT NULL,
                  status TEXT NOT NULL,
                  attempts INTEGER NOT NULL,
                  metadata TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE evaluation_runs (
                  cases INTEGER NOT NULL,
                  passed INTEGER NOT NULL,
                  failed INTEGER NOT NULL,
                  context_precision FLOAT NOT NULL,
                  context_recall FLOAT NOT NULL,
                  answer_relevance FLOAT NOT NULL,
                  answer_groundedness FLOAT NOT NULL,
                  report TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
        )


def _patch_engine(monkeypatch, engine) -> None:
    monkeypatch.setattr(analytics, "_query_events_table_ready", True)
    monkeypatch.setattr(analytics, "_model_latency_events_table_ready", True)
    monkeypatch.setattr(analytics, "_processing_job_events_table_ready", True)
    monkeypatch.setattr(analytics, "_evaluation_runs_table_ready", True)
    import app.db as db

    monkeypatch.setattr(db, "engine", engine)
