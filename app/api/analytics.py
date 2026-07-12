from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.rag.analytics import get_analytics
from app.schemas.analytics import AnalyticsResponse


router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsResponse)
def analytics(current_user: AuthenticatedUser = Depends(get_current_user)) -> AnalyticsResponse:
    return get_analytics(current_user)

