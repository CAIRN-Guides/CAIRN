#!/usr/bin/env python
"""
cairn_sync_script.py - v4.0

Synchronizes metadata from a Google Sheet to Supabase and uploads
corresponding local PDF files to Backblaze B2, ensuring the B2 file ID
is stored in Supabase for retrieval via the API proxy.

Workflow:
1. Read data from Google Sheet.
2. Clean and normalize data.
3. Upsert metadata to Supabase 'files' table.
4. Identify Supabase records needing B2 sync (missing b2_file_id or recently updated).
5. For each record, find the corresponding local file based on 'source_file_id'.
6. If local file found, ensure it's uploaded to B2 (upload if not present).
7. Update the Supabase record with the B2 file ID and sync timestamp.
"""

from __future__ import annotations
import logging
import os
import time
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Dict, Any, Set, Optional, Tuple

import pandas as pd
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from supabase import Client, create_client
# Import specific exceptions for better handling
from postgrest.exceptions import APIError as SupabaseAPIError
from b2sdk.v2 import (
    B2Api,
    InMemoryAccountInfo,
    Bucket,
    UploadSourceLocalFile,
    exception as b2_exceptions,
)

# --- Logging Setup ---
# Configure logging early
logging.basicConfig(
    level=logging.INFO, # Default level, can be overridden by ENV
    format="%(asctime)s - %(levelname)-8s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("CairnSyncScript")


# ───────────────── CONFIGURATION ───────────────── #
def load_config() -> Dict[str, Any]:
    """Loads configuration from environment variables."""
    load_dotenv()
    config = {
        "supabase_url": os.getenv("SUPABASE_URL"),
        "supabase_key": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "sheet_name": os.getenv("GSHEET_NAME", "CAIRN_Labels_Gsheets_Input"),
        "worksheet_name": os.getenv("GSHEET_WORKSHEET", "Document_Tags"),
        "creds_file": Path(os.getenv("GOOGLE_CREDS_FILE", "cairn_google_creds.json")),
        "local_backup_dir": Path(os.getenv("LOCAL_BACKUPS_DIR")), # Require this to be set
        "b2_key_id": os.getenv("B2_APP_KEY_ID"),
        "b2_key": os.getenv("B2_APP_KEY"),
        "b2_bucket_name": os.getenv("B2_BUCKET"),
        "sync_window_days": int(os.getenv("SYNC_WINDOW_DAYS", "30")), # Look for files updated within this window for potential re-sync
        "supabase_page_size": int(os.getenv("SUPABASE_PAGE_SIZE", "100")), # Rows to fetch from Supabase at a time
        "log_level": os.getenv("LOG_LEVEL", "INFO").upper(),
        "b2_object_prefix": os.getenv("B2_OBJECT_PREFIX", "cairn_docs/").rstrip("/") + "/", # Optional prefix for B2 objects
    }

    # Validation
    required_vars = ["supabase_url", "supabase_key", "b2_key_id", "b2_key", "b2_bucket_name", "local_backup_dir"]
    missing_vars = [k for k, v in config.items() if k in required_vars and not v]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    if not config["creds_file"].is_file():
         raise FileNotFoundError(f"Google credentials file not found: {config['creds_file']}")
    if not config["local_backup_dir"].is_dir():
         raise FileNotFoundError(f"Local backup directory not found or not a directory: {config['local_backup_dir']}")

    # Apply log level from config
    try:
        logging.getLogger().setLevel(config["log_level"])
        logger.info(f"Log level set to {config['log_level']}")
    except ValueError:
        logger.warning(f"Invalid LOG_LEVEL '{config['log_level']}'. Using INFO.")
        logging.getLogger().setLevel(logging.INFO)

    logger.info(f"Configuration loaded. Sheet: '{config['sheet_name']}/{config['worksheet_name']}', Backup Dir: '{config['local_backup_dir']}', B2 Bucket: '{config['b2_bucket_name']}'")
    return config

CONFIG = load_config()

# ───────── Column Mapping (Sheet Name -> Supabase Name) ───────── #
# Ensure these match your Google Sheet headers and Supabase column names exactly.
# Use the 'File ID' from the sheet as the key to find local files.
COLUMN_MAPPING: Dict[str, str] = {
    # --- Key Identifiers ---
    "Tag ID": "document_id",        # REQUIRED: Primary business key for upsert
    "File ID": "source_file_id",    # REQUIRED: Used to find the local file for upload

    # --- Core Metadata ---
    "Document Title": "document_title",
    "Published Date": "published_date", # Expects date format parsable by pandas
    "Org/Utility Name": "org_utility_name",
    "Docket Number": "docket_number",
    "Document Type": "document_type",
    "Document Subtype": "document_subtype",
    "State/Region": "state_region",
    "Regulatory Body": "regulatory_body",
    "Jurisdiction Type": "jurisdiction_type",
    "Document Author": "document_author", # Added from schema
    "File Format": "file_format",

    # --- Links ---
    "Document URL": "document_url",
    "CAIRN URL": "cairn_url", # Often populated by sync, but can be source

    # --- Tagging / Classification (Scalar) ---
    "Rate Impact": "rate_impact", # Expects values matching Supabase enum or text
    "Physical Climate Risk": "physical_climate_risk", # Expects boolean compatible (Y/N, True/False)
    "Quality Check": "quality_check", # Expects values matching Supabase enum or text

    # --- Tagging / Classification (Array/List - Comma-separated in Sheet) ---
    "Utility Reform": "utility_reform",
    "Energy Resources": "energy_resources",
    "Customer Classes": "customer_classes",
    "DERs": "ders",
    "Additional Keywords": "additional_keywords",

    # --- Relationships ---
    "Parent Document": "parent_document", # Should be a 'File ID' or 'Tag ID'
    "Replaces Document": "replaces_document", # Should be a 'File ID' or 'Tag ID'
    "Related Documents": "related_documents", # Comma-separated 'File ID's or 'Tag ID's
    "Relationship Types": "relationship_types", # Comma-separated text

    # --- Process / Provenance ---
    "Tagger": "tagger",
    "Date Tagged": "date_tagged", # Expects date format
    "Processing Notes": "processing_notes",
    "Local Backup Name": "local_backup_name", # Original filename if different from File ID
}

# Identify which sheet columns should be treated as arrays
ARRAY_SHEET_COLUMNS = {
    "Utility Reform", "Energy Resources", "Customer Classes", "DERs",
    "Additional Keywords", "Related Documents", "Relationship Types",
}

# Identify which sheet columns should be parsed as dates
DATE_SHEET_COLUMNS = {"Published Date", "Date Tagged"}

# Identify boolean column
BOOL_SHEET_COLUMN = "Physical Climate Risk"

# Required columns in the Sheet for a row to be considered valid for processing
REQUIRED_SHEET_COLUMNS = {"Tag ID", "File ID", "Document Title"}


# ───────── Helper Functions ───────── #

def iso_now_utc() -> str:
    """Returns the current time in UTC ISO format."""
    return datetime.now(timezone.utc).isoformat()

def clean_value(value: Any) -> Optional[str|bool|list|datetime]:
    """Basic cleaning for values from Sheet."""
    if pd.isna(value):
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    # Handle potential numeric types if needed, convert to string or leave as number
    # if isinstance(value, (int, float)):
    #     return value
    return value # Return other types as is for now

def parse_date(value: Any) -> Optional[str]:
    """Parses a value into ISO date string, handling common invalid entries."""
    if value is None: return None
    s_val = str(value).strip()
    # Handle placeholder or invalid strings explicitly
    if s_val.lower() in ('', 'date', 'tbd', 'n/a', 'unknown', 'pending'): return None
    try:
        # `infer_datetime_format` can speed up parsing if format is consistent
        dt = pd.to_datetime(s_val, errors='coerce', infer_datetime_format=True)
        if pd.isna(dt):
            logger.warning(f"Could not parse date: '{value}'")
            return None
        return dt.date().isoformat() # Return only date part
    except Exception as e:
        logger.warning(f"Error parsing date '{value}': {e}")
        return None

def parse_comma_separated_list(value: Any) -> Optional[List[str]]:
    """Splits comma-separated string into a list of stripped strings."""
    if value is None: return None
    s_val = str(value).strip()
    if not s_val: return None
    # Split by comma, strip whitespace from each part, filter out empty strings
    return [part.strip() for part in s_val.split(',') if part.strip()]

def parse_boolean(value: Any) -> Optional[bool]:
    """Parses common string representations into a boolean."""
    if value is None: return None
    s_val = str(value).strip().lower()
    if s_val in ('y', 'yes', 'true', 't', '1', 'on'): return True
    if s_val in ('n', 'no', 'false', 'f', '0', 'off'): return False
    if s_val == '': return None # Treat empty string as None
    logger.warning(f"Unrecognized boolean value: '{value}' - treating as None")
    return None


# ───────── Client Initialization ───────── #

def init_supabase_client(url: str, key: str) -> Client:
    """Initializes and returns the Supabase client."""
    logger.info("Initializing Supabase client...")
    try:
        client: Client = create_client(url, key)
        # Optional: Test connection by making a simple request
        client.table("files").select("id", count="exact").limit(1).execute()
        logger.info("✅ Supabase client initialized and connection tested.")
        return client
    except Exception as e:
        logger.critical(f"❌ Failed to initialize Supabase client: {e}", exc_info=True)
        raise

def init_gspread_client(creds_path: Path) -> gspread.Client:
    """Initializes and returns the Google Sheets client."""
    logger.info("Initializing Google Sheets client...")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly", # Use readonly if only reading
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    try:
        creds = Credentials.from_service_account_file(str(creds_path), scopes=scopes)
        client = gspread.authorize(creds)
        logger.info("✅ Google Sheets client initialized.")
        return client
    except Exception as e:
        logger.critical(f"❌ Failed to initialize Google Sheets client: {e}", exc_info=True)
        raise

def init_b2_bucket(key_id: str, key: str, bucket_name: str) -> Bucket:
    """Initializes B2 API and returns the target Bucket object."""
    logger.info(f"Initializing Backblaze B2 client for bucket '{bucket_name}'...")
    try:
        info = InMemoryAccountInfo()
        api = B2Api(info)
        api.authorize_account("production", key_id, key)
        bucket = api.get_bucket_by_name(bucket_name)
        logger.info("✅ Backblaze B2 client initialized.")
        return bucket
    except Exception as e:
        logger.critical(f"❌ Failed to initialize B2 client or get bucket: {e}", exc_info=True)
        raise


# ───────── Step 1: Sync Google Sheet to Supabase ───────── #

def fetch_sheet_data(gs: gspread.Client, sheet_name: str, worksheet_name: str) -> pd.DataFrame:
    """Fetches data from the specified Google Sheet worksheet."""
    logger.info(f"Fetching data from Google Sheet '{sheet_name}/{worksheet_name}'...")
    try:
        sheet = gs.open(sheet_name).worksheet(worksheet_name)
        data = sheet.get_all_records(head=1, value_render_option='UNFORMATTED_VALUE') # Get raw values
        df = pd.DataFrame(data)
        logger.info(f"Fetched {len(df)} rows from Google Sheet.")
        # Basic validation: Check if required columns exist in the DataFrame
        missing_req_cols = [col for col in REQUIRED_SHEET_COLUMNS if col not in df.columns]
        if missing_req_cols:
             logger.error(f"Missing required columns in Google Sheet: {', '.join(missing_req_cols)}")
             raise ValueError("Sheet is missing required columns.")
        return df
    except gspread.exceptions.SpreadsheetNotFound:
        logger.critical(f"❌ Google Sheet '{sheet_name}' not found.")
        raise
    except gspread.exceptions.WorksheetNotFound:
        logger.critical(f"❌ Worksheet '{worksheet_name}' not found in sheet '{sheet_name}'.")
        raise
    except Exception as e:
        logger.critical(f"❌ Failed to fetch data from Google Sheet: {e}", exc_info=True)
        raise

def prepare_supabase_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Cleans sheet data and transforms it into a list of dictionaries for Supabase."""
    logger.info("Preparing records for Supabase...")
    records = []
    processed_count = 0
    skipped_count = 0

    for index, row in df.iterrows():
        # --- Basic Row Validation ---
        if not all(pd.notna(row.get(req_col)) and str(row.get(req_col)).strip() != "" for req_col in REQUIRED_SHEET_COLUMNS):
            logger.warning(f"Skipping row {index + 2} due to missing required data ({', '.join(REQUIRED_SHEET_COLUMNS)}). Row data: {row.to_dict()}")
            skipped_count += 1
            continue

        record = {}
        try:
            for sheet_col, supabase_col in COLUMN_MAPPING.items():
                if sheet_col not in row:
                    # This shouldn't happen if using get_all_records, but good practice
                    logger.debug(f"Column '{sheet_col}' not found in row {index + 2}, skipping mapping.")
                    continue

                raw_value = row[sheet_col]
                cleaned_value = clean_value(raw_value) # Basic strip/None handling

                # Apply specific parsing based on column type
                if cleaned_value is not None:
                    if sheet_col in DATE_SHEET_COLUMNS:
                        parsed_value = parse_date(cleaned_value)
                    elif sheet_col in ARRAY_SHEET_COLUMNS:
                        parsed_value = parse_comma_separated_list(cleaned_value)
                        # Supabase Python client expects lists for array columns
                    elif sheet_col == BOOL_SHEET_COLUMN:
                        parsed_value = parse_boolean(cleaned_value)
                    else:
                        # Assume text or other compatible types for scalar columns
                        # Ensure it's a string if the Supabase column expects text
                        parsed_value = str(cleaned_value)
                else:
                     parsed_value = None # Keep it None if cleaning resulted in None

                record[supabase_col] = parsed_value

            # Add timestamp for when this sync happened (optional but useful)
            # record["metadata_last_synced_at"] = iso_now_utc() # Add a dedicated column if needed

            records.append(record)
            processed_count += 1

        except Exception as e:
            logger.error(f"Failed to process row {index + 2}: {e}. Row data: {row.to_dict()}", exc_info=True)
            skipped_count += 1

    logger.info(f"Prepared {processed_count} valid records for Supabase. Skipped {skipped_count} rows.")
    return records


def upsert_to_supabase(sb: Client, records: List[Dict[str, Any]]):
    """Upserts records into the Supabase 'files' table."""
    if not records:
        logger.info("No records prepared for Supabase upsert.")
        return

    logger.info(f"Upserting {len(records)} records to Supabase 'files' table...")
    try:
        # Upsert based on 'document_id' which should be unique from the Sheet "Tag ID"
        # Ensure 'document_id' has a UNIQUE constraint in your Supabase table.
        response = sb.table("files").upsert(
            records,
            on_conflict="document_id", # Specify the column(s) for conflict resolution
            # ignore_duplicates=False # Default is False, True would skip duplicates instead of updating
        ).execute()

        # Note: Supabase response structure might vary. Check actual response if needed.
        # successful_upserts = len(response.data) if hasattr(response, 'data') else len(records) # Estimate success
        # logger.info(f"Successfully upserted/updated {successful_upserts} records.")
        # Simplified logging based on lack of errors:
        logger.info(f"✅ Supabase upsert request completed for {len(records)} records.")

    except SupabaseAPIError as e:
         logger.critical(f"❌ Supabase API error during upsert: {e.message} (Code: {e.code}, Details: {e.details})", exc_info=True)
         # Potentially log problematic records if possible from error details
         raise
    except Exception as e:
        logger.critical(f"❌ Unexpected error during Supabase upsert: {e}", exc_info=True)
        raise


# ───────── Step 2: Sync Files from Supabase to B2 ───────── #

def fetch_rows_for_b2_sync(sb: Client, sync_window_days: int, page_size: int) -> Iterable[Dict[str, Any]]:
    """Fetches rows from Supabase that need B2 file sync."""
    logger.info("Fetching Supabase rows requiring B2 sync...")
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=sync_window_days)).isoformat()
    last_id = 0
    total_fetched = 0

    while True:
        try:
            query = (
                sb.table("files")
                .select("id, document_id, source_file_id, updated_at, b2_file_id") # Select needed fields
                .gt("id", last_id) # Paginate by primary key ID
                .filter("source_file_id", "not.is", "null") # MUST have a source_file_id
                .or_(
                    f"b2_file_id.is.null,"      # Sync if b2_file_id is missing
                    f"updated_at.gt.{cutoff_date}" # Or if metadata updated recently (potential re-sync needed)
                )
                .order("id", desc=False)
                .limit(page_size)
            )
            # logger.debug(f"Executing Supabase query: {query.params}") # If debugging needed
            response = query.execute()

            page_data = response.data if response.data is not None else []
            if not page_data:
                logger.info(f"Finished fetching rows. Total potentially needing sync: {total_fetched}")
                break # No more pages

            page_fetched = len(page_data)
            total_fetched += page_fetched
            logger.info(f"Fetched page with {page_fetched} rows (starting after id {last_id})...")
            yield from page_data

            # Get the ID of the last item in the current page for the next query offset
            last_id = page_data[-1]["id"]

        except SupabaseAPIError as e:
            logger.error(f"❌ Supabase API error fetching rows for B2 sync: {e.message}", exc_info=True)
            break # Stop fetching on error
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching rows for B2 sync: {e}", exc_info=True)
            break # Stop fetching on error


def find_local_pdf(backup_dir: Path, source_file_id: str) -> Optional[Path]:
    """Finds the local PDF file based on source_file_id."""
    if not source_file_id:
        logger.warning("Cannot find local file: source_file_id is empty.")
        return None

    # Attempt 1: Exact match (case-insensitive extension)
    base_path = backup_dir / source_file_id
    for ext in (".pdf", ".PDF"):
        pdf_path = base_path.with_suffix(ext)
        if pdf_path.is_file():
            logger.debug(f"Found exact match: {pdf_path}")
            return pdf_path

    # Attempt 2: Glob pattern if exact match fails (e.g., if source_file_id has no extension)
    # This assumes source_file_id is the base name.
    try:
        # Escape special characters in file_id for glob safety
        pattern = re.escape(source_file_id) + "*.pdf"
        hits = list(backup_dir.glob(pattern))
        # Case-insensitive glob might require more complex logic if needed
        # For now, rely on standard glob

        if hits:
            # Prioritize exact .pdf match if multiple hits (e.g., file.pdf vs file.pdf.bak)
            exact_matches = [h for h in hits if h.name.lower() == f"{source_file_id}.pdf".lower()]
            if exact_matches:
                 logger.debug(f"Found glob match (exact pdf): {exact_matches[0]}")
                 return exact_matches[0]
            else:
                 # Return the first hit if no exact .pdf found
                 logger.debug(f"Found glob match (first hit): {hits[0]}")
                 return hits[0]
    except Exception as e:
        logger.error(f"Error during glob search for '{source_file_id}' in {backup_dir}: {e}", exc_info=True)

    logger.warning(f"Local PDF file not found for source_file_id '{source_file_id}' in directory '{backup_dir}'")
    return None


def upload_to_b2_if_missing(bucket: Bucket, b2_object_name: str, local_file_path: Path) -> Optional[str]:
    """
    Checks if the file exists in B2. If not, uploads it.
    Returns the B2 file ID ('fileId') of the existing or newly uploaded file.
    """
    logger.info(f"Checking/Uploading '{local_file_path.name}' to B2 as '{b2_object_name}'...")
    try:
        # Check if file already exists (based on name)
        file_info = bucket.get_file_info_by_name(b2_object_name)
        logger.info(f"File '{b2_object_name}' already exists in B2 (B2 ID: {file_info.id_}). Skipping upload.")
        return file_info.id_ # Return existing B2 File ID

    except b2_exceptions.FileNotPresent:
        logger.info(f"File '{b2_object_name}' not found in B2. Uploading...")
        try:
            # Use recommended upload method with progress reporting (optional)
            # from b2sdk.v2.progress import TqdmProgressListener # Example
            # progress_listener = TqdmProgressListener(f'Uploading {local_file_path.name}')

            uploaded_file = bucket.upload_local_file(
                local_file=str(local_file_path),
                file_name=b2_object_name,
                # content_type='application/pdf', # Optional: let B2 SDK detect or set explicitly
                # file_infos={}, # Optional: Add custom file metadata if needed
                # progress_listener=progress_listener,
            )
            # Short delay potentially helps with eventual consistency, though maybe not needed
            # time.sleep(0.5)
            logger.info(f"✅ Successfully uploaded '{b2_object_name}'. B2 ID: {uploaded_file.id_}")
            return uploaded_file.id_ # Return the new B2 File ID

        except b2_exceptions.B2Error as e:
            logger.error(f"❌ B2 API Error uploading '{b2_object_name}': {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error uploading '{b2_object_name}': {e}", exc_info=True)
            return None

    except b2_exceptions.B2Error as e:
         logger.error(f"❌ B2 API Error checking file '{b2_object_name}': {e}", exc_info=True)
         return None
    except Exception as e:
        logger.error(f"❌ Unexpected error checking file '{b2_object_name}': {e}", exc_info=True)
        return None


def update_supabase_b2_link(sb: Client, supabase_pk_id: int, b2_file_id: str):
    """Updates the Supabase record with the B2 file ID and sync timestamp."""
    logger.debug(f"Updating Supabase row ID {supabase_pk_id} with B2 ID {b2_file_id}...")
    payload = {
        "b2_file_id": b2_file_id,
        "last_synced_at": iso_now_utc() # Update sync timestamp
        # Removed "b2_temp_url": it's not needed by the proxy approach
    }
    try:
        sb.table("files").update(payload).eq("id", supabase_pk_id).execute()
        logger.info(f"✅ Updated Supabase row ID {supabase_pk_id} with B2 file ID.")
    except SupabaseAPIError as e:
        logger.error(f"❌ Supabase API Error updating row ID {supabase_pk_id}: {e.message}", exc_info=True)
        # Consider how to handle this - maybe retry later?
    except Exception as e:
        logger.error(f"❌ Unexpected error updating Supabase row ID {supabase_pk_id}: {e}", exc_info=True)


# ───────── Main Execution Logic ───────── #

def main():
    """Main function to run the sync process."""
    logger.info("========== Starting CAIRN Sync Script ==========")
    start_time = time.monotonic()

    try:
        # --- Initialize Clients ---
        sb_client = init_supabase_client(CONFIG["supabase_url"], CONFIG["supabase_key"])
        gs_client = init_gspread_client(CONFIG["creds_file"])
        b2_bucket = init_b2_bucket(CONFIG["b2_key_id"], CONFIG["b2_key"], CONFIG["b2_bucket_name"])

        # --- Step 1: Sync Google Sheet to Supabase ---
        logger.info("--- Running Step 1: Google Sheet -> Supabase Sync ---")
        sheet_df = fetch_sheet_data(gs_client, CONFIG["sheet_name"], CONFIG["worksheet_name"])
        supabase_records = prepare_supabase_records(sheet_df)
        upsert_to_supabase(sb_client, supabase_records)
        logger.info("--- Step 1 Completed ---")

        # --- Step 2: Sync Supabase Records to B2 ---
        logger.info("--- Running Step 2: Supabase -> B2 File Sync ---")
        sync_count = 0
        skip_local_missing = 0
        skip_no_source_id = 0
        upload_errors = 0
        update_errors = 0 # Count Supabase update errors separately

        rows_to_process = fetch_rows_for_b2_sync(
            sb_client, CONFIG["sync_window_days"], CONFIG["supabase_page_size"]
        )

        for row in rows_to_process:
            supabase_pk = row["id"]
            source_file_id = row.get("source_file_id") # Used to find local file AND as base B2 name
            current_b2_id = row.get("b2_file_id") # Check if already synced

            logger.debug(f"Processing Supabase row ID: {supabase_pk}, Source File ID: {source_file_id}, Current B2 ID: {current_b2_id}")

            if not source_file_id:
                logger.warning(f"Skipping row ID {supabase_pk}: 'source_file_id' is missing.")
                skip_no_source_id += 1
                continue

            # Find the corresponding local file
            local_file_path = find_local_pdf(CONFIG["local_backup_dir"], source_file_id)
            if not local_file_path:
                logger.warning(f"Skipping row ID {supabase_pk}: Local file not found for '{source_file_id}'.")
                skip_local_missing += 1
                continue # Cannot proceed without local file

            # Define the target B2 object name (using prefix + source_id)
            b2_object_name = f"{CONFIG['b2_object_prefix']}{source_file_id}"
            # If source_file_id includes path separators, they might translate to B2 folders.
            # Consider sanitizing source_file_id if it can contain problematic chars.
            # For now, assume source_file_id is a safe base name.

            # Ensure file is on B2 and get its B2 internal file ID
            new_b2_file_id = upload_to_b2_if_missing(b2_bucket, b2_object_name, local_file_path)

            if not new_b2_file_id:
                logger.error(f"Failed to ensure file presence on B2 for row ID {supabase_pk}. Skipping Supabase update.")
                upload_errors += 1
                continue # Don't update Supabase if B2 failed

            # Update Supabase only if the B2 ID is new or wasn't set before
            # (Avoids unnecessary updates if file existed and ID matches)
            if new_b2_file_id != current_b2_id:
                 try:
                     update_supabase_b2_link(sb_client, supabase_pk, new_b2_file_id)
                     sync_count += 1
                 except Exception:
                     # Error logged within update_supabase_b2_link
                     update_errors += 1
            else:
                logger.info(f"Row ID {supabase_pk} already has correct B2 ID ({current_b2_id}). No Supabase update needed.")
                # Consider updating last_synced_at even if ID hasn't changed? Optional.


        logger.info("--- Step 2 Completed ---")
        logger.info(f"B2 Sync Summary: Successful Updates={sync_count}, Upload Errors={upload_errors}, Supabase Update Errors={update_errors}, Skipped (No Source ID)={skip_no_source_id}, Skipped (Local Missing)={skip_local_missing}")

    except Exception as e:
        logger.critical(f" FAILED: {e}", exc_info=True)

    finally:
        end_time = time.monotonic()
        logger.info(f"========== CAIRN Sync Script Finished in {end_time - start_time:.2f} seconds ==========")


if __name__ == "__main__":
    main()