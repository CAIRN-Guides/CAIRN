# backend/main.py (Rewritten v1.6)

import os
import io
import uuid
import re
import zipfile
import logging
from typing import List, Optional, Any, Dict

import requests
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from supabase import create_client, Client
# Import specific exception for better handling
from postgrest.exceptions import APIError
from b2sdk.v2 import B2Api, InMemoryAccountInfo, Bucket
from b2sdk.v2 import exception as b2_exceptions

# --- Environment Loading ---
load_dotenv()

# --- Configuration ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") # Use service role for backend operations
B2_KEY_ID = os.getenv("B2_APP_KEY_ID")
B2_KEY = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
B2_TEMP_ZIP_PREFIX = os.getenv("B2_TEMP_ZIP_PREFIX", "temp-zips/").rstrip("/") + "/" # Ensure trailing slash
ZIP_URL_TTL_SECONDS = int(os.getenv("ZIP_URL_TTL_SECONDS", "600")) # How long the zip download URL is suggested to be valid
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501")

# Ensure critical variables are set
if not all([SUPABASE_URL, SUPABASE_KEY, B2_KEY_ID, B2_KEY, B2_BUCKET_NAME]):
    raise RuntimeError("FATAL: Missing one or more required environment variables (Supabase/B2 credentials).")

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Initialize External Clients ---
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("✅ Supabase client initialized.")

    b2_info = InMemoryAccountInfo()
    b2_api = B2Api(b2_info)
    b2_api.authorize_account("production", B2_KEY_ID, B2_KEY)
    bucket: Bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)
    B2_DOWNLOAD_URL_BASE = b2_info.get_download_url().rstrip("/")
    logger.info(f"✅ B2 API client initialized for bucket '{B2_BUCKET_NAME}'. Download base: {B2_DOWNLOAD_URL_BASE}")

except Exception as e:
    logger.exception("FATAL: Failed to initialize Supabase or B2 client.")
    raise RuntimeError(f"Client initialization failed: {e}")

# --- Pydantic Schemas (Data Models) ---
class DocumentOut(BaseModel):
    # Define fields expected to be returned by the /documents endpoint
    # Add all relevant fields from your 'files' table that the frontend needs
    id: int
    created_at: Optional[str] = None
    document_id: Optional[str] = None
    document_title: Optional[str] = None
    b2_file_id: Optional[str] = None
    published_date: Optional[str] = None
    document_author: Optional[str] = None
    org_utility_name: Optional[str] = None
    docket_number: Optional[str] = None
    document_type: Optional[str] = None
    # ... add other fields like state_region, keywords, etc.

    class Config:
        orm_mode = True # Compatibility if creating from ORM objects (though Supabase client returns dicts)

class DocumentsResponse(BaseModel):
    data: List[DocumentOut]
    page: int
    page_size: int
    total_count: int

class BatchDownloadRequest(BaseModel):
    document_ids: List[int] = Field(..., description="List of document primary keys (DB IDs) to zip.")

class DownloadResponse(BaseModel):
    url: str = Field(..., description="Relative URL path to the download proxy endpoint.")
    filename: str = Field(..., description="Suggested filename for the download.")
    expires_in_seconds: int = Field(..., description="Suggested duration the URL remains valid (not strictly enforced by proxy).")

# --- FastAPI Application Setup ---
app = FastAPI(
    title="CAIRN Document Finder API",
    version="1.7", # Incremented version for fuzzy search feature
    description="Search document metadata from Supabase and retrieve files via Backblaze B2 proxy.",
)

# --- CORS Configuration ---
origins = [o.strip() for o in ALLOWED_ORIGINS_STR.split(",") if o.strip()]
if not origins:
    logger.warning("No ALLOWED_ORIGINS specified, defaulting to localhost:8501")
    origins = ["http://localhost:8501", "http://127.0.0.1:8501"]

logger.info(f"Allowing CORS origins: {origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# --- Helper Functions ---
def sanitize_filename(name: str, max_length: int = 100) -> str:
    if not name:
        return "unknown_file"
    clean = re.sub(r"[^\w\-.\s]", "_", name)
    clean = re.sub(r"\s+", "_", clean)
    clean = re.sub(r"_+", "_", clean)
    clean = clean.strip("_.")
    if len(clean) > max_length:
        base, dot, ext = clean.rpartition(".")
        if dot and len(ext) < 10:
            max_base_len = max_length - len(ext) - 1
            clean = base[:max_base_len].strip('_') + "." + ext
        else:
            clean = clean[:max_length].strip('_')
    return clean or "downloaded_file"

async def get_current_user(token: Optional[str] = None) -> Optional[Dict]:
    if token:
        logger.debug("Received auth token (validation not implemented).")
    return None

# --- API Endpoints ---

PARAMS_TO_IGNORE_FOR_FILTERING = {"page", "page_size", "include_download_url"}
# Define which column will use FTS. More can be added.
FTS_COLUMNS = {"org_utility_name"} # Using a set for efficient lookup

@app.get("/documents", response_model=DocumentsResponse, tags=["Documents"])
def list_documents(
    request: Request,
    page: int = Query(1, ge=1, description="Page number to retrieve."),
    page_size: int = Query(20, ge=1, le=200, description="Number of documents per page."),
):
    """
    Lists documents from the Supabase 'files' table with dynamic filtering and pagination.
    - 'org_utility_name' uses Full-Text Search (FTS) for fuzzy matching.
    - Other query parameters matching column names use exact match (or array contains for comma-separated values).
    """
    try:
        query = supabase.table("files").select("*", count="exact")
        applied_filters = {}

        for key, value in request.query_params.items():
            original_value = str(value).strip() # Store original stripped value for logging/use
            if key in PARAMS_TO_IGNORE_FOR_FILTERING or not original_value:
                continue

            if key in FTS_COLUMNS:
                if key == "org_utility_name":
                    # Prepare search term for FTS:
                    # 'websearch_to_tsquery' handles terms like "Puget Energy" well by often
                    # converting them to "Puget & Energy". Using spaces between terms
                    # in the query string will often be interpreted as an AND by websearch_to_tsquery.
                    # No complex manual ' & ' insertion is typically needed if ts_type='websearch' is used.
                    fts_search_term = original_value
                    
                    query = query.text_search(
                        key, # The column name, e.g., "org_utility_name"
                        f"'{fts_search_term}'", # The search query needs to be quoted for websearch
                        config="english",       # PostgreSQL text search configuration
                        ts_type="websearch"     # Type of FTS query
                    )
                    applied_filters[key] = f"fts.websearch('{fts_search_term}')"
                    logger.info(f"Applied FTS filter on '{key}' with term: '{fts_search_term}'")
                # Add elif for other FTS columns if needed
            
            elif "," in original_value: # Handle array columns (e.g., keywords)
                vals = [v.strip() for v in original_value.split(",") if v.strip()]
                if vals:
                    query = query.cs(key, vals) # 'cs' for "contains" (array elements)
                    applied_filters[key] = f"cs.{vals}"
            
            else: # Standard equality filter for other columns
                query = query.eq(key, original_value)
                applied_filters[key] = f"eq.{original_value}"

        if applied_filters:
            logger.info(f"Full list of applied filters: {applied_filters}")

        # Apply pagination
        start_index = (page - 1) * page_size
        
        # Optional: Order by FTS rank if a search term was provided for an FTS column
        # This makes the most relevant results appear first.
        # To do this, you'd also need to select the rank: .select("*, ts_rank(...) as rank")
        # For simplicity, we'll keep the default ordering for now.
        # If you want to order by rank, you'd need a more complex query construction
        # as the rank depends on the search term.
        query = query.order("id", desc=False).range(start_index, start_index + page_size - 1)
        
        logger.debug(f"Executing Supabase query for page {page}, size {page_size}")
        result = query.execute()

        docs = result.data if result.data is not None else []
        total_count = result.count if result.count is not None else 0

        logger.info(f"Query successful. Found {len(docs)} documents (total: {total_count}) for page {page}.")
        return DocumentsResponse(
            data=[DocumentOut(**doc) for doc in docs],
            page=page,
            page_size=page_size,
            total_count=total_count
        )

    except APIError as db_error:
        logger.error(f"Database API Error: {db_error.code} - {db_error.message}", exc_info=True)
        detail = f"Database query error: {db_error.message}"
        status_code = 400
        if hasattr(db_error, 'code'): # Check if code attribute exists
            if db_error.code == '42703':
                detail = f"Database query error: Invalid filter field used - {db_error.message}"
            elif db_error.code == '22P02':
                detail = f"Database query error: Invalid value format for a filter field - {db_error.message}"
            # PGRST100: Error related to FTS, often bad query string format
            elif db_error.code == 'PGRST100' and 'syntax error in tsquery' in db_error.message:
                 detail = f"FTS Error: Invalid search query syntax for '{db_error.message.split(':')[1]}'. Try simpler terms."

        raise HTTPException(status_code=status_code, detail=detail)

    except Exception as e:
        logger.exception("Unexpected error fetching documents.")
        raise HTTPException(status_code=500, detail="Internal server error: An unexpected error occurred.")

# ... (rest of your backend code: /download-url, /batch-download-url, /b2-proxy, etc. remains unchanged) ...
# Ensure the DocumentOut model is comprehensive enough for all fields you select and intend to return.

@app.get("/documents/{doc_pk}/download-url", response_model=DownloadResponse, tags=["Download"])
async def get_single_download_url(doc_pk: int):
    if doc_pk <= 0:
        logger.warning(f"Received invalid document PK for download URL: {doc_pk}")
        raise HTTPException(status_code=400, detail="Invalid document Primary Key (ID)")
    logger.info(f"Requesting single download URL for document PK: {doc_pk}")
    try:
        res = (
            supabase.table("files")
            .select("b2_file_id, document_title, document_id, file_format") # Added file_format
            .eq("id", doc_pk)
            .maybe_single()
            .execute()
        )
        if not res.data:
            logger.warning(f"Document PK {doc_pk} not found in database.")
            raise HTTPException(status_code=404, detail="Document not found")

        b2_file_id = res.data.get("b2_file_id")
        if not b2_file_id:
            logger.warning(f"Document PK {doc_pk} found but has no associated B2 file ID.")
            raise HTTPException(status_code=404, detail="No downloadable file associated with this document")

        title = res.data.get("document_title") or res.data.get("document_id") or f"document_{doc_pk}"
        base_filename = sanitize_filename(title)
        
        # Determine filename extension
        file_ext = ""
        db_file_format = res.data.get("file_format") # e.g., "PDF", "DOCX"
        if db_file_format:
            file_ext = "." + db_file_format.lower().replace(" ", "") # .pdf, .docx
        elif "." not in base_filename: # Fallback if no format and no extension in title
            file_ext = ".pdf" # Default to .pdf if unknown

        filename = f"{base_filename}{file_ext}" if not base_filename.endswith(file_ext) and file_ext else base_filename


        proxy_url_path = f"/api/b2-proxy/{b2_file_id}/{filename}"
        logger.info(f"Generated proxy URL path for PK {doc_pk} (B2 ID: {b2_file_id}): {proxy_url_path}")
        return DownloadResponse(
            url=proxy_url_path,
            filename=filename,
            expires_in_seconds=ZIP_URL_TTL_SECONDS
        )
    except APIError as db_error:
        logger.error(f"Database error generating single download URL for PK {doc_pk}: {db_error.message}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error while retrieving file information.")
    except Exception as e:
        logger.exception(f"Unexpected error generating single download URL for PK {doc_pk}.")
        raise HTTPException(status_code=500, detail="Internal server error generating download link.")


@app.post("/documents/batch-download-url", response_model=DownloadResponse, tags=["Download"])
async def get_batch_download_url(request_data: BatchDownloadRequest):
    doc_ids = request_data.document_ids
    if not doc_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided for batch download.")
    valid_ids = [pk for pk in doc_ids if isinstance(pk, int) and pk > 0]
    invalid_ids = [pk for pk in doc_ids if pk not in valid_ids]
    if not valid_ids:
        logger.warning(f"Batch download request contained no valid document IDs. Received: {doc_ids}")
        raise HTTPException(status_code=400, detail="No valid document IDs provided.")
    if invalid_ids:
        logger.warning(f"Ignoring invalid document IDs in batch request: {invalid_ids}")
    logger.info(f"Requesting batch download URL for {len(valid_ids)} document PKs: {valid_ids}")
    try:
        db_res = (
            supabase.table("files")
            .select("id, b2_file_id, document_title, document_id, file_format") # Added file_format
            .in_("id", valid_ids)
            .execute()
        )
        files_to_zip = []
        found_ids = set()
        for record in db_res.data or []:
            if record.get("b2_file_id"):
                files_to_zip.append(record)
                found_ids.add(record["id"])
            else:
                logger.warning(f"Skipping document PK {record['id']} in batch: no B2 file ID found.")
        missing_ids = set(valid_ids) - found_ids
        if missing_ids:
            logger.warning(f"Could not find database records for document PKs: {missing_ids}")
        if not files_to_zip:
            logger.warning("No downloadable files found for the requested batch IDs.")
            raise HTTPException(status_code=404, detail="None of the requested documents could be found or have associated files.")

        zip_buffer = io.BytesIO()
        files_added_count = 0
        download_errors = []
        try:
            b2_auth_token = b2_api.account_info.get_account_auth_token()
        except Exception as auth_err:
            logger.exception("Failed to get B2 auth token for batch download.")
            raise HTTPException(status_code=503, detail="Could not authenticate with file storage service.")
        
        headers = {"Authorization": b2_auth_token}
        session = requests.Session()

        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for record in files_to_zip:
                b2_file_id = record["b2_file_id"]
                pk = record["id"]
                title = record.get("document_title") or record.get("document_id") or f"document_{pk}"
                base_filename = sanitize_filename(title)

                file_ext = ""
                db_file_format = record.get("file_format")
                if db_file_format:
                    file_ext = "." + db_file_format.lower().replace(" ", "")
                elif "." not in base_filename:
                     file_ext = ".pdf" # Default if unknown

                entry_filename = f"{base_filename}{file_ext}" if not base_filename.endswith(file_ext) and file_ext else base_filename
                
                file_download_url = f"{B2_DOWNLOAD_URL_BASE}/b2api/v1/b2_download_file_by_id?fileId={b2_file_id}"
                try:
                    logger.debug(f"Downloading B2 file {b2_file_id} for PK {pk} to add to ZIP...")
                    response = session.get(file_download_url, headers=headers, timeout=60)
                    response.raise_for_status()
                    zip_file.writestr(entry_filename, response.content)
                    files_added_count += 1
                    logger.debug(f"Added '{entry_filename}' (PK {pk}) to ZIP.")
                except requests.exceptions.RequestException as req_err:
                    logger.error(f"Failed to download file for PK {pk} (B2 ID: {b2_file_id}): {req_err}")
                    download_errors.append(pk)
                except Exception as e:
                    logger.exception(f"Unexpected error processing file for PK {pk} (B2 ID: {b2_file_id}) for ZIP.")
                    download_errors.append(pk)
        
        if files_added_count == 0:
            logger.error("Failed to download any files for the batch ZIP.")
            raise HTTPException(status_code=500, detail="Failed to retrieve files to include in the ZIP archive.")
        if download_errors:
            logger.warning(f"Errors occurred downloading files for PKs: {download_errors}")

        zip_buffer.seek(0)
        zip_bytes = zip_buffer.read()
        temp_zip_b2_filename = f"{B2_TEMP_ZIP_PREFIX}{uuid.uuid4()}.zip"
        suggested_zip_download_filename = f"cairn_documents_{files_added_count}_files.zip"
        try:
            logger.info(f"Uploading generated ZIP ({len(zip_bytes)} bytes) to B2 as '{temp_zip_b2_filename}'...")
            uploaded_file_info = bucket.upload_bytes(
                data_bytes=zip_bytes,
                file_name=temp_zip_b2_filename,
                content_type="application/zip"
            )
            zip_b2_file_id = uploaded_file_info.id_
            logger.info(f"Successfully uploaded ZIP. B2 File ID: {zip_b2_file_id}")
        except b2_exceptions.B2Error as b2e:
            logger.exception(f"B2 Error uploading generated ZIP file: {b2e}")
            raise HTTPException(status_code=503, detail="Failed to store generated ZIP file in B2.")
        except Exception as e:
            logger.exception("Unexpected error uploading generated ZIP file to B2.")
            raise HTTPException(status_code=500, detail="Failed to store generated ZIP file.")

        zip_proxy_url_path = f"/api/b2-proxy/{zip_b2_file_id}/{suggested_zip_download_filename}"
        logger.info(f"Generated proxy URL path for batch ZIP: {zip_proxy_url_path}")
        return DownloadResponse(
            url=zip_proxy_url_path,
            filename=suggested_zip_download_filename,
            expires_in_seconds=ZIP_URL_TTL_SECONDS
        )
    except APIError as db_error:
        logger.error(f"Database error during batch download prep: {db_error.message}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error while retrieving file information for batch.")
    except Exception as e:
        logger.exception("Unexpected error generating batch download URL.")
        raise HTTPException(status_code=500, detail="Internal server error generating batch download link.")

@app.get("/api/b2-proxy/{b2_file_id}/{intended_filename}")
async def proxy_b2_download(b2_file_id: str, intended_filename: str):
    if not b2_file_id:
        raise HTTPException(status_code=400, detail="Missing B2 File ID.")
    intended_filename = sanitize_filename(intended_filename or "downloaded_file")
    logger.info(f"Proxy download request received for B2 File ID: {b2_file_id}, Filename: {intended_filename}")
    try:
        download_url = f"{B2_DOWNLOAD_URL_BASE}/b2api/v1/b2_download_file_by_id?fileId={b2_file_id}"
        auth_token = b2_api.account_info.get_account_auth_token()
        headers = {"Authorization": auth_token}
        logger.debug(f"Proxying request to B2 URL: {download_url}")
        session = requests.Session()
        response = session.get(download_url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', 'application/octet-stream')
        content_length = response.headers.get('Content-Length')
        resp_headers = {"Content-Disposition": f'attachment; filename="{intended_filename}"'}
        if content_length:
            resp_headers["Content-Length"] = content_length
        logger.info(f"Streaming file {b2_file_id} as '{intended_filename}' ({content_type}, Size: {content_length or 'Unknown'}).")
        return StreamingResponse(
            response.iter_content(chunk_size=8192),
            media_type=content_type,
            headers=resp_headers
        )
    except requests.exceptions.HTTPError as http_err:
        status_code = http_err.response.status_code
        logger.error(f"B2 download failed for ID {b2_file_id}. Status: {status_code}, Response: {http_err.response.text}")
        detail = f"Failed to retrieve file from storage (Status: {status_code})."
        proxy_status = 502 # Bad Gateway default
        if status_code == 401: detail, proxy_status = "Authentication error with file storage.", 503
        elif status_code == 404: detail, proxy_status = "File not found in storage.", 404
        elif status_code == 416: detail, proxy_status = "Invalid file range requested from storage.", 400
        raise HTTPException(status_code=proxy_status, detail=detail)
    except requests.exceptions.RequestException as req_err:
        logger.exception(f"Network error during B2 download proxy for ID {b2_file_id}: {req_err}")
        raise HTTPException(status_code=504, detail="Network error communicating with file storage.")
    except Exception as e:
        logger.exception(f"Unexpected error during B2 download proxy for ID {b2_file_id}.")
        raise HTTPException(status_code=500, detail="Internal server error during file download.")

# --- Main Execution Guard (for local testing) ---
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server for local development...")
    uvicorn.run(
        "main:app", # Assuming the script is saved as main.py
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
        log_level="debug"
    )