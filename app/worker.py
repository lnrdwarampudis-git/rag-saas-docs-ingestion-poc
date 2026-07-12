import logging

from app.rag.jobs import process_next_queued_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Starting RAG document processing worker")
    while True:
        result = process_next_queued_job(timeout_seconds=10)
        if result is not None:
            logger.info(
                "Processed job %s for document %s with status=%s",
                result.job_id,
                result.document_id,
                result.status,
            )


if __name__ == "__main__":
    main()
