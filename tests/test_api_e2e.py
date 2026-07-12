from pathlib import Path
from uuid import UUID


def test_ingest_then_query_authorized_context(tmp_path: Path, api_client_as) -> None:
    source = tmp_path / "policy.txt"
    source.write_text(
        "FINANCE POLICY\nRevenue forecasts are confidential and available to finance members.",
        encoding="utf-8",
    )
    tenant_id = "00000000-0000-4000-8000-000000000001"
    client = api_client_as(tenant_id, ["finance"])

    ingest_response = client.post(
        "/api/v1/documents/ingest",
        json={
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
            "query": "Who can read revenue forecasts?",
            "top_k": 3,
        },
    )

    assert query_response.status_code == 200
    query_payload = query_response.json()
    assert "Revenue forecasts" in query_payload["answer"]
    assert query_payload["citations"]
    assert query_payload["metrics"]["contexts_used"] >= 1


def test_query_hides_role_restricted_context_from_unauthorized_member(tmp_path: Path, api_client_as) -> None:
    source = tmp_path / "legal.txt"
    source.write_text("LEGAL HOLD\nLitigation strategy is available only to legal.", encoding="utf-8")
    tenant_id = "00000000-0000-4000-8000-000000000002"

    ingest_client = api_client_as(tenant_id, ["legal"])
    ingest_client.post(
        "/api/v1/documents/ingest",
        json={
            "local_path": str(source),
            "visibility": "role",
            "allowed_role_names": ["legal"],
            "force_ocr": False,
        },
    )

    unauthorized_client = api_client_as(tenant_id, ["support"])
    query_response = unauthorized_client.post(
        "/api/v1/query",
        json={
            "query": "What is the litigation strategy?",
            "top_k": 3,
        },
    )

    assert query_response.status_code == 200
    query_payload = query_response.json()
    assert query_payload["citations"] == []
    assert "could not find enough authorized context" in query_payload["answer"]


def test_query_hides_context_across_tenants(tmp_path: Path, api_client_as) -> None:
    """A user in Tenant A must never see Tenant B's documents, even with matching roles."""
    source = tmp_path / "tenant-a-only.txt"
    source.write_text("TENANT A SECRET\nOnly Tenant A admins should see this rollout plan.", encoding="utf-8")
    tenant_a = "00000000-0000-4000-8000-0000000000aa"
    tenant_b = "00000000-0000-4000-8000-0000000000bb"

    api_client_as(tenant_a, ["admin"]).post(
        "/api/v1/documents/ingest",
        json={
            "local_path": str(source),
            "visibility": "tenant",
            "force_ocr": False,
        },
    )

    cross_tenant_client = api_client_as(tenant_b, ["admin"])
    query_response = cross_tenant_client.post(
        "/api/v1/query",
        json={"query": "What is the rollout plan?", "top_k": 3},
    )

    assert query_response.status_code == 200
    assert query_response.json()["citations"] == []


def test_upload_document_then_query_context(tmp_path: Path, api_client_as) -> None:
    tenant_id = "00000000-0000-4000-8000-000000000003"
    client = api_client_as(tenant_id, ["admin"])

    upload_response = client.post(
        "/api/v1/documents/upload",
        data={
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
            "query": "What should parse uploaded files?",
            "top_k": 3,
        },
    )

    assert query_response.status_code == 200
    query_payload = query_response.json()
    assert "Uploaded files" in query_payload["answer"]


def test_document_management_lists_and_details_authorized_documents(tmp_path: Path, api_client_as) -> None:
    tenant_id = "00000000-0000-4000-8000-000000000004"
    client = api_client_as(tenant_id, ["finance"], "finance-subject")
    source = tmp_path / "finance-policy.txt"
    source.write_text("Finance members can review quarterly forecast policy.", encoding="utf-8")

    ingest_response = client.post(
        "/api/v1/documents/ingest",
        json={
            "local_path": str(source),
            "visibility": "role",
            "allowed_role_names": ["finance"],
            "force_ocr": False,
        },
    )
    assert ingest_response.status_code == 200
    document_id = ingest_response.json()["document_id"]

    list_response = client.get("/api/v1/documents")
    assert list_response.status_code == 200
    documents = list_response.json()["documents"]
    matching = [document for document in documents if document["document_id"] == document_id]
    assert matching
    assert matching[0]["file_name"] == "finance-policy.txt"
    assert matching[0]["visibility"] == "role"
    assert matching[0]["chunks_created"] >= 1

    detail_response = client.get(f"/api/v1/documents/{document_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["document_id"] == document_id
    assert detail["chunks"]
    assert "quarterly forecast" in detail["chunks"][0]["text"]


def test_document_management_hides_unauthorized_documents(tmp_path: Path, api_client_as) -> None:
    tenant_id = "00000000-0000-4000-8000-000000000005"
    legal_client = api_client_as(tenant_id, ["legal"], "legal-subject")
    source = tmp_path / "legal-only.txt"
    source.write_text("Legal settlement terms are restricted.", encoding="utf-8")

    ingest_response = legal_client.post(
        "/api/v1/documents/ingest",
        json={
            "local_path": str(source),
            "visibility": "role",
            "allowed_role_names": ["legal"],
            "force_ocr": False,
        },
    )
    assert ingest_response.status_code == 200
    document_id = ingest_response.json()["document_id"]

    support_client = api_client_as(tenant_id, ["support"], "support-subject")
    list_response = support_client.get("/api/v1/documents")
    assert list_response.status_code == 200
    assert all(document["document_id"] != document_id for document in list_response.json()["documents"])

    detail_response = support_client.get(f"/api/v1/documents/{document_id}")
    assert detail_response.status_code == 404


def test_query_requires_authentication() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.post("/api/v1/query", json={"query": "anything", "top_k": 3})
    assert response.status_code == 401
