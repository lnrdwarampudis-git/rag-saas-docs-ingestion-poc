from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json

from app.rag.model_providers import ExtractiveAnswerGenerator
from app.rag.retrieval import HybridRetriever, RetrievalRequest
from app.schemas.documents import ChunkDTO

DEFAULT_DATASET = Path("data/eval/retrieval_cases.json")
CONTEXT_PRECISION_TARGET = 0.85
CONTEXT_RECALL_TARGET = 0.80
ANSWER_RELEVANCE_TARGET = 0.85
ANSWER_GENERATOR = ExtractiveAnswerGenerator()


@dataclass(frozen=True)
class EvalCaseResult:
    case_id: str
    context_precision: float
    context_recall: float
    answer_relevance: float
    retrieved_document_ids: list[str]
    expected_document_ids: list[str]
    answer: str

    @property
    def passed(self) -> bool:
        return (
            self.context_precision >= CONTEXT_PRECISION_TARGET
            and self.context_recall >= CONTEXT_RECALL_TARGET
            and self.answer_relevance >= ANSWER_RELEVANCE_TARGET
        )


def run_eval(dataset_path: Path = DEFAULT_DATASET) -> dict:
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    results = [_evaluate_case(case) for case in cases]
    summary = {
        "cases": len(results),
        "passed": sum(result.passed for result in results),
        "failed": sum(not result.passed for result in results),
        "context_precision": _average([result.context_precision for result in results]),
        "context_recall": _average([result.context_recall for result in results]),
        "answer_relevance": _average([result.answer_relevance for result in results]),
        "targets": {
            "context_precision": CONTEXT_PRECISION_TARGET,
            "context_recall": CONTEXT_RECALL_TARGET,
            "answer_relevance": ANSWER_RELEVANCE_TARGET,
        },
    }
    return {
        "summary": summary,
        "results": [
            {
                "case_id": result.case_id,
                "passed": result.passed,
                "context_precision": round(result.context_precision, 4),
                "context_recall": round(result.context_recall, 4),
                "answer_relevance": round(result.answer_relevance, 4),
                "retrieved_document_ids": result.retrieved_document_ids,
                "expected_document_ids": result.expected_document_ids,
                "answer": result.answer,
            }
            for result in results
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline RAG retrieval evaluation.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    args = parser.parse_args()

    report = run_eval(args.dataset)
    if args.json:
        print(json.dumps(report, indent=2))
        return

    summary = report["summary"]
    print("RAG retrieval evaluation")
    print(f"Cases: {summary['cases']} passed={summary['passed']} failed={summary['failed']}")
    print(
        "Averages: "
        f"context_precision={summary['context_precision']:.3f}, "
        f"context_recall={summary['context_recall']:.3f}, "
        f"answer_relevance={summary['answer_relevance']:.3f}"
    )
    for result in report["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"{status} {result['case_id']} "
            f"precision={result['context_precision']:.3f} "
            f"recall={result['context_recall']:.3f} "
            f"answer={result['answer_relevance']:.3f}"
        )


def _evaluate_case(case: dict) -> EvalCaseResult:
    chunks = [_chunk_from_case(case, chunk) for chunk in case["chunks"]]
    expected_document_ids = list(case.get("expected_document_ids", []))
    results = HybridRetriever().retrieve(
        chunks,
        RetrievalRequest(
            query=case["query"],
            tenant_id=case["tenant_id"],
            role_names=list(case.get("role_names", [])),
            requester_subject=case.get("requester_subject"),
            top_k=case.get("top_k", 5),
        ),
    )
    retrieved_document_ids = [
        str(result.chunk.metadata.get("document_id"))
        for result in results
        if result.chunk.metadata.get("document_id")
    ]
    answer = ANSWER_GENERATOR.generate(case["query"], results).lower()
    return EvalCaseResult(
        case_id=case["id"],
        context_precision=_context_precision(retrieved_document_ids, expected_document_ids),
        context_recall=_context_recall(retrieved_document_ids, expected_document_ids),
        answer_relevance=_answer_relevance(answer, case.get("expected_answer_terms", [])),
        retrieved_document_ids=retrieved_document_ids,
        expected_document_ids=expected_document_ids,
        answer=answer,
    )


def _chunk_from_case(case: dict, chunk: dict) -> ChunkDTO:
    metadata = {
        "tenant_id": case["tenant_id"],
        "document_id": chunk["document_id"],
        "file_name": chunk["file_name"],
        "visibility": chunk.get("visibility", "tenant"),
        "allowed_role_names": chunk.get("allowed_role_names", []),
        "uploaded_by": chunk.get("uploaded_by"),
        "ocr_used": chunk.get("ocr_used", False),
    }
    return ChunkDTO(
        chunk_index=chunk["chunk_index"],
        text=chunk["text"],
        token_count=len(chunk["text"].split()),
        metadata=metadata,
    )


def _context_precision(retrieved: list[str], expected: list[str]) -> float:
    if not retrieved:
        return 1.0 if not expected else 0.0
    return len([document_id for document_id in retrieved if document_id in expected]) / len(retrieved)


def _context_recall(retrieved: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0 if not retrieved else 0.0
    return len(set(retrieved).intersection(expected)) / len(set(expected))


def _answer_relevance(answer: str, expected_terms: list[str]) -> float:
    if not expected_terms:
        return 1.0
    return len([term for term in expected_terms if term.lower() in answer]) / len(expected_terms)


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


if __name__ == "__main__":
    main()
