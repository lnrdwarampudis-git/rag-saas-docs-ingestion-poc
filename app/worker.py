import logging

from app.config import get_settings
from app.rag.jobs import process_next_queued_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    queues = [
        queue.strip()
        for queue in settings.worker_queue_names.split(",")
        if queue.strip()
    ] or [settings.processing_queue_name]
    logger.info("Starting RAG document processing worker for queues=%s", queues)
    while True:
        result = process_next_queued_job(timeout_seconds=10, queue_names=queues)
        if result is not None:
            logger.info(
                "Processed job %s for document %s with status=%s",
                result.job_id,
                result.document_id,
                result.status,
            )


if __name__ == "__main__":
    main()
