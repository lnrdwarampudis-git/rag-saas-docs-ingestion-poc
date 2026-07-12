from fastapi import APIRouter

from app.rag.pipeline import RagPipeline
from app.schemas.query import QueryRequest, QueryResponse

router = APIRouter(prefix="/query", tags=["query"])
pipeline = RagPipeline()


@router.post("", response_model=QueryResponse)
def query_documents(payload: QueryRequest) -> QueryResponse:
    result = pipeline.answer(
        query=payload.query,
        tenant_id=str(payload.tenant_id),
        role_names=payload.role_names,
        top_k=payload.top_k,
    )
    return QueryResponse(
        answer=result.answer,
        cached=result.cached,
        citations=result.citations,
        metrics=result.metrics,
    )
