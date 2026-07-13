from uuid import UUID, uuid4

from sqlalchemy import create_engine, text

from app.auth.models import AuthenticatedUser
from app.rag import analytics
from app.rag.pipeline import RagPipeline
from app.rag.store import document_store
from app.schemas.documents import ChunkDTO, ProcessingJobStatus


def test_analytics_endpoint_returns_operational_summary(api_client_as) -> None:
    tenant_id = "00000000-0000-4000-8000-000000000012"
    client = api_client_as(tenant_id, ["admin"])

    response = client.get("/api/v1/analytics")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"documents", "jobs", "queries", "evaluation", "recent_events"}
    assert payload["evaluation"]["cases"] == 3
    assert payload["evaluation"]["failed"] == 0


def test_analytics_counts_in_memory_documents_and_query_events(api_client_as) -> None:
    tenant_id = "00000000-0000-4000-8000-000000000013"
    document_store.put_chunks(
        uuid4(),
        [
            ChunkDTO(
                chunk_index=0,
                text="Redis cache improves repeated RAG query latency.",
                token_count=7,
                metadata={
                    "tenant_id": tenant_id,
                    "document_id": "analytics-doc",
                    "file_name": "analytics.txt",
                    "visibility": "tenant",
                    "allowed_role_names": [],
                    "ocr_used": False,
                },
            )
        ],
        tenant_id=UUID(tenant_id),
        file_name="analytics.txt",
    )
    pipeline = RagPipeline()
    pipeline.answer("How does Redis help?", tenant_id, [])
    pipeline.answer("How does Redis help?", tenant_id, [])

    response = api_client_as(tenant_id, ["admin"]).get("/api/v1/analytics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"]["total"] >= 1
    assert payload["documents"]["chunks"] >= 1
    assert payload["queries"]["total"] >= 2
    assert payload["queries"]["cache_hits"] >= 1
    assert payload["queries"]["cache_hit_rate"] > 0


def test_persistent_query_analytics_rolls_up_recent_events(monkeypatch) -> None:
    tenant_id = UUID("00000000-0000-4000-8000-000000000014")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE query_events (
                  tenant_id TEXT NOT NULL,
                  cached BOOLEAN NOT NULL,
                  retrieval_ms FLOAT NOT NULL,
                  total_ms FLOAT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO query_events (tenant_id, cached, retrieval_ms, total_ms)
                VALUES
                  (:tenant_id, 0, 10.0, 30.0),
                  (:tenant_id, 1, 4.0, 8.0),
                  (:other_tenant_id, 1, 1.0, 1.0)
                """
            ),
            {
                "tenant_id": str(tenant_id),
                "other_tenant_id": "00000000-0000-4000-8000-000000000099",
            },
        )

    monkeypatch.setattr(analytics.get_settings(), "enable_db_persistence", True)
    monkeypatch.setattr(analytics, "_query_events_table_ready", True)
    import app.db as db

    monkeypatch.setattr(db, "engine", engine)

    report = analytics._persistent_query_analytics(
        AuthenticatedUser(
            keycloak_subject="analytics-subject",
            tenant_id=tenant_id,
            roles=["admin"],
        )
    )

    assert report is not None
    assert report.total == 2
    assert report.cache_hits == 1
    assert report.cache_misses == 1
    assert report.cache_hit_rate == 0.5
    assert report.average_retrieval_ms == 7.0
    assert report.average_total_ms == 19.0


def test_persistent_audit_events_return_recent_tenant_history(monkeypatch) -> None:
    tenant_id = UUID("00000000-0000-4000-8000-000000000015")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE app_users (
                  id TEXT PRIMARY KEY,
                  display_name TEXT,
                  email TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE audit_logs (
                  tenant_id TEXT NOT NULL,
                  actor_user_id TEXT,
                  action TEXT NOT NULL,
                  resource_type TEXT NOT NULL,
                  resource_id TEXT,
                  metadata TEXT,
                  created_at TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO app_users (id, display_name, email)
                VALUES ('user-1', 'Alex Admin', 'alex@example.test')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO audit_logs (
                  tenant_id, actor_user_id, action, resource_type, resource_id, metadata, created_at
                )
                VALUES
                  (:tenant_id, 'user-1', 'document.ingested', 'document', 'doc-1',
                   :metadata, '2026-07-12T10:00:00'),
                  (:other_tenant_id, 'user-1', 'document.ingested', 'document', 'doc-2',
                   :other_metadata, '2026-07-12T11:00:00')
                """
            ),
            {
                "tenant_id": str(tenant_id),
                "other_tenant_id": "00000000-0000-4000-8000-000000000099",
                "metadata": '{"file_name":"runbook.pdf","chunks_created":4}',
                "other_metadata": '{"file_name":"other.pdf"}',
            },
        )

    monkeypatch.setattr(analytics.get_settings(), "enable_db_persistence", True)
    import app.db as db

    monkeypatch.setattr(db, "engine", engine)

    events = analytics._persistent_audit_events(
        AuthenticatedUser(
            keycloak_subject="analytics-subject",
            tenant_id=tenant_id,
            roles=["admin"],
        )
    )

    assert len(events) == 1
    assert events[0].action == "document.ingested"
    assert events[0].actor == "Alex Admin"
    assert events[0].resource_id == "doc-1"
    assert events[0].metadata["file_name"] == "runbook.pdf"


def test_query_audit_event_persists_safe_metadata(monkeypatch) -> None:
    tenant_id = UUID("00000000-0000-4000-8000-000000000016")
    actor_id = UUID("10000000-0000-4000-8000-000000000016")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE audit_logs (
                  tenant_id TEXT NOT NULL,
                  actor_user_id TEXT,
                  action TEXT NOT NULL,
                  resource_type TEXT NOT NULL,
                  metadata TEXT NOT NULL
                )
                """
            )
        )

    monkeypatch.setattr(analytics.get_settings(), "enable_db_persistence", True)
    import app.db as db

    monkeypatch.setattr(db, "engine", engine)

    analytics.record_query_audit_event(
        current_user=AuthenticatedUser(
            keycloak_subject="analytics-subject",
            tenant_id=tenant_id,
            roles=["admin"],
            app_user_id=actor_id,
        ),
        query="What is the sensitive roadmap?",
        top_k=3,
        cached=False,
        citations=[{"document_id": "doc-1"}, {"document_id": "doc-1"}, {"document_id": "doc-2"}],
        metrics={
            "contexts_used": 2,
            "retrieval_ms": 11.25,
            "total_ms": 24.5,
            "embedding_model": "hashing-384",
            "answer_model": "extractive",
        },
    )

    with engine.begin() as connection:
        row = connection.execute(text("SELECT * FROM audit_logs")).mappings().one()

    metadata = analytics._metadata_dict(row["metadata"])
    assert row["tenant_id"] == str(tenant_id)
    assert row["actor_user_id"] == str(actor_id)
    assert row["action"] == "query.executed"
    assert row["resource_type"] == "query"
    assert metadata["query_length"] == 30
    assert metadata["top_k"] == 3
    assert metadata["cached"] is False
    assert metadata["contexts_used"] == 2
    assert metadata["citation_document_ids"] == ["doc-1", "doc-2"]
    assert "sensitive roadmap" not in row["metadata"]


def test_job_retry_audit_event_persists_retry_metadata(monkeypatch) -> None:
    tenant_id = UUID("00000000-0000-4000-8000-000000000017")
    actor_id = UUID("10000000-0000-4000-8000-000000000017")
    job_id = UUID("20000000-0000-4000-8000-000000000017")
    document_id = UUID("30000000-0000-4000-8000-000000000017")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE audit_logs (
                  tenant_id TEXT NOT NULL,
                  actor_user_id TEXT,
                  action TEXT NOT NULL,
                  resource_type TEXT NOT NULL,
                  resource_id TEXT,
                  metadata TEXT NOT NULL
                )
                """
            )
        )

    monkeypatch.setattr(analytics.get_settings(), "enable_db_persistence", True)
    import app.db as db

    monkeypatch.setattr(db, "engine", engine)

    analytics.record_job_retry_audit_event(
        current_user=AuthenticatedUser(
            keycloak_subject="analytics-subject",
            tenant_id=tenant_id,
            roles=["admin"],
            app_user_id=actor_id,
        ),
        job_status=ProcessingJobStatus(
            job_id=job_id,
            document_id=document_id,
            file_name="retry-me.pdf",
            status="queued",
            stage="upload",
            attempts=1,
        ),
    )

    with engine.begin() as connection:
        row = connection.execute(text("SELECT * FROM audit_logs")).mappings().one()

    metadata = analytics._metadata_dict(row["metadata"])
    assert row["tenant_id"] == str(tenant_id)
    assert row["actor_user_id"] == str(actor_id)
    assert row["action"] == "processing_job.retried"
    assert row["resource_type"] == "processing_job"
    assert row["resource_id"] == str(job_id)
    assert metadata == {
        "job_id": str(job_id),
        "document_id": str(document_id),
        "file_name": "retry-me.pdf",
        "attempts": 1,
        "status": "queued",
        "stage": "upload",
    }
