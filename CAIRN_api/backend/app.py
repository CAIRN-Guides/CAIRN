# backend Start re-write 5.5.25 1.1

import os
import io
import uuid
import re
import zipfile
import logging  # Import logging first
import sys      # For sys.version logging

# --- Logging Setup ---
# This must be done before any 'logger.info' or other logging calls.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - [%(module)s:%(lineno)d] - %(message)s", # Added module/lineno
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Create the logger instance that will be used throughout the module
logger = logging.getLogger(__name__)

# --- Now, other imports can follow ---
from typing import List, Optional, Any, Dict

import requests
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Supabase specific imports
from supabase import create_client, Client as SupabaseClient # Use an alias if 'Client' is too generic
from postgrest.exceptions import APIError as PostgrestAPIError # Alias to be specific

# B2 specific imports
from b2sdk.v2 import B2Api, InMemoryAccountInfo, Bucket as B2Bucket # Use an alias
from b2sdk.v2 import exception as b2_exceptions

# Import supabase and postgrest again if needed specifically for version checking,
# though accessing __version__ directly from the top-level import is usually fine.
import supabase
import postgrest # For version checking

# --- Version Logging ---
# This section now correctly uses the 'logger' instance defined above.
logger.info(f"Python version: {sys.version.splitlines()[0]}")
logger.info(f"Supabase-py version: {supabase.__version__}")
try:
    import importlib.metadata
    logger.info(f"PostgREST-py (postgrest client) version (via importlib.metadata): {importlib.metadata.version('postgrest')}")
except ImportError:
    logger.warning("importlib.metadata not available (likely Python < 3.8). Trying direct __version__ for postgrest.")
    try:
        # The 'postgrest' module (client library) might not always expose __version__ directly.
        # This is a fallback and might not work for all package structures.
        logger.info(f"PostgREST-py (postgrest client) version (via __version__): {postgrest.__version__}")
    except AttributeError:
        logger.error("The 'postgrest' client module does not have a __version__ attribute. Version info may be incomplete.")
    except Exception as e_pv:
        logger.error(f"Could not determine postgrest client version using __version__: {e_pv}")
except Exception as e_im: # Catches other errors from importlib.metadata.version like PackageNotFoundError
    logger.error(f"Could not determine postgrest client version using importlib.metadata: {e_im}")


# --- Environment Loading ---
load_dotenv()
logger.info("Environment variables loaded via load_dotenv().")

# --- Configuration ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
B2_KEY_ID = os.getenv("B2_APP_KEY_ID")
B2_KEY = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
B2_TEMP_ZIP_PREFIX = os.getenv("B2_TEMP_ZIP_PREFIX", "temp-zips/").rstrip("/") + "/"
ZIP_URL_TTL_SECONDS = int(os.getenv("ZIP_URL_TTL_SECONDS", "600"))
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501")

# Ensure critical variables are set
critical_env_vars = {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
    "B2_KEY_ID": B2_KEY_ID,
    "B2_KEY": B2_KEY,
    "B2_BUCKET_NAME": B2_BUCKET_NAME,
}
missing_vars = [name for name, value in critical_env_vars.items() if not value]
if missing_vars:
    error_msg = f"FATAL: Missing required environment variables: {', '.join(missing_vars)}."
    logger.error(error_msg)
    raise RuntimeError(error_msg)
logger.info("Critical environment variables verified.")

# --- Initialize External Clients ---
try:
    # 'supabase_client' is the instance of the Supabase client.
    # The 'supabase' import is the module itself.
    supabase_client: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("✅ Supabase client initialized.")

    b2_info = InMemoryAccountInfo()
    b2_api = B2Api(b2_info)
    b2_api.authorize_account("production", B2_KEY_ID, B2_KEY)
    b2_bucket: B2Bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME) # Use aliased type
    B2_DOWNLOAD_URL_BASE = b2_info.get_download_url().rstrip("/")
    logger.info(f"✅ B2 API client initialized for bucket '{B2_BUCKET_NAME}'. Download base: {B2_DOWNLOAD_URL_BASE}")

except Exception as e:
    logger.exception("FATAL: Failed to initialize Supabase or B2 client.")
    raise RuntimeError(f"Client initialization failed: {e}")

# --- Pydantic Schemas (Data Models) ---
class DocumentOut(BaseModel):
    id: int
    created_at: Optional[str] = None
    document_id: Optional[str] = None
    document_title: Optional[str] = None
    b2_file_id: Optional[str] = None
    published_date: Optional[str] = None
    org_utility_name: Optional[str] = None
    docket_number: Optional[str] = None
    document_type: Optional[str] = None
    document_author: Optional[str] = None # Added field
    description: Optional[str] = None    # Added field
    # TODO: Add ALL other fields from your 'files' table that you want to expose.
    # Example:
    # state_region: Optional[str] = None
    # keywords: Optional[List[str]] = None # If it's an array type in DB and JSON

    class Config:
        from_attributes = True # Pydantic v2+ style

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
    expires_in_seconds: int = Field(..., description="Suggested duration the URL remains valid.")

# --- FastAPI Application Setup ---
app = FastAPI(
    title="CAIRN Document Finder API",
    version="1.7", # Incremented version for logging fix
    description="Search document metadata from Supabase and retrieve files via Backblaze B2 proxy.",
)
logger.info(f"FastAPI application '{app.title}' version {app.version} initialized.")

# --- CORS Configuration ---
origins = [o.strip() for o in ALLOWED_ORIGINS_STR.split(",") if o.strip()]
if not origins:
    logger.warning("No ALLOWED_ORIGINS specified, defaulting to localhost:8501 and 127.0.0.1:8501")
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
    if not name: return "unknown_file"
    clean = re.sub(r"[^\w\-.\s]", "_", name)
    clean = re.sub(r"\s+", "_", clean)
    clean = re.sub(r"_+", "_", clean)
    clean = clean.strip("_.")
    if len(clean) > max_length:
        base, dot, ext = clean.rpartition(".")
        if dot and len(ext) < 10: # Plausible extension
            max_base_len = max_length - len(ext) - 1
            clean = base[:max_base_len].strip('_') + "." + ext
        else: # No/long extension
            clean = clean[:max_length].strip('_')
    return clean or "downloaded_file"

async def get_current_user(token: Optional[str] = None) -> Optional[Dict]:
    if token: logger.debug("Received auth token (validation not implemented).")
    return None

# --- API Endpoints ---
PARAMS_TO_IGNORE_FOR_FILTERING = {"page", "page_size", "include_download_url"}

@app.get("/documents", response_model=DocumentsResponse, tags=["Documents"])
def list_documents(
    request: Request,
    page: int = Query(1, ge=1, description="Page number to retrieve."),
    page_size: int = Query(20, ge=1, le=200, description="Number of documents per page."),
):
    logger.debug(f"list_documents called with page={page}, page_size={page_size}, params={request.query_params}")
    try:
        query = supabase_client.table("files").select("*", count="exact")

        applied_filters = {}
        for key, value in request.query_params.items():
            if key in PARAMS_TO_IGNORE_FOR_FILTERING or not value:
                continue
            
            # TODO: Add specific handling for known array columns if needed
            # For now, 'cs' is used if a comma is present.
            if "," in value:
                vals = [v.strip() for v in value.split(",") if v.strip()]
                if vals:
                    query = query.cs(key, vals)
                    applied_filters[key] = f"cs.{vals}"
                else:
                    logger.warning(f"Ignoring filter '{key}': comma-separated value resulted in empty list.")
            else:
                query = query.eq(key, value)
                applied_filters[key] = f"eq.{value}"

        if applied_filters: logger.info(f"Applying filters: {applied_filters}")

        start_index = (page - 1) * page_size
        query = query.order("id", desc=False).range(start_index, start_index + page_size - 1)

        logger.info(f"Executing Supabase query for page {page}, size {page_size}")
        result = query.execute()

        docs_data = result.data if result.data is not None else []
        total_count = result.count if result.count is not None else 0
        logger.info(f"Query successful. Found {len(docs_data)} documents (total: {total_count}).")

        validated_docs = []
        for i, doc_dict in enumerate(docs_data):
            try:
                validated_docs.append(DocumentOut(**doc_dict))
            except Exception as p_exc: # More specific PydanticValidationError if preferred
                logger.warning(f"Pydantic validation failed for document at index {i} (ID: {doc_dict.get('id', 'N/A')}): {p_exc}. Skipping this document.")
        
        return DocumentsResponse(
            data=validated_docs,
            page=page,
            page_size=page_size,
            total_count=total_count
        )

    except PostgrestAPIError as db_error: # Using the aliased exception
        err_code = getattr(db_error, 'code', 'N/A')
        logger.error(f"Database API Error: Code '{err_code}' - {db_error.message}", exc_info=True)
        detail = f"Database query error: {db_error.message}"
        status_code = 400
        if err_code == '42703': detail = f"Database query error: Invalid filter field used. ({db_error.message})"
        elif err_code == '22P02': detail = f"Database query error: Invalid value format for a filter. ({db_error.message})"
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        logger.exception("Unexpected error fetching documents.")
        raise HTTPException(status_code=500, detail="Internal server error: An unexpected error occurred while fetching documents.")

@app.get("/documents/{doc_pk}/download-url", response_model=DownloadResponse, tags=["Download"])
async def get_single_download_url(doc_pk: int):
    if doc_pk <= 0:
        logger.warning(f"Received invalid document PK for download URL: {doc_pk}")
        raise HTTPException(status_code=400, detail="Invalid document Primary Key (ID).")

    logger.info(f"Requesting single download URL for document PK: {doc_pk}")
    try:
        res = (
            supabase_client.table("files")
            .select("b2_file_id, document_title, document_id")
            .eq("id", doc_pk)
            .maybe_single()
            .execute()
        )

        if not res.data:
            logger.warning(f"Document PK {doc_pk} not found in database.")
            raise HTTPException(status_code=404, detail="Document not found.")

        b2_file_id = res.data.get("b2_file_id")
        if not b2_file_id:
            logger.warning(f"Document PK {doc_pk} (Title: {res.data.get('document_title', 'N/A')}) found but has no associated B2 file ID.")
            raise HTTPException(status_code=404, detail="No downloadable file associated with this document.")

        title = res.data.get("document_title") or res.data.get("document_id") or f"document_{doc_pk}"
        base_filename = sanitize_filename(title)
        filename_to_serve = f"{base_filename}.pdf" if "." not in base_filename else base_filename
        
        # Relative path for the frontend to construct full URL
        proxy_url_path = f"/api/b2-proxy/{b2_file_id}/{filename_to_serve}"
        logger.info(f"Generated proxy URL path for PK {doc_pk} (B2 ID: {b2_file_id}): {proxy_url_path}")

        return DownloadResponse(url=proxy_url_path, filename=filename_to_serve, expires_in_seconds=ZIP_URL_TTL_SECONDS)

    except PostgrestAPIError as db_error:
        logger.error(f"Database error for single download URL (PK {doc_pk}): {db_error.message}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error retrieving file information.")
    except Exception as e:
        logger.exception(f"Unexpected error for single download URL (PK {doc_pk}).")
        raise HTTPException(status_code=500, detail="Internal server error generating download link.")

@app.post("/documents/batch-download-url", response_model=DownloadResponse, tags=["Download"])
async def get_batch_download_url(request_data: BatchDownloadRequest):
    doc_ids = request_data.document_ids
    if not doc_ids: raise HTTPException(status_code=400, detail="No document IDs provided.")

    valid_ids = [pk for pk in doc_ids if isinstance(pk, int) and pk > 0]
    if not valid_ids:
        logger.warning(f"Batch download: no valid IDs. Received: {doc_ids}")
        raise HTTPException(status_code=400, detail="No valid document IDs provided.")
    
    ignored_ids = set(doc_ids) - set(valid_ids)
    if ignored_ids: logger.warning(f"Batch download: ignoring invalid IDs: {ignored_ids}")

    logger.info(f"Requesting batch download URL for {len(valid_ids)} document PKs: {valid_ids}")
    try:
        db_res = (
            supabase_client.table("files")
            .select("id, b2_file_id, document_title, document_id")
            .in_("id", valid_ids)
            .execute()
        )

        files_to_zip = [r for r in (db_res.data or []) if r.get("b2_file_id")]
        found_db_ids = {r["id"] for r in (db_res.data or [])}
        not_found_or_no_b2 = set(valid_ids) - {r["id"] for r in files_to_zip}

        if not_found_or_no_b2:
            logger.warning(f"Batch download: PKs not found, or no B2 ID for: {not_found_or_no_b2}")
        if not files_to_zip:
            logger.warning("Batch download: No downloadable files found for the requested IDs.")
            raise HTTPException(status_code=404, detail="None of the requested documents are available for download.")

        zip_buffer = io.BytesIO()
        files_added_count = 0
        download_errors_pks = []

        b2_auth_token = b2_api.account_info.get_account_auth_token()
        headers = {"Authorization": b2_auth_token}

        with requests.Session() as session, \
             zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for record in files_to_zip:
                b2_file_id, pk = record["b2_file_id"], record["id"]
                title = record.get("document_title") or record.get("document_id") or f"document_{pk}"
                entry_filename = sanitize_filename(title)
                entry_filename = f"{entry_filename}.pdf" if "." not in entry_filename else entry_filename
                file_url = f"{B2_DOWNLOAD_URL_BASE}/b2api/v1/b2_download_file_by_id?fileId={b2_file_id}"
                try:
                    logger.debug(f"Batch: Downloading B2 file {b2_file_id} (PK {pk}) for ZIP...")
                    response = session.get(file_url, headers=headers, timeout=60)
                    response.raise_for_status()
                    zip_file.writestr(entry_filename, response.content)
                    files_added_count += 1
                except requests.exceptions.RequestException as req_err:
                    logger.error(f"Batch: Failed to download file PK {pk} (B2 ID: {b2_file_id}): {req_err}")
                    download_errors_pks.append(pk)
                except Exception as e_zip:
                    logger.exception(f"Batch: Unexpected error with file PK {pk} (B2 ID: {b2_file_id}) for ZIP.")
                    download_errors_pks.append(pk)
        
        if files_added_count == 0:
            logger.error("Batch: Failed to download any files for the ZIP.")
            raise HTTPException(status_code=500, detail="Failed to retrieve any files for the ZIP archive.")
        if download_errors_pks:
            logger.warning(f"Batch: Errors occurred downloading files for PKs: {download_errors_pks}")

        zip_buffer.seek(0)
        temp_zip_b2_filename = f"{B2_TEMP_ZIP_PREFIX}{uuid.uuid4()}.zip"
        final_zip_filename = f"cairn_documents_{files_added_count}_files.zip"
        
        logger.info(f"Uploading generated ZIP ({zip_buffer.getbuffer().nbytes} bytes) to B2 as '{temp_zip_b2_filename}'...")
        uploaded_file_info = b2_bucket.upload_bytes(zip_buffer.getvalue(), temp_zip_b2_filename, content_type="application/zip")
        zip_b2_file_id = uploaded_file_info.id_
        logger.info(f"Batch: Successfully uploaded ZIP. B2 File ID: {zip_b2_file_id}")
        
        # Relative path for the frontend
        zip_proxy_url_path = f"/api/b2-proxy/{zip_b2_file_id}/{final_zip_filename}"
        return DownloadResponse(url=zip_proxy_url_path, filename=final_zip_filename, expires_in_seconds=ZIP_URL_TTL_SECONDS)

    except b2_exceptions.B2Error as b2e:
        logger.exception(f"Batch: B2 Error during ZIP upload: {b2e}")
        raise HTTPException(status_code=503, detail="Failed to store generated ZIP file.")
    except PostgrestAPIError as db_error:
        logger.error(f"Batch: Database error: {db_error.message}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error preparing batch download.")
    except Exception as e:
        logger.exception("Batch: Unexpected error generating batch download URL.")
        raise HTTPException(status_code=500, detail="Internal server error generating batch download link.")

@app.get("/api/b2-proxy/{b2_file_id}/{intended_filename}")
async def proxy_b2_download(b2_file_id: str, intended_filename: str):
    if not b2_file_id: raise HTTPException(status_code=400, detail="Missing B2 File ID.")
    intended_filename = sanitize_filename(intended_filename or "downloaded_file")
    logger.info(f"Proxy: Request for B2 File ID: {b2_file_id}, Filename: {intended_filename}")

    try:
        download_url = f"{B2_DOWNLOAD_URL_BASE}/b2api/v1/b2_download_file_by_id?fileId={b2_file_id}"
        auth_token = b2_api.account_info.get_account_auth_token()
        b2_headers = {"Authorization": auth_token}
        logger.debug(f"Proxy: Requesting from B2 URL: {download_url}")

        with requests.Session() as session:
            response = session.get(download_url, headers=b2_headers, stream=True, timeout=60)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', 'application/octet-stream')
            content_length = response.headers.get('Content-Length')
            client_resp_headers = {"Content-Disposition": f'attachment; filename="{intended_filename}"'}
            if content_length: client_resp_headers["Content-Length"] = content_length
            logger.info(f"Proxy: Streaming B2 file {b2_file_id} as '{intended_filename}' ({content_type}, Size: {content_length or 'Unknown'}).")
            return StreamingResponse(response.iter_content(chunk_size=8192), media_type=content_type, headers=client_resp_headers)

    except requests.exceptions.HTTPError as http_err:
        status = getattr(http_err.response, 'status_code', 500)
        resp_text = getattr(http_err.response, 'text', 'No response text')
        logger.error(f"Proxy: B2 download HTTPError. ID {b2_file_id}. Status: {status}, Response: {resp_text[:200]}...")
        detail, proxy_status = f"Failed to retrieve file from storage (Status: {status}).", 502 # Bad Gateway
        if status == 401: detail, proxy_status = "Authentication error with file storage.", 503
        elif status == 404: detail, proxy_status = "File not found in remote storage.", 404
        raise HTTPException(status_code=proxy_status, detail=detail)
    except requests.exceptions.RequestException as req_err:
        logger.exception(f"Proxy: Network error for B2 ID {b2_file_id}: {req_err}")
        raise HTTPException(status_code=504, detail="Network error communicating with file storage.")
    except Exception as e:
        logger.exception(f"Proxy: Unexpected error for B2 ID {b2_file_id}.")
        raise HTTPException(status_code=500, detail="Internal server error during file download.")

# --- Main Execution Guard (for local testing) ---
if __name__ == "__main__":
    import uvicorn
    # The logger instance is already configured at the module level
    logger.info("Starting Uvicorn server for local development (app.py)...")
    uvicorn.run(
        "__main__:app", # Runs the 'app' object from the current file when executed as a script
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
        log_level="debug" # Uvicorn's own log level, separate from app logging for its messages
    )
