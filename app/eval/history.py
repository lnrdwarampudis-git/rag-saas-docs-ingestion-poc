from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.rag.analytics import _ensure_evaluation_runs_table, _metadata_sql_expression


def record_evaluation_run(report: dict) -> None:
    if not get_settings().enable_db_persistence:
        return

    summary = report["summary"]
    try:
        from app.db import engine

        with engine.begin() as connection:
            _ensure_evaluation_runs_table(connection)
            connection.execute(
                text(
                    f"""
                    INSERT INTO evaluation_runs (
                      cases, passed, failed, context_precision, context_recall,
                      answer_relevance, answer_groundedness, report
                    )
                    VALUES (
                      :cases, :passed, :failed, :context_precision, :context_recall,
                      :answer_relevance, :answer_groundedness,
                      {_metadata_sql_expression(connection)}
                    )
                    """
                ),
                {
                    "cases": int(summary["cases"]),
                    "passed": int(summary["passed"]),
                    "failed": int(summary["failed"]),
                    "context_precision": float(summary["context_precision"]),
                    "context_recall": float(summary["context_recall"]),
                    "answer_relevance": float(summary["answer_relevance"]),
                    "answer_groundedness": float(summary["answer_groundedness"]),
                    "metadata": json.dumps(report),
                },
            )
    except SQLAlchemyError:
        return
