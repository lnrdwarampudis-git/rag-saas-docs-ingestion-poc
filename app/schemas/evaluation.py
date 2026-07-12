from pydantic import BaseModel


class EvaluationSummary(BaseModel):
    cases: int
    passed: int
    failed: int
    context_precision: float
    context_recall: float
    answer_relevance: float
    targets: dict[str, float]


class EvaluationCaseResult(BaseModel):
    case_id: str
    passed: bool
    context_precision: float
    context_recall: float
    answer_relevance: float
    retrieved_document_ids: list[str]
    expected_document_ids: list[str]
    answer: str


class EvaluationReport(BaseModel):
    summary: EvaluationSummary
    results: list[EvaluationCaseResult]

