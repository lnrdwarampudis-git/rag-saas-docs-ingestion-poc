from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import Settings, get_settings
from app.rag.analytics import (
    _ensure_evaluation_runs_table,
    _ensure_model_latency_events_table,
    _ensure_processing_job_events_table,
    _ensure_query_events_table,
)


@dataclass(frozen=True)
class RetentionTableResult:
    table_name: str
    retention_days: int
    cutoff: str
    rows_matched: int
    rows_deleted: int


@dataclass(frozen=True)
class RetentionRunResult:
    dry_run: bool
    skipped: bool = False
    reason: str = ""
    tables: list[RetentionTableResult] = field(default_factory=list)

    @property
    def total_deleted(self) -> int:
        return sum(table.rows_deleted for table in self.tables)

    @property
    def total_matched(self) -> int:
        return sum(table.rows_matched for table in self.tables)


def run_ops_history_retention(
    *,
    dry_run: bool = False,
    query_events_days: int | None = None,
    model_latency_events_days: int | None = None,
    processing_job_events_days: int | None = None,
    evaluation_runs_days: int | None = None,
    settings: Settings | None = None,
) -> RetentionRunResult:
    settings = settings or get_settings()
    if not settings.enable_db_persistence:
        return RetentionRunResult(
            dry_run=dry_run,
            skipped=True,
            reason="ENABLE_DB_PERSISTENCE is false.",
        )

    from app.db import engine

    with engine.begin() as connection:
        _ensure_query_events_table(connection)
        _ensure_model_latency_events_table(connection)
        _ensure_processing_job_events_table(connection)
        _ensure_evaluation_runs_table(connection)
        table_specs = [
            ("query_events", _retention_days(query_events_days, settings.query_events_retention_days)),
            (
                "model_latency_events",
                _retention_days(
                    model_latency_events_days,
                    settings.model_latency_events_retention_days,
                ),
            ),
            (
                "processing_job_events",
                _retention_days(
                    processing_job_events_days,
                    settings.processing_job_events_retention_days,
                ),
            ),
            ("evaluation_runs", _retention_days(evaluation_runs_days, settings.evaluation_runs_retention_days)),
        ]
        return RetentionRunResult(
            dry_run=dry_run,
            tables=[
                _apply_table_retention(connection, table_name, days, dry_run=dry_run)
                for table_name, days in table_specs
            ],
        )


def _apply_table_retention(
    connection: Connection,
    table_name: str,
    retention_days: int,
    *,
    dry_run: bool,
) -> RetentionTableResult:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    cutoff_value = _cutoff_value(connection, cutoff)
    rows_matched = int(
        connection.execute(
            text(f"SELECT count(*) FROM {table_name} WHERE created_at < :cutoff"),
            {"cutoff": cutoff_value},
        ).scalar_one()
        or 0
    )
    rows_deleted = 0
    if not dry_run and rows_matched:
        result = connection.execute(
            text(f"DELETE FROM {table_name} WHERE created_at < :cutoff"),
            {"cutoff": cutoff_value},
        )
        rows_deleted = int(result.rowcount or 0)
    return RetentionTableResult(
        table_name=table_name,
        retention_days=retention_days,
        cutoff=_cutoff_string(cutoff),
        rows_matched=rows_matched,
        rows_deleted=rows_deleted,
    )


def _retention_days(override: int | None, configured: int) -> int:
    return max(1, int(override if override is not None else configured))


def _cutoff_value(connection: Connection, cutoff: datetime):
    if connection.dialect.name == "postgresql":
        return cutoff
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")


def _cutoff_string(cutoff: datetime) -> str:
    return cutoff.replace(microsecond=0).isoformat().replace("+00:00", "Z")
