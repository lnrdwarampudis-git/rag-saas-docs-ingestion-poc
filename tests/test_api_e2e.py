from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app


def test_ingest_then_query_authorized_context(tmp_path: Path) -> None:
    source = tmp_path / "policy.txt"
    source.write_text(
        "FINANCE POLICY\nRevenue forecasts are confidential and available to finance members.",
        encoding="utf-8",
    )
    tenant_id = "00000000-0000-4000-8000-000000000001"
    client = TestClient(app)

    ingest_response = client.post(
        "/api/v1/documents/ingest",
        json={
            "tenant_id": tenant_id,
            "local_path": str(source),
            "visibility": "role",
            "allowed_role_names": ["finance"],
            "force_ocr": False,
        },
    )

    assert ingest_response.status_code == 200
    ingest_payload = ingest_response.json()
    UUID(ingest_payload["document_id"])
    assert ingest_payload["chunks_created"] >= 1

    query_response = client.post(
        "/api/v1/query",
        json={
            "tenant_id": tenant_id,
            "query": "Who can read revenue forecasts?",
            "role_names": ["finance"],
            "top_k": 3,
        },
    )

    assert query_response.status_code == 200
    query_payload = query_response.json()
    assert "Revenue forecasts" in query_payload["answer"]
    assert query_payload["citations"]
    assert query_payload["metrics"]["contexts_used"] >= 1


def test_query_hides_role_restricted_context_from_unauthorized_member(tmp_path: Path) -> None:
    source = tmp_path / "legal.txt"
    source.write_text("LEGAL HOLD\nLitigation strategy is available only to legal.", encoding="utf-8")
    tenant_id = "00000000-0000-4000-8000-000000000002"
    client = TestClient(app)

    client.post(
        "/api/v1/documents/ingest",
        json={
            "tenant_id": tenant_id,
            "local_path": str(source),
            "visibility": "role",
            "allowed_role_names": ["legal"],
            "force_ocr": False,
        },
    )

    query_response = client.post(
        "/api/v1/query",
        json={
            "tenant_id": tenant_id,
            "query": "What is the litigation strategy?",
            "role_names": ["support"],
            "top_k": 3,
        },
    )

    assert query_response.status_code == 200
    query_payload = query_response.json()
    assert query_payload["citations"] == []
    assert "could not find enough authorized context" in query_payload["answer"]


def test_upload_document_then_query_context() -> None:
    tenant_id = "00000000-0000-4000-8000-000000000003"
    client = TestClient(app)

    upload_response = client.post(
        "/api/v1/documents/upload",
        data={
            "tenant_id": tenant_id,
            "visibility": "tenant",
            "force_ocr": "false",
        },
        files={
            "file": (
                "remote-policy.txt",
                b"REMOTE POLICY\nUploaded files should be parsed by the backend.",
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 200
    upload_payload = upload_response.json()
    assert upload_payload["file_name"] == "remote-policy.txt"
    assert upload_payload["chunks_created"] >= 1

    query_response = client.post(
        "/api/v1/query",
        json={
            "tenant_id": tenant_id,
            "query": "What should parse uploaded files?",
            "role_names": [],
            "top_k": 3,
        },
    )

    assert query_response.status_code == 200
    query_payload = query_response.json()
    assert "Uploaded files" in query_payload["answer"]
