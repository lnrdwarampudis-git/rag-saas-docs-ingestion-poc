import argparse

from app.rag.retention import run_ops_history_retention


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up persisted operations history tables.")
    parser.add_argument("--dry-run", action="store_true", help="Count matching rows without deleting them.")
    parser.add_argument("--query-events-days", type=int, default=None)
    parser.add_argument("--model-latency-events-days", type=int, default=None)
    parser.add_argument("--processing-job-events-days", type=int, default=None)
    parser.add_argument("--evaluation-runs-days", type=int, default=None)
    args = parser.parse_args()

    result = run_ops_history_retention(
        dry_run=args.dry_run,
        query_events_days=args.query_events_days,
        model_latency_events_days=args.model_latency_events_days,
        processing_job_events_days=args.processing_job_events_days,
        evaluation_runs_days=args.evaluation_runs_days,
    )
    if result.skipped:
        print(f"Ops history cleanup skipped: {result.reason}")
        return

    mode = "dry-run" if result.dry_run else "delete"
    print(
        f"Ops history cleanup ({mode}): "
        f"matched={result.total_matched} deleted={result.total_deleted}"
    )
    for table in result.tables:
        print(
            f"- {table.table_name}: retention_days={table.retention_days} "
            f"cutoff={table.cutoff} matched={table.rows_matched} "
            f"deleted={table.rows_deleted}"
        )


if __name__ == "__main__":
    main()
