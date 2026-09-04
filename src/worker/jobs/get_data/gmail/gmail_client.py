from __future__ import annotations

import base64
import logging
import os
import pickle

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Gmail configuration
# ----------------------------------------------------------------------

# Must stay in sync with gmail_token_init.py
SCOPES = [
    "https://mail.google.com/",
]

# Environment variables take precedence.
#
# Local example:
# GMAIL_CREDENTIALS_PATH=C:\Users\erik\Code\bokser_app\secrets\google\gmail_credentials.json
# GMAIL_TOKEN_PATH=C:\Users\erik\Code\bokser_app\secrets\google\gmail_token.pickle
#
# Docker example:
# GMAIL_CREDENTIALS_PATH=/run/secrets/gmail_credentials.json
# GMAIL_TOKEN_PATH=/run/secrets/gmail_token.pickle


MAX_EMAILS_PER_REQUEST = 500
DEFAULT_MAX_RESULTS = 50


class GmailClient:

    def __init__(
        self,
        credentials_file: str | None = None,
        token_file: str | None = None,
    ) -> None:

        self.credentials_file = (
            credentials_file
            or os.environ.get("GMAIL_CREDENTIALS_PATH")
            or "credentials/gmail_api/gmail_credentials.json"
        )

        self.token_file = (
            token_file
            or os.environ.get("GMAIL_TOKEN_PATH")
            or "credentials/gmail_api/gmail_token.pickle"
        )

        self.service = None
        self._label_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _get_credentials(self) -> Credentials:
        """
        Load Gmail OAuth credentials from the pre-generated token pickle.

        If the access token has expired and a refresh token is available,
        refresh the credentials and persist the updated token.

        gmail_token_init.py must be run locally before this client is used.
        """

        if not os.path.exists(self.token_file):
            raise FileNotFoundError(
                f"Gmail token file not found: {self.token_file}. "
                "Run gmail_token_init.py locally first."
            )

        try:
            with open(self.token_file, "rb") as token:
                creds = pickle.load(token)

        except Exception as exc:
            raise RuntimeError(
                f"Unable to load Gmail token file: " f"{self.token_file}"
            ) from exc

        if not isinstance(creds, Credentials):
            raise RuntimeError(
                f"Invalid Gmail credentials object in " f"{self.token_file}"
            )

        # --------------------------------------------------------------
        # Validate scopes
        # --------------------------------------------------------------

        expected_scopes = set(SCOPES)
        granted_scopes = set(creds.scopes or [])

        if not expected_scopes.issubset(granted_scopes):
            missing = expected_scopes - granted_scopes

            raise RuntimeError(
                f"Gmail token {self.token_file} is missing "
                f"required scopes: "
                f"{', '.join(sorted(missing))}. "
                "Delete the token and rerun gmail_token_init.py."
            )

        # --------------------------------------------------------------
        # Refresh expired access token
        # --------------------------------------------------------------

        if creds.expired:
            if not creds.refresh_token:
                raise RuntimeError(
                    "Gmail access token has expired and no "
                    "refresh token is available. "
                    "Rerun gmail_token_init.py."
                )

            try:
                creds.refresh(Request())

            except Exception as exc:
                raise RuntimeError(
                    "Failed to refresh Gmail OAuth credentials."
                ) from exc

            # Persist the refreshed credential state.
            try:
                with open(self.token_file, "wb") as token:
                    pickle.dump(creds, token)

            except Exception as exc:
                raise RuntimeError(
                    f"Gmail credentials refreshed successfully, "
                    f"but the updated token could not be written "
                    f"to {self.token_file}"
                ) from exc

        if not creds.valid:
            raise RuntimeError(
                "Gmail credentials are invalid and could not "
                "be refreshed. Rerun gmail_token_init.py."
            )

        return creds

    def _get_service(self):
        """
        Return the Gmail API service, creating it on first use.
        """

        if self.service is None:
            creds = self._get_credentials()

            self.service = build(
                "gmail",
                "v1",
                credentials=creds,
                cache_discovery=False,
            )

        return self.service

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    def _get_label_id(
        self,
        label_name: str,
    ) -> str | None:
        """
        Return an existing Gmail label ID if present.
        """

        if label_name in self._label_cache:
            return self._label_cache[label_name]

        service = self._get_service()

        response = service.users().labels().list(userId="me").execute()

        for label in response.get("labels", []):
            if label.get("name") == label_name:
                label_id = label["id"]

                self._label_cache[label_name] = label_id

                return label_id

        return None

    def ensure_label(
        self,
        label_name: str = "PROCESSED",
    ) -> str:
        """
        Ensure a Gmail label exists and return its ID.
        """

        label_id = self._get_label_id(label_name)

        if label_id:
            return label_id

        service = self._get_service()

        created = (
            service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": label_name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )

        label_id = created["id"]

        self._label_cache[label_name] = label_id

        return label_id

    def mark_processed(
        self,
        message_id: str,
        label_name: str = "PROCESSED",
    ) -> None:
        """
        Mark a Gmail message as processed.

        Adds the requested label and removes INBOX and UNREAD.
        """

        try:
            label_id = self.ensure_label(label_name)

            service = self._get_service()

            (
                service.users()
                .messages()
                .modify(
                    userId="me",
                    id=message_id,
                    body={
                        "addLabelIds": [label_id],
                        "removeLabelIds": [
                            "INBOX",
                            "UNREAD",
                        ],
                    },
                )
                .execute()
            )

            logger.info(
                "Marked Gmail message %s as processed " "with label %s",
                message_id,
                label_name,
            )

        except Exception:
            logger.exception(
                "Failed to mark Gmail message %s as processed",
                message_id,
            )
            raise

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def fetch_emails(
        self,
        query: str = "has:attachment",
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> list[dict[str, Any]]:
        """
        Fetch Gmail messages matching a search query.

        Args:
            query:
                Gmail search query.

            max_results:
                Maximum number of messages to return.

        Returns:
            Gmail message references containing id/threadId.
        """

        try:
            service = self._get_service()

            results = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=min(
                        max_results,
                        MAX_EMAILS_PER_REQUEST,
                    ),
                )
                .execute()
            )

            messages = results.get("messages", [])

            logger.info(
                "Found %s Gmail messages matching query: %s",
                len(messages),
                query,
            )

            return messages

        except Exception:
            logger.exception(
                "Error fetching Gmail messages " "for query: %s",
                query,
            )
            raise

    async def get_email_details(
        self,
        message_id: str,
    ) -> dict[str, Any]:
        """
        Return basic metadata for a Gmail message.
        """

        try:
            service = self._get_service()

            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=[
                        "Subject",
                        "From",
                        "Date",
                    ],
                )
                .execute()
            )

            headers = {
                header["name"]: header["value"]
                for header in (message.get("payload", {}).get("headers", []))
            }

            date_str = headers.get("Date", "")

            try:
                email_date = parsedate_to_datetime(date_str)

            except (TypeError, ValueError):
                email_date = datetime.now(timezone.utc)

            return {
                "id": message_id,
                "subject": headers.get(
                    "Subject",
                    "No Subject",
                ),
                "from": headers.get(
                    "From",
                    "Unknown",
                ),
                "date": email_date,
            }

        except Exception:
            logger.exception(
                "Error getting Gmail message details " "for %s",
                message_id,
            )

            return {
                "id": message_id,
                "subject": "Unknown",
                "from": "Unknown",
                "date": datetime.now(timezone.utc),
            }

    # ------------------------------------------------------------------
    # Attachments
    # ------------------------------------------------------------------

    async def get_attachments(
        self,
        message_id: str,
    ) -> list[dict[str, Any]]:
        """
        Download all attachments from a Gmail message.

        Returns:
            List of dictionaries containing:
                filename
                data
                mimeType
                size
        """

        try:
            service = self._get_service()

            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="full",
                )
                .execute()
            )

            payload = message.get("payload", {})

            parts = payload.get("parts")

            if not parts:
                parts = [payload]

            attachments: list[dict[str, Any]] = []

            for part in parts:
                attachments.extend(
                    self._extract_attachments_from_part(
                        service,
                        message_id,
                        part,
                    )
                )

            logger.info(
                "Found %s attachments in Gmail " "message %s",
                len(attachments),
                message_id,
            )

            return attachments

        except Exception:
            logger.exception(
                "Error getting Gmail attachments " "for message %s",
                message_id,
            )

            return []

    def _extract_attachments_from_part(
        self,
        service: Any,
        message_id: str,
        part: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Recursively extract Gmail attachments from MIME parts.
        """

        attachments: list[dict[str, Any]] = []

        filename = part.get("filename")
        body = part.get("body") or {}
        attachment_id = body.get("attachmentId")

        # --------------------------------------------------------------
        # Attachment
        # --------------------------------------------------------------

        if filename and attachment_id:
            try:
                attachment = (
                    service.users()
                    .messages()
                    .attachments()
                    .get(
                        userId="me",
                        messageId=message_id,
                        id=attachment_id,
                    )
                    .execute()
                )

                encoded_data = attachment.get("data")

                if not encoded_data:
                    raise ValueError(f"No attachment data returned " f"for {filename}")

                data = base64.urlsafe_b64decode(encoded_data)

                attachments.append(
                    {
                        "filename": filename,
                        "data": data,
                        "mimeType": part.get(
                            "mimeType",
                            "application/octet-stream",
                        ),
                        "size": len(data),
                    }
                )

            except Exception:
                logger.exception(
                    "Error downloading Gmail attachment " "%s from message %s",
                    filename,
                    message_id,
                )

        # --------------------------------------------------------------
        # Nested MIME parts
        # --------------------------------------------------------------

        for subpart in part.get("parts") or []:
            attachments.extend(
                self._extract_attachments_from_part(
                    service,
                    message_id,
                    subpart,
                )
            )

        return attachments
