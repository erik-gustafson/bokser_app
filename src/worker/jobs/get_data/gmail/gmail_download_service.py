import logging

from typing import List, Optional
from pathlib import Path

from src.database.database import async_session
from src.storage.raw.writer import RawPayloadWriter
from src.storage.raw.utils import write_file_to_data_lake
from src.worker.jobs.get_data.gmail.gmail_client import GmailClient
from src.worker.jobs.process_data.sutton.process_sutton_reporting import (
    SuttonReportManager,
    SuttonReportTasks,
)

logger = logging.getLogger(__name__)


class GmailDownloadService:
    def __init__(self):
        self.gmail_client = GmailClient()
        self.sutton_report_tasks = SuttonReportTasks()

    async def download_attachments_background(
        self,
        search_query: str,
        source_name: str,
        raw_writer: RawPayloadWriter,
        max_results: int,
        file_types: Optional[List[str]],
    ):
        """
        Background task to download attachments from Gmail to NAS
        """

        try:

            async with async_session() as session:
                async with session.begin():
                    logger.info(f"Fetching emails with query: {search_query}")
                    emails = await self.gmail_client.fetch_emails(
                        query=search_query, max_results=max_results
                    )

                    if not emails:
                        logger.info(f"No Emails Found with query: {search_query}")
                        return

                    # 3. Process each email
                    downloaded_files = 0
                    errors = []

                    for email in emails:
                        try:
                            # Get email metadata
                            email_details = await self.gmail_client.get_email_details(
                                email["id"]
                            )

                            # Get attachments
                            attachments = await self.gmail_client.get_attachments(
                                email["id"]
                            )
                            saved_any = False

                            for attachment in attachments:
                                try:
                                    # Filter by file type if specified
                                    if file_types:
                                        ext = (
                                            attachment["filename"]
                                            .split(".")[-1]
                                            .lower()
                                        )
                                        if ext not in file_types:
                                            continue

                                    filename = attachment["filename"]

                                    if source_name == "sutton":
                                        entity_name = self.sutton_report_tasks.normalize_report_name(
                                            filename
                                        )
                                    elif source_name == "guest_supply":
                                        entity_name = "purchase_orders"
                                    else:
                                        entity_name = "undefined_report"

                                    await write_file_to_data_lake(
                                        session=session,
                                        raw_writer=raw_writer,
                                        source_name=source_name,
                                        entity_name=entity_name,
                                        file_bytes=attachment["data"],
                                        file_type=Path(filename).suffix,
                                        original_file_name=filename,
                                        metadata={
                                            "gmail_message_id": email["id"],
                                            "email_subject": email_details["subject"],
                                            "email_date": email_details["date"],
                                            "gmail_mime_type": attachment["mimeType"],
                                        },
                                        commit=False,
                                    )

                                    downloaded_files += 1

                                    saved_any = True

                                    logger.info(
                                        f"Downloaded {attachment['filename']} ({len(attachment['data'])} bytes)"
                                    )

                                except Exception as e:
                                    error_msg = f"Failed to download {attachment['filename']}: {str(e)}"
                                    errors.append(error_msg)
                                    logger.error(f"Download Error: {error_msg}")

                            if saved_any:
                                try:
                                    self.gmail_client.mark_processed(email["id"])
                                except Exception as e:
                                    errors.append(
                                        f"Label/mark-read failed for {email['id']}: {e}"
                                    )
                                    logger.error(
                                        f"Error:: Could not mark email processed: {e}"
                                    )

                        except Exception as e:
                            error_msg = (
                                f"Error processing email {email['id']}: {str(e)}"
                            )
                            errors.append(error_msg)
                            logger.error(f"Error: {error_msg}")

            logger.info(
                f"Gmail Download Complete. Downloaded {downloaded_files} files, {len(errors)} errors"
            )

        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")


# Singleton instance
gmail_download_service = GmailDownloadService()
