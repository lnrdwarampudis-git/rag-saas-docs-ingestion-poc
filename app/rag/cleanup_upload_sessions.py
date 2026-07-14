import argparse

from app.rag.upload_sessions import cleanup_stale_upload_sessions


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up stale resumable upload sessions.")
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=None,
        help="Remove upload sessions older than this age. Defaults to settings.",
    )
    args = parser.parse_args()
    result = cleanup_stale_upload_sessions(max_age_hours=args.max_age_hours)
    print(
        "Upload session cleanup: "
        f"sessions_removed={result.sessions_removed} "
        f"parts_removed={result.parts_removed} "
        f"bytes_removed={result.bytes_removed}"
    )


if __name__ == "__main__":
    main()
