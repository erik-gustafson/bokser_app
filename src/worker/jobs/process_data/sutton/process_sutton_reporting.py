from __future__ import annotations

import logging
import os

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from dateutil import parser

from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from src.database.database import SessionLocal, async_session
from src.database.models import *
from src.worker.jobs.process_data.utils import data_lake_tools
from src.worker.jobs.process_data.utils.data_lake_tools import ClaimedLakeFile

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Sutton Data Lake Configuration
# ----------------------------------------------------------------------

# CHANGE THESE TO MATCH DataLakeFile.source_name / entity_name
SUTTON_ENTITIES = [
    ("sutton", "sales_report"),
    ("sutton", "inventory_report"),
    ("sutton", "open_order_report"),
    ("sutton", "edi_load_report"),
    ("sutton", "order_submission_report"),
]

REPORT_ENTITY_MAP = {
    "SLS003T": "sales_report",
    "INVENAVL": "inventory_report",
    "oo": "open_order_report",
    "EDILDT": "edi_load_report",
    "Order": "order_submission_report",
}


# ----------------------------------------------------------------------
# Optional local development lake-path translation
# ----------------------------------------------------------------------


def resolve_lake_path(file_path: str) -> Path:
    """
    Resolve a DataLakeFile path.

    In Docker/production, the DataLakeFile path is used directly.

    For Windows local development, set:

        SUTTON_LOCAL_LAKE_ROOT=X:\\data_lake\\prod

    If the database contains paths beginning with /app/data_lake,
    they will be translated to that local root.
    """

    path = Path(file_path)

    local_root = os.environ.get("SUTTON_LOCAL_LAKE_ROOT")

    if not local_root:
        return path

    container_root = Path("/app/data_lake")

    try:
        relative_path = path.relative_to(container_root)
    except ValueError:
        return path

    return Path(local_root) / relative_path


# ======================================================================
# Task
# ======================================================================


class SuttonReportTasks:

    def __init__(self) -> None:
        self.service = SuttonReportProcessor()

    async def process_sutton_reports(self) -> None:

        logger.info("Starting Sutton data lake report processing")

        try:
            stats = await self.service.process_sutton_lake_files(
                entities=SUTTON_ENTITIES,
            )

            logger.info(
                "Sutton processing complete - "
                "claimed=%s, loaded=%s, skipped=%s, "
                "failed=%s, records_processed=%s, "
                "inserted=%s, updated=%s, "
                "records_skipped=%s",
                stats["claimed"],
                stats["loaded"],
                stats["skipped"],
                stats["failed"],
                stats["records_processed"],
                stats["records_inserted"],
                stats["records_updated"],
                stats["records_skipped"],
            )

        except Exception:
            logger.exception("Fatal error in Sutton report processing")
            raise

    @classmethod
    def normalize_report_name(
        cls,
        raw_name: str,
    ) -> str:

        report_code = raw_name.split("_")[0]

        try:
            return REPORT_ENTITY_MAP[report_code]
        except KeyError:
            logger.error(
                "Unknown Sutton report name: %s",
                report_code,
            )
            return "undefined_report"


# ======================================================================
# Report Manager
# ======================================================================


class SuttonReportManager:
    """
    Categorize Sutton reports.

    Snapshot reports:
        Keep only the highest Sutton file ID.

    Historical/additive reports:
        Keep every file.

    Raw data-lake files are NEVER deleted.
    """

    def __init__(self) -> None:

        self.report_dicts: dict[
            str,
            list[
                tuple[
                    str,
                    Path,
                    str | None,
                ]
            ],
        ] = defaultdict(list)

    def add_report(
        self,
        report_type: str,
        file_id: str,
        report: Path,
        max_file_id_type: set[str] | None = None,
    ) -> None:

        max_file_id_type = max_file_id_type or set()

        # --------------------------------------------------------------
        # Determine Excel sheet
        # --------------------------------------------------------------

        if report_type == "INVENAVL":
            sheet_name = "INVEN"

        elif report_type == "EDILDT":
            sheet_names = pd.ExcelFile(report).sheet_names

            if len(sheet_names) < 2:
                raise ValueError(
                    f"EDILDT report {report.name} " "does not contain a second sheet"
                )

            sheet_name = sheet_names[1]

        else:
            sheet_name = None

        report_tuple = (
            file_id,
            report,
            sheet_name,
        )

        # --------------------------------------------------------------
        # Additive / historical report
        # --------------------------------------------------------------

        if report_type not in max_file_id_type:

            self.report_dicts[report_type].append(report_tuple)

            return

        # --------------------------------------------------------------
        # Snapshot report
        #
        # Only retain the report with the highest Sutton file ID.
        # --------------------------------------------------------------

        current = self.report_dicts[report_type]

        if not current:
            current.append(report_tuple)
            return

        existing_id = current[0][0]

        try:
            incoming_numeric_id = int(file_id)

            existing_numeric_id = int(existing_id)

        except ValueError as exc:
            raise ValueError(
                f"Unable to compare Sutton snapshot IDs "
                f"for {report_type}: "
                f"existing={existing_id!r}, "
                f"incoming={file_id!r}"
            ) from exc

        if incoming_numeric_id <= existing_numeric_id:
            return

        logger.info(
            "Replacing selected %s Sutton snapshot: " "%s -> %s",
            report_type,
            existing_id,
            file_id,
        )

        current[0] = report_tuple


# ======================================================================
# Sutton Processor
# ======================================================================


class SuttonReportProcessor:
    """
    Read Sutton files from the data lake, select appropriate files,
    load report data to Postgres, and update DataLakeFile status.
    """

    def __init__(self) -> None:

        self.sutton_reports = SuttonReportManager()

        # Reports representing the current snapshot.
        #
        # Only the highest Sutton file ID should be processed.
        self.overwrite = {
            "INVENAVL",
            "oo",
        }

        # Reports that should never be loaded.
        self.ignore = {
            "cnt004",
        }

    # ==================================================================
    # Main orchestration
    # ==================================================================

    async def process_sutton_lake_files(
        self,
        *,
        entities: list[tuple[str, str]],
        claim_batch_size: int = 100,
    ) -> dict[str, Any]:

        stats: dict[str, Any] = {
            "claimed": 0,
            "loaded": 0,
            "skipped": 0,
            "failed": 0,
            "records_processed": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "records_skipped": 0,
            "errors": [],
        }

        # --------------------------------------------------------------
        # 1. Claim ALL available Sutton lake files.
        #
        # We must see every unprocessed snapshot file before deciding
        # which snapshot is newest.
        # --------------------------------------------------------------

        claimed_files: list[ClaimedLakeFile] = []

        for source_name, entity_name in entities:
            claimed_files.extend(
                await self._claim_all_lake_files(
                    source_name=source_name,
                    entity_name=entity_name,
                    batch_size=claim_batch_size,
                )
            )

        stats["claimed"] = len(claimed_files)

        if not claimed_files:

            logger.info("No Sutton lake files available " "for processing")

            return stats

        logger.info(
            "Claimed %s Sutton lake files",
            len(claimed_files),
        )

        # --------------------------------------------------------------
        # 2. Categorize all claimed files before processing anything.
        # --------------------------------------------------------------

        self.sutton_reports = SuttonReportManager()

        usable_files: dict[Path, ClaimedLakeFile] = {}

        ignored_files: list[ClaimedLakeFile] = []

        invalid_files: list[tuple[ClaimedLakeFile, str]] = []

        for lake_file in claimed_files:

            try:
                path = resolve_lake_path(lake_file.file_path)

                if not path.exists():
                    raise FileNotFoundError(f"Sutton lake file " f"not found: {path}")

                report_type, file_id = self._filetype(path)

                if not report_type or not file_id:
                    raise ValueError(
                        f"Unable to determine Sutton "
                        f"report type/file ID from "
                        f"{path.name}"
                    )

                if report_type in self.ignore:

                    logger.info(
                        "Ignoring Sutton report %s",
                        path.name,
                    )

                    ignored_files.append(lake_file)

                    continue

                self.sutton_reports.add_report(
                    report_type=report_type,
                    file_id=file_id,
                    report=path,
                    max_file_id_type=(self.overwrite),
                )

                usable_files[path] = lake_file

            except Exception as exc:

                logger.exception(
                    "Failed to categorize Sutton " "lake file id=%s path=%s",
                    lake_file.id,
                    lake_file.file_path,
                )

                invalid_files.append(
                    (
                        lake_file,
                        str(exc),
                    )
                )

        # --------------------------------------------------------------
        # 3. Determine selected vs superseded files.
        # --------------------------------------------------------------

        selected_paths = {
            report_path
            for report_tuples in self.sutton_reports.report_dicts.values()
            for _, report_path, _ in report_tuples
        }

        selected_files = {
            path: lake_file
            for path, lake_file in usable_files.items()
            if path in selected_paths
        }

        superseded_files = [
            lake_file
            for path, lake_file in usable_files.items()
            if path not in selected_paths
        ]

        # --------------------------------------------------------------
        # 4. Mark ignored files SKIPPED.
        # --------------------------------------------------------------

        for lake_file in ignored_files:

            await self._mark_lake_file_skipped(
                lake_file.id,
                reason=("Ignored Sutton report type"),
            )

            stats["skipped"] += 1

        # --------------------------------------------------------------
        # 5. Mark superseded snapshots SKIPPED.
        #
        # Raw files remain in the data lake.
        # --------------------------------------------------------------

        for lake_file in superseded_files:

            await self._mark_lake_file_skipped(
                lake_file.id,
                reason=("Superseded by newer Sutton " "snapshot based on file ID"),
            )

            stats["skipped"] += 1

        # --------------------------------------------------------------
        # 6. Mark malformed / unreadable files FAILED.
        # --------------------------------------------------------------

        for (
            lake_file,
            error,
        ) in invalid_files:

            await self._mark_lake_file_failed(
                lake_file.id,
                error=error,
            )

            stats["failed"] += 1

            stats["errors"].append(
                {
                    "file_id": (lake_file.id),
                    "file_path": (lake_file.file_path),
                    "error": error,
                }
            )

        # --------------------------------------------------------------
        # 7. Process each selected file.
        #
        # Process files individually so each DataLakeFile gets an
        # accurate LOADED / FAILED state.
        # --------------------------------------------------------------

        for (
            report_name,
            report_tuples,
        ) in self.sutton_reports.report_dicts.items():

            for report_tuple in report_tuples:

                _, report_path, _ = report_tuple

                lake_file = selected_files.get(report_path)

                if lake_file is None:

                    logger.error(
                        "Unable to locate DataLakeFile "
                        "for selected Sutton report %s",
                        report_path,
                    )

                    continue

                try:
                    result = self.process_sutton_report(
                        report_name,
                        [report_tuple],
                    )

                    stats["records_processed"] += result.get(
                        "records_processed",
                        0,
                    )

                    stats["records_inserted"] += result.get(
                        "records_inserted",
                        0,
                    )

                    stats["records_updated"] += result.get(
                        "records_updated",
                        0,
                    )

                    stats["records_skipped"] += result.get(
                        "records_skipped",
                        0,
                    )

                    result_errors = result.get(
                        "errors",
                        0,
                    )

                    # If rows failed but the report otherwise
                    # completed, treat the file as PARTIAL.
                    if result_errors:

                        await self._mark_lake_file_partial(
                            lake_file.id,
                            loaded_count=(
                                result.get(
                                    "records_inserted",
                                    0,
                                )
                                + result.get(
                                    "records_updated",
                                    0,
                                )
                                + result.get(
                                    "records_skipped",
                                    0,
                                )
                            ),
                            failed_count=(result_errors),
                            error_details=(
                                result.get(
                                    "error_details",
                                    [],
                                )
                            ),
                        )

                        stats["failed"] += 1

                        stats["errors"].append(
                            {
                                "file_id": (lake_file.id),
                                "file_path": (lake_file.file_path),
                                "error": (
                                    result.get(
                                        "error_details",
                                        [],
                                    )
                                ),
                            }
                        )

                        continue

                    await self._mark_lake_file_loaded(
                        lake_file.id,
                        loaded_count=(
                            result.get(
                                "records_processed",
                                0,
                            )
                        ),
                    )

                    stats["loaded"] += 1

                except Exception as exc:

                    logger.exception(
                        "Failed processing Sutton " "report type=%s file=%s",
                        report_name,
                        report_path,
                    )

                    await self._mark_lake_file_failed(
                        lake_file.id,
                        error=str(exc),
                    )

                    stats["failed"] += 1

                    stats["errors"].append(
                        {
                            "file_id": (lake_file.id),
                            "file_path": (lake_file.file_path),
                            "error": str(exc),
                        }
                    )

        return stats

    # ==================================================================
    # Claim all DataLakeFile rows
    # ==================================================================

    async def _claim_all_lake_files(
        self,
        *,
        source_name: str,
        entity_name: str,
        batch_size: int = 100,
    ) -> list[ClaimedLakeFile]:

        claimed: list[ClaimedLakeFile] = []

        while True:
            async with async_session() as session:
                async with session.begin():
                    batch = await data_lake_tools.claim_lake_files(
                        session,
                        source_name=source_name,
                        entity_name=entity_name,
                        limit=batch_size,
                    )

            if not batch:
                break

            claimed.extend(batch)

            logger.info(
                "Claimed %s Sutton %s files; running total=%s",
                len(batch),
                entity_name,
                len(claimed),
            )

        return claimed

    # ==================================================================
    # DataLakeFile state updates
    # ==================================================================

    async def _mark_lake_file_loaded(
        self,
        file_id: int,
        *,
        loaded_count: int,
    ) -> None:

        async with async_session() as session:

            async with session.begin():

                db_file = await session.get(
                    DataLakeFile,
                    file_id,
                    with_for_update=True,
                )

                if db_file is None:
                    raise RuntimeError(f"DataLakeFile " f"id={file_id} disappeared")

                db_file.status = "LOADED"

                db_file.processed_at = datetime.now(timezone.utc)

                db_file.loaded_count = loaded_count

                db_file.skipped_count = 0
                db_file.failed_count = 0
                db_file.last_error = None

    async def _mark_lake_file_skipped(
        self,
        file_id: int,
        *,
        reason: str,
    ) -> None:

        async with async_session() as session:

            async with session.begin():

                db_file = await session.get(
                    DataLakeFile,
                    file_id,
                    with_for_update=True,
                )

                if db_file is None:
                    raise RuntimeError(f"DataLakeFile " f"id={file_id} disappeared")

                db_file.status = "SKIPPED"

                db_file.processed_at = datetime.now(timezone.utc)

                db_file.loaded_count = 0

                db_file.skipped_count = db_file.record_count or 0

                db_file.failed_count = 0

                db_file.last_error = reason[:5000]

    async def _mark_lake_file_failed(
        self,
        file_id: int,
        *,
        error: str,
    ) -> None:

        async with async_session() as session:

            async with session.begin():

                db_file = await session.get(
                    DataLakeFile,
                    file_id,
                    with_for_update=True,
                )

                if db_file is None:
                    return

                db_file.status = "FAILED"

                db_file.processed_at = datetime.now(timezone.utc)

                db_file.loaded_count = 0
                db_file.skipped_count = 0

                db_file.failed_count = db_file.record_count or 0

                db_file.last_error = error[:5000]

    async def _mark_lake_file_partial(
        self,
        file_id: int,
        *,
        loaded_count: int,
        failed_count: int,
        error_details: list[Any],
    ) -> None:

        async with async_session() as session:

            async with session.begin():

                db_file = await session.get(
                    DataLakeFile,
                    file_id,
                    with_for_update=True,
                )

                if db_file is None:
                    return

                db_file.status = "PARTIAL"

                db_file.processed_at = datetime.now(timezone.utc)

                db_file.loaded_count = loaded_count

                db_file.skipped_count = 0

                db_file.failed_count = failed_count

                db_file.last_error = str(error_details)[:5000]

    # ==================================================================
    # Filename parsing
    # ==================================================================

    def _filetype(
        self,
        filename: Path,
    ) -> tuple[
        str | None,
        str | None,
    ]:
        """
        Sutton filenames are expected to begin:

            REPORTTYPE_FILEID_...

        Examples:

            INVENAVL_736340.xlsx
            oo_736400.xlsx
            SLS003T_736450.xls
        """

        try:
            filename_parts = filename.stem.split("_")

            if len(filename_parts) < 2:

                logger.warning(
                    "Filename %s does not have " "expected type_id format",
                    filename.name,
                )

                return None, None

            report_type = str(filename_parts[0])

            file_id = str(filename_parts[1])

            return (
                report_type,
                file_id,
            )

        except Exception:

            logger.exception(
                "Unable to parse Sutton " "filename %s",
                filename.name,
            )

            return None, None

    # ==================================================================
    # Report -> DB routing
    # ==================================================================

    def process_sutton_report(
        self,
        report_name: str,
        report_tuples: list[
            tuple[
                str,
                Path,
                str | None,
            ]
        ],
    ) -> dict[str, Any]:
        """
        Process a Sutton report and load it to the appropriate table.
        """

        db = SessionLocal()

        try:

            # ----------------------------------------------------------
            # Inventory Snapshot
            # ----------------------------------------------------------

            if report_name == "inventory":

                cls = SuttonInventoryReport

                report_df = self._pandas_read_excel_files(
                    report_tuples,
                    cls,
                    report_name,
                )

                stats = self._commit_to_db(
                    df=report_df,
                    cls=cls,
                    overwrite=True,
                    db=db,
                )

            # ----------------------------------------------------------
            # Open Orders Snapshot
            # ----------------------------------------------------------

            elif report_name == "open":

                cls = SuttonOpenOrderReport

                report_df = self._pandas_read_excel_files(
                    report_tuples,
                    cls,
                    report_name,
                )

                stats = self._commit_to_db(
                    df=report_df,
                    cls=cls,
                    overwrite=True,
                    db=db,
                )

            # ----------------------------------------------------------
            # Sales
            # ----------------------------------------------------------

            elif report_name == "sales":

                cls = SuttonSalesReport

                report_df = self._pandas_read_excel_files(
                    report_tuples,
                    cls,
                    report_name,
                )

                stats = self._commit_to_db(
                    df=report_df,
                    cls=cls,
                    overwrite=False,
                    db=db,
                )

            # ----------------------------------------------------------
            # EDI Load
            # ----------------------------------------------------------

            elif report_name == "edi":

                cls = SuttonEDILoad

                report_df = self._pandas_read_excel_files(
                    report_tuples,
                    cls,
                    report_name,
                )

                stats = self._commit_to_db(
                    df=report_df,
                    cls=cls,
                    overwrite=False,
                    db=db,
                )

            # ----------------------------------------------------------
            # Order Submission
            # ----------------------------------------------------------

            elif report_name == "order":

                cls = SuttonOrderSubmission

                report_df = self._pandas_read_excel_files(
                    report_tuples,
                    cls,
                    report_name,
                )

                stats = self._commit_to_db(
                    df=report_df,
                    cls=cls,
                    overwrite=False,
                    db=db,
                )

            else:

                raise ValueError(f"Unknown Sutton report name: " f"{report_name}")

            logger.info(
                "Successfully processed Sutton " "report type=%s",
                report_name,
            )

            return stats

        except Exception:

            logger.exception(
                "Error processing Sutton " "report type=%s",
                report_name,
            )

            raise

        finally:
            db.close()

    # ==================================================================
    # Excel Reader
    # ==================================================================

    def _pandas_read_excel_files(
        self,
        report_tuples: list[
            tuple[
                str,
                Path,
                str | None,
            ]
        ],
        cls: type,
        report_type: str | None = None,
    ) -> pd.DataFrame:
        """
        Read one or more Sutton Excel reports and return the normalized
        DataFrame expected by the destination model.
        """

        logger.info(
            "Processing %s %s report(s)",
            len(report_tuples),
            report_type,
        )

        df_list: list[pd.DataFrame] = []

        for (
            file_id,
            report_path,
            sheet_name,
        ) in report_tuples:

            file_extension = report_path.suffix.lower()

            if file_extension == ".xls":
                engine = "xlrd"

            elif file_extension == ".xlsx":
                engine = "openpyxl"

            else:
                raise ValueError(
                    f"Unsupported Sutton file type: " f"{report_path.name}"
                )

            try:
                df_or_dict = pd.read_excel(
                    report_path,
                    sheet_name=(sheet_name if sheet_name else 0),
                    engine=engine,
                )

            except Exception as exc:
                raise RuntimeError(
                    f"Unable to read Sutton report " f"{report_path.name}"
                ) from exc

            if isinstance(
                df_or_dict,
                dict,
            ):

                if not df_or_dict:
                    raise ValueError(
                        f"No Excel sheets returned " f"for {report_path.name}"
                    )

                first_key = next(iter(df_or_dict))

                df = df_or_dict[first_key]

            else:
                df = df_or_dict

            if (
                not isinstance(
                    df,
                    pd.DataFrame,
                )
                or df.empty
            ):
                raise ValueError(
                    f"Empty or invalid DataFrame " f"from {report_path.name}"
                )

            df_list.append(df)

            logger.info(
                "Successfully read Sutton report " "%s: rows=%s columns=%s",
                report_path.name,
                len(df),
                len(df.columns),
            )

        if not df_list:
            raise ValueError(
                f"No valid Excel files available " f"for Sutton report {report_type}"
            )

        combined_df = pd.concat(
            df_list,
            ignore_index=True,
        )

        combined_df.columns = combined_df.columns.str.strip()

        cleaned_df = self._clean_dataframe_values(combined_df)

        final_df = cls.dataframe_drop_rename(cleaned_df)

        logger.info(
            "Prepared Sutton %s DataFrame: " "rows=%s columns=%s",
            report_type,
            len(final_df),
            len(final_df.columns),
        )

        return final_df

    # ==================================================================
    # Database Load
    # ==================================================================

    def _commit_to_db(
        self,
        df: pd.DataFrame,
        cls: type,
        db: Session,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """
        Generic Sutton DataFrame -> SQLAlchemy model loader.
        """

        stats: dict[str, Any] = {
            "records_processed": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "records_skipped": 0,
            "errors": 0,
            "error_details": [],
        }

        if df.empty:
            return stats

        try:
            mapper = inspect(cls)

            pk_columns = [col.name for col in mapper.primary_key]

            logger.info(
                "Primary key columns for %s: %s",
                cls.__name__,
                pk_columns,
            )

            # ----------------------------------------------------------
            # Snapshot replacement
            # ----------------------------------------------------------

            if overwrite:

                logger.info(
                    "Replacing existing %s snapshot",
                    cls.__name__,
                )

                db.query(cls).delete(synchronize_session=False)

                db.flush()

            # ----------------------------------------------------------
            # Rows
            # ----------------------------------------------------------

            for (
                row_number,
                (_, row),
            ) in enumerate(
                df.iterrows(),
                start=2,
            ):

                stats["records_processed"] += 1

                try:
                    row_dict: dict[str, Any] = {
                        str(key): (value.strip() if isinstance(value, str) else value)
                        for key, value in row.to_dict().items()
                    }

                    mapped_data = self._check_datatypes_for_db(
                        row_dict,
                        cls,
                    )

                    missing_pk_fields = [
                        pk for pk in pk_columns if not mapped_data.get(pk)
                    ]

                    if missing_pk_fields:

                        error_msg = (
                            f"Row {row_number}: "
                            f"Missing primary key "
                            f"field(s) "
                            f"{missing_pk_fields}"
                        )

                        logger.warning(error_msg)

                        stats["errors"] += 1

                        stats["error_details"].append(error_msg)

                        continue

                    pk_filter = {pk: mapped_data[pk] for pk in pk_columns}

                    existing = db.query(cls).filter_by(**pk_filter).first()

                    # --------------------------------------------------
                    # Existing
                    # --------------------------------------------------

                    if existing:

                        if self._has_changes(
                            existing,
                            mapped_data,
                        ):

                            for (
                                key,
                                value,
                            ) in mapped_data.items():

                                setattr(
                                    existing,
                                    key,
                                    value,
                                )

                            stats["records_updated"] += 1

                        else:
                            stats["records_skipped"] += 1

                    # --------------------------------------------------
                    # New
                    # --------------------------------------------------

                    else:

                        record = cls(**mapped_data)

                        db.add(record)

                        stats["records_inserted"] += 1

                    # --------------------------------------------------
                    # Flush periodically.
                    #
                    # Keep one final commit for this file so exceptions
                    # do not unnecessarily create many transactions.
                    # --------------------------------------------------

                    if stats["records_processed"] % 100 == 0:
                        db.flush()

                        logger.info(
                            "Processed %s %s rows - "
                            "inserted=%s updated=%s "
                            "skipped=%s",
                            stats["records_processed"],
                            cls.__name__,
                            stats["records_inserted"],
                            stats["records_updated"],
                            stats["records_skipped"],
                        )

                except Exception as exc:

                    stats["errors"] += 1

                    error_msg = f"Row {row_number}: " f"{exc}"

                    stats["error_details"].append(error_msg)

                    logger.exception(
                        "Sutton row processing error: %s",
                        error_msg,
                    )

            # ----------------------------------------------------------
            # Final commit
            # ----------------------------------------------------------

            db.commit()

            logger.info(
                "Sutton import complete for %s - "
                "processed=%s inserted=%s updated=%s "
                "skipped=%s errors=%s",
                cls.__name__,
                stats["records_processed"],
                stats["records_inserted"],
                stats["records_updated"],
                stats["records_skipped"],
                stats["errors"],
            )

            return stats

        except Exception:

            db.rollback()

            logger.exception(
                "Fatal error importing Sutton " "model %s",
                cls.__name__,
            )

            raise

    # ==================================================================
    # Change Detection
    # ==================================================================

    def _has_changes(
        self,
        existing_record: Any,
        new_data: dict[str, Any],
    ) -> bool:

        for (
            key,
            new_value,
        ) in new_data.items():

            if key in {
                "created_at",
                "updated_at",
            }:
                continue

            existing_value = getattr(
                existing_record,
                key,
                None,
            )

            if existing_value is None and new_value is None:
                continue

            if existing_value is None or new_value is None:
                return True

            if isinstance(
                existing_value,
                float,
            ) and isinstance(
                new_value,
                float,
            ):

                if abs(existing_value - new_value) > 0.0001:
                    return True

            elif existing_value != new_value:
                return True

        return False

    # ==================================================================
    # DataFrame Cleanup
    # ==================================================================

    def _clean_dataframe_values(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:

        return df.replace(
            {
                "": None,
                pd.NA: None,
                float("nan"): None,
            }
        )

    # ==================================================================
    # Data Type Conversion
    # ==================================================================

    def _check_datatypes_for_db(
        self,
        mapped_data: dict[str, Any],
        cls: type,
    ) -> dict[str, Any]:

        for (
            col,
            value,
        ) in mapped_data.items():

            # Ignore incoming fields that do not exist
            # on the SQLAlchemy model.
            if not hasattr(
                cls,
                col,
            ):
                logger.warning(
                    "Ignoring unknown Sutton field " "%s for model %s",
                    col,
                    cls.__name__,
                )

                continue

            column = getattr(
                cls,
                col,
            )

            try:
                expected_type = column.type.python_type

            except (AttributeError, NotImplementedError):

                logger.warning(
                    "Unable to determine SQLAlchemy " "python type for %s.%s",
                    cls.__name__,
                    col,
                )

                continue

            # ----------------------------------------------------------
            # Null / NaN handling
            # ----------------------------------------------------------

            if pd.isna(value):
                mapped_data[col] = None
                continue

            if isinstance(
                value,
                str,
            ) and value.strip() in {
                "",
                "NaN",
                "nan",
                "00/00/00",
                "00-00-00",
                "0000-00-00",
            }:
                mapped_data[col] = None
                continue

            if value is None:
                continue

            # Already the expected type.
            if isinstance(
                value,
                expected_type,
            ):
                continue

            try:

                if expected_type is str:

                    mapped_data[col] = str(value)

                elif expected_type is int:

                    mapped_data[col] = int(float(value))

                elif expected_type is float:

                    mapped_data[col] = float(value)

                elif expected_type in {
                    datetime,
                    date,
                }:

                    if isinstance(
                        value,
                        str,
                    ):
                        parsed = parser.parse(value)

                    elif isinstance(
                        value,
                        datetime,
                    ):
                        parsed = value

                    elif isinstance(
                        value,
                        date,
                    ):
                        parsed = datetime.combine(
                            value,
                            datetime.min.time(),
                        )

                    else:
                        raise ValueError(f"Unsupported date value " f"{value!r}")

                    if expected_type is date:
                        mapped_data[col] = parsed.date()

                    else:
                        mapped_data[col] = parsed

                else:

                    logger.warning(
                        "Unhandled Sutton conversion " "for %s.%s: %s -> %s",
                        cls.__name__,
                        col,
                        type(value).__name__,
                        expected_type,
                    )

            except Exception as exc:

                raise ValueError(
                    f"Unable to convert "
                    f"{cls.__name__}.{col} "
                    f"value={value!r} "
                    f"to {expected_type.__name__}"
                ) from exc

        return mapped_data


sutton_report_tasks = SuttonReportTasks()
