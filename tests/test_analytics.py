from uuid import UUID, uuid4

from app.rag.pipeline import RagPipeline
from app.rag.store import document_store
from app.schemas.documents import ChunkDTO


def test_analytics_endpoint_returns_operational_summary(api_client_as) -> None:
    tenant_id = "00000000-0000-4000-8000-000000000012"
    client = api_client_as(tenant_id, ["admin"])

    response = client.get("/api/v1/analytics")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"documents", "jobs", "queries", "evaluation"}
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
