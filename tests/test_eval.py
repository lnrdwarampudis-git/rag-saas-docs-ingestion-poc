from pathlib import Path

from app.eval.run import run_eval


def test_offline_eval_dataset_passes_quality_targets() -> None:
    report = run_eval(Path("data/eval/retrieval_cases.json"))

    assert report["summary"]["cases"] == 5
    assert report["summary"]["failed"] == 0
    assert report["summary"]["context_precision"] >= 0.85
    assert report["summary"]["context_recall"] >= 0.80
    assert report["summary"]["answer_relevance"] >= 0.85
    assert report["summary"]["answer_groundedness"] >= 0.90


def test_retrieval_evaluation_endpoint_returns_quality_gate(api_client_as) -> None:
    client = api_client_as("00000000-0000-4000-8000-000000000011", ["admin"])

    response = client.get("/api/v1/evaluation/retrieval")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["cases"] == 5
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["targets"]["context_precision"] == 0.85
    assert payload["summary"]["targets"]["answer_groundedness"] == 0.9
    assert all(result["passed"] for result in payload["results"])
