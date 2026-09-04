import logging

from src.storage.raw.writer import RawPayloadWriter
from src.worker.jobs.get_data.gmail.gmail_download_service import gmail_download_service
from src.database.database import async_session

# from app.worker.services.guest_supply_order_service import (
#     GuestSupplyPOService,
# )
from src.worker.jobs.get_data.gmail.gmail_schemas import EmailDownloadRequest

logger = logging.getLogger(__name__)


class GmailTasks:

    def __init__(self):
        self.request = EmailDownloadRequest()
        # self.guest_service = GuestSupplyPOService()

    # async def guest_supply_pdf_download(self):
    #     """Download invoices every night at 2 AM"""
    #     db = SessionLocal()
    #     try:
    #         job_id = gmail_download_service.create_job_id()
    #         await gmail_download_service.download_attachments_background(
    #             job_id=job_id,
    #             search_query=self.request.guest_supply_pdf_gmail_query,
    #             download_path="guest_supply_pdfs/downloaded",
    #             max_results=100,
    #             file_types=["pdf", "PDF"],
    #             db=db,
    #         )
    #     finally:
    #         db.close()

    async def sutton_report_download(
        self,
        raw_writer: RawPayloadWriter,
    ):
        """Download invoices every night at 2 AM"""
        try:
            await gmail_download_service.download_attachments_background(
                search_query=self.request.sutton_report_gmail_query,
                source_name="sutton",
                raw_writer=raw_writer,
                max_results=10000,
                file_types=["xls", "XLS"],
            )
        except Exception as exc:
            logger.exception(f"Sutton Report Download Failed with exception: {exc}")

    # async def run_guest_supply_po_process(self):

    #     db = SessionLocal()
    #     try:
    #         job_id = gmail_download_service.create_job_id()
    #         await gmail_download_service.download_attachments_background(
    #             job_id=job_id,
    #             search_query=self.request.guest_supply_pdf_gmail_query,
    #             download_path="guest_supply_pdfs/downloaded",
    #             max_results=100,
    #             file_types=["pdf", "PDF"],
    #             db=db,
    #         )
    #     finally:
    #         db.close()

    #     logger.info("Starting Guest Supply PO PDF processing task")

    #     try:
    #         results = await self.guest_service.process_all_guest_supply_pdfs()

    #         logger.info(
    #             f"Guest Supply PO Processing Complete - "
    #             f"Processed: {results['processed']}, "
    #             f"Failed: {results['failed']}, "
    #             f"Total Lines: {results['total_order_lines']}"
    #         )

    #     except Exception as e:
    #         logger.error(
    #             f"Fatal error in Guest Supply PO processing task: {e}", exc_info=True
    #         )
    #         raise
