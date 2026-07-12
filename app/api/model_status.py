from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.rag.model_status import get_model_status
from app.schemas.model_status import ModelStatusResponse


router = APIRouter(prefix="/model-status", tags=["model-status"])


@router.get("", response_model=ModelStatusResponse)
def model_status(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ModelStatusResponse:
    return get_model_status()

