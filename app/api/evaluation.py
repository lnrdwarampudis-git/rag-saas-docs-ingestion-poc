from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.eval.history import record_evaluation_run
from app.eval.run import run_eval
from app.schemas.evaluation import EvaluationReport


router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/retrieval", response_model=EvaluationReport)
def retrieval_evaluation(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> EvaluationReport:
    report = run_eval()
    record_evaluation_run(report)
    return EvaluationReport.model_validate(report)
