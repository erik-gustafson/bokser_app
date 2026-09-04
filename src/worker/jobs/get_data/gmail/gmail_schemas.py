from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


class EmailDownloadRequest(BaseModel):
    search_query: str = Field(
        default="has:attachment", description="Gmail search query"
    )
    guest_supply_pdf_gmail_query: str = Field(
        default="Dispatched Purchase Order has:attachment label:unread",
        description="Guest Supply Order PDF search query",
    )
    sutton_report_gmail_query: str = Field(
        default="has:attachment from:REPORT-FROM-AS400@essutton.com label:unread",
        description="Sutton Report search query",
    )
    download_path: Optional[str] = Field(
        default=None, description="Optional subdirectory on NAS (e.g., 'invoices/2024')"
    )
    max_results: int = Field(
        default=50, ge=1, le=500, description="Maximum number of emails to process"
    )
    file_types: Optional[List[str]] = Field(
        default=None, description="Filter by file extensions (e.g., ['pdf', 'xlsx'])"
    )

    @field_validator("file_types")
    @classmethod
    def validate_file_types(cls, v):
        if v:
            return [ext.lower().strip(".") for ext in v]
        return v
