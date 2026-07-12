from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.rag.pipeline import RagPipeline
from app.schemas.query import QueryRequest, QueryResponse

router = APIRouter(prefix="/query", tags=["query"])
pipeline = RagPipeline()


@router.post("", response_model=QueryResponse)
def query_documents(
    payload: QueryRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> QueryResponse:
    result = pipeline.answer(
        query=payload.query,
        tenant_id=str(current_user.tenant_id),
        role_names=current_user.roles,
        top_k=payload.top_k,
        requester_subject=current_user.keycloak_subject,
    )
    return QueryResponse(
        answer=result.answer,
        cached=result.cached,
        citations=result.citations,
        metrics=result.metrics,
    )
