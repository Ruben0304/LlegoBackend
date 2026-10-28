"""Background worker for processing pending menu OCR tasks."""

from repositories import branch_menus_repo
from services.menu_ocr_service import process_menu


async def process_pending_menus(batch_limit: int = 5, stale_after_seconds: int = 600) -> int:
    """Process pending menus in batches.

    Requeues stale tasks first, then processes up to batch_limit menus.
    A failure in one menu does not stop processing of others.

    Args:
        batch_limit: Maximum menus to process per call
        stale_after_seconds: Requeue tasks stuck in processing for > N seconds

    Returns:
        Number of menus successfully processed
    """
    # Requeue stale processing tasks
    requeued = await branch_menus_repo.requeue_stale_processing(stale_after_seconds)
    if requeued > 0:
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"Requeued {requeued} stale menus back to pending")

    # Process up to batch_limit menus
    processed = 0
    for _ in range(batch_limit):
        menu = await branch_menus_repo.claim_next_pending()
        if menu is None:
            break

        success = await process_menu(menu)
        if success:
            processed += 1

    return processed
