# backend/main.py
import os
import logging
import uuid
import io
import zipfile
import re # For filename sanitization
from typing import List, Optional, Any

import requests # To download files from B2 URLs
from fastapi import FastAPI, HTTPException, Query, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from supabase import create_client, Client
# Ensure correct imports from b2sdk v2
from b2sdk.v2 import B2Api, InMemoryAccountInfo, Bucket, FileInfo
from b2sdk.v2 import exception as b2_exceptions

# ─── Load environment ──────────────────────────────────────────────────────────
load_dotenv() # loads backend/.env

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
B2_KEY_ID = os.getenv("B2_APP_KEY_ID")
B2_KEY = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
# Optional: Define a prefix/folder for temporary ZIP files in B2
B2_TEMP_ZIP_PREFIX = os.getenv("B2_TEMP_ZIP_PREFIX", "temp-zips/")
# Optional: TTL for the final ZIP download URL (in seconds)
ZIP_URL_TTL_SECONDS = int(os.getenv("ZIP_URL_TTL_SECONDS", "600")) # Default: 10 minutes

if not all([SUPABASE_URL, SUPABASE_KEY, B2_KEY_ID, B2_KEY, B2_BUCKET_NAME]):
    raise RuntimeError("Missing one or more required env vars in backend/.env")

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ─── Clients ──────────────────────────────────────────────────────────────────
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    _info = InMemoryAccountInfo()
    _b2 = B2Api(_info)
    # Authorize the B2API instance
    _b2.authorize_account("production", B2_KEY_ID, B2_KEY)
    # Get the bucket object using the authorized B2API instance
    bucket: Bucket = _b2.get_bucket_by_name(B2_BUCKET_NAME)
    logging.info("Successfully initialized Supabase and Backblaze B2 clients.")
except Exception as e:
    logging.exception("FATAL: Failed to initialize Supabase or B2 client.")
    raise RuntimeError(f"Client initialization failed: {e}") from e


# ─── Schemas ──────────────────────────────────────────────────────────────────
class DocumentOut(BaseModel):
    # All your files.* columns MUST INCLUDE 'id' for frontend selection
    id: int # Crucial: Ensure this is selected and returned
    created_at: Optional[str] = None
    document_id: Optional[str] = None
    local_backup_name: Optional[str] = None
    published_date: Optional[str] = None
    date_tagged: Optional[str] = None
    last_synced_at: Optional[str] = None
    b2_file_id: Optional[str] = None # Needed for download
    b2_temp_url: Optional[str] = None # We won't use this directly anymore
    updated_at: Optional[str] = None
    source_file_id: Optional[str] = None
    tags_json: Optional[Any] = None
    additional_keywords: Optional[List[str]] = None
    cairn_url: Optional[str] = None
    ders: Optional[List[str]] = None
    tagger: Optional[str] = None
    file_format: Optional[str] = None
    rate_impact: Optional[str] = None
    document_url: Optional[str] = None
    state_region: Optional[str] = None
    docket_number: Optional[str] = None
    document_type: Optional[str] = None
    quality_check: Optional[str] = None
    document_title: Optional[str] = None
    utility_reform: Optional[List[str]] = None
    parent_document: Optional[str] = None
    regulatory_body: Optional[str] = None
    customer_classes: Optional[List[str]] = None
    document_subtype: Optional[str] = None
    energy_resources: Optional[List[str]] = None
    org_utility_name: Optional[str] = None
    processing_notes: Optional[str] = None
    jurisdiction_type: Optional[str] = None
    related_documents: Optional[List[str]] = None
    replaces_document: Optional[str] = None
    relationship_types: Optional[List[str]] = None
    physical_climate_risk: Optional[bool] = None

class DocumentsResponse(BaseModel):
    data: List[DocumentOut]
    page: int
    page_size: int
    total_count: int

# --- NEW: Schema for Batch Download Request ---
class BatchDownloadRequest(BaseModel):
    # Expecting PK_IDs which are integers in the DB, but might come as strings from frontend JSON
    document_ids: List[Any] = Field(..., description="List of document primary keys (PK_ID) to include in the ZIP.")

# --- NEW: Schema for Batch Download Response ---
class BatchDownloadResponse(BaseModel):
    url: str = Field(..., description="Pre-signed URL to download the generated ZIP file.")
    filename: str = Field(..., description="Suggested filename for the ZIP file.")
    expires_in_seconds: int = Field(..., description="Validity duration of the URL.")

# ─── App & CORS ────────────────────────────────────────────────────────────────

ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",") if origin.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["http://localhost:8501", "http://127.0.0.1:8501"] # Default Streamlit ports

app = FastAPI(
    title="CAIRN Document Finder API",
    version="1.4", # Incremented version
    description="Search & retrieve document metadata. Provides endpoints for generating B2 download URLs (single and batch ZIP)."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"], # Ensure POST is allowed
    allow_headers=["*"],
)

# ─── Helper Functions ─────────────────────────────────────────────────────────

# --- Corrected Helper Function v3 ---
def b2_get_download_url(file_id: str, ttl: int = 3600) -> Optional[str]:
    """Generates a presigned download URL for a B2 file ID using the bucket method."""
    if not file_id:
        logging.warning("b2_get_download_url called with empty file_id")
        return None
    try:
        logging.info(f"Attempting to generate presigned URL for b2_file_id: {file_id} with TTL: {ttl}")
        if not isinstance(_b2, B2Api):
             logging.error("B2 API object (_b2) is not initialized correctly.")
             return None
        if not isinstance(bucket, Bucket):
             logging.error("B2 Bucket object is not initialized correctly.")
             return None

        # --- FIX: Use bucket.get_download_url with duration_seconds ---
        # 1. Get file info (including the filename) from the file ID using the B2Api instance
        file_info: FileInfo = _b2.get_file_info_by_id(file_id)
        file_name = file_info.file_name # Get the actual filename stored in B2

        # 2. Generate the download URL using the bucket object, filename, and duration
        # Ensure the ttl variable (integer seconds) is passed to duration_seconds
        url = bucket.get_download_url(
            file_name=file_name,
            duration_seconds=ttl
        )
        # --- End Fix ---

        logging.info(f"Successfully generated URL for b2_file_id: {file_id} (filename: {file_name})")
        return url

    except b2_exceptions.FileNotPresent as fnfe:
        # Specific error if the file ID doesn't exist in B2
        logging.error(f"[B2 SDK Error] File not present for file_id {file_id}: {fnfe}")
        return None
    except b2_exceptions.NonExistentBucket as neb:
        logging.error(f"[B2 SDK Error] Bucket '{B2_BUCKET_NAME}' not found: {neb}")
        # This indicates a fundamental setup issue
        return None
    except b2_exceptions.B2Error as b2e:
        logging.error(f"[B2 SDK Error] Presign URL error for {file_id} (filename: {file_name if 'file_name' in locals() else 'unknown'}): {b2e}")
        return None
    except Exception as e:
        # Catch potential errors from get_file_info_by_id as well
        logging.exception(f"[Unexpected Error] Presign URL failed for {file_id}: {e}")
        return None


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """Removes invalid characters and truncates filename."""
    if not filename:
        return "unknown_file"
    # Remove potentially problematic characters (allow letters, numbers, underscore, hyphen, period)
    sanitized = re.sub(r'[^\w\-\.]', '_', filename)
    # Replace multiple underscores with a single one
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores/periods
    sanitized = sanitized.strip('_.')
    # Truncate if too long
    if len(sanitized) > max_length:
        # Try to preserve extension
        base, dot, ext = sanitized.rpartition('.')
        if dot and len(ext) < 10: # Simple check for a plausible extension
             max_base_len = max_length - len(ext) - 1
             sanitized = base[:max_base_len] + dot + ext
        else: # No extension or long extension, just truncate
             sanitized = sanitized[:max_length]
    if not sanitized: # If everything was removed
        return "sanitized_file"
    return sanitized

# --- Placeholder for Authentication ---
async def get_current_user(token: Optional[str] = None):
    return None # No auth enforced for now

# ─── API Endpoints ────────────────────────────────────────────────────────────

# --- Existing /documents endpoint (Unchanged) ---
@app.get("/documents", response_model=DocumentsResponse, tags=["Documents"])
def get_documents(
    # ... (all existing filter parameters remain unchanged) ...
    document_id: Optional[str] = Query(None),
    document_title: Optional[str] = Query(None),
    local_backup_name: Optional[str] = Query(None),
    tagger: Optional[str] = Query(None),
    file_format: Optional[str] = Query(None),
    rate_impact: Optional[str] = Query(None),
    quality_check: Optional[str] = Query(None),
    regulatory_body: Optional[str] = Query(None),
    state_region: Optional[str] = Query(None),
    docket_number: Optional[str] = Query(None),
    document_type: Optional[str] = Query(None),
    org_utility_name: Optional[str] = Query(None),
    parent_document: Optional[str] = Query(None),
    replaces_document: Optional[str] = Query(None),
    document_url: Optional[str] = Query(None),
    cairn_url: Optional[str] = Query(None),
    processing_notes: Optional[str] = Query(None),
    published_date: Optional[str] = Query(None),
    date_tagged: Optional[str] = Query(None),
    last_synced_at: Optional[str] = Query(None),
    updated_at: Optional[str] = Query(None),
    additional_keywords: Optional[List[str]] = Query(None),
    ders: Optional[List[str]] = Query(None),
    utility_reform: Optional[List[str]] = Query(None),
    customer_classes: Optional[List[str]] = Query(None),
    energy_resources: Optional[List[str]] = Query(None),
    related_documents: Optional[List[str]] = Query(None),
    relationship_types: Optional[List[str]] = Query(None),
    physical_climate_risk: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: Optional[dict] = Depends(get_current_user)
):
    try:
        # Select all columns needed, ESPECIALLY 'id' and 'b2_file_id'
        query = supabase.table("files").select("*", count='exact')

        # --- Apply filters (same logic as before) ---
        filter_params = {
            "document_id": document_id, "document_title": document_title,
            "local_backup_name": local_backup_name, "tagger": tagger,
            "file_format": file_format, "rate_impact": rate_impact,
            "quality_check": quality_check, "regulatory_body": regulatory_body,
            "state_region": state_region, "docket_number": docket_number,
            "document_type": document_type, "org_utility_name": org_utility_name,
            "parent_document": parent_document, "replaces_document": replaces_document,
            "document_url": document_url, "cairn_url": cairn_url,
            "processing_notes": processing_notes, "published_date": published_date,
            "date_tagged": date_tagged, "last_synced_at": last_synced_at,
            "updated_at": updated_at,
        }
        for fld, val in filter_params.items():
            if val is not None and val != "":
                query = query.eq(fld, val)

        array_filter_params = {
            "additional_keywords": additional_keywords, "ders": ders,
            "utility_reform": utility_reform, "customer_classes": customer_classes,
            "energy_resources": energy_resources, "related_documents": related_documents,
            "relationship_types": relationship_types,
        }
        for fld, vals in array_filter_params.items():
            if vals:
                query = query.cs(fld, vals) # Use 'cs' for contains

        if physical_climate_risk is not None:
            query = query.eq("physical_climate_risk", physical_climate_risk)

        # pagination & ordering
        start_index = (page - 1) * page_size
        query = query.order("id", desc=False).range(start_index, start_index + page_size - 1)

        # Execute query
        result = query.execute()

        docs = result.data or []
        total_count = result.count if result.count is not None else 0

        logging.info(f"Found {len(docs)} documents for page {page} (Total: {total_count}).")

        return {
            "data": docs,
            "page": page,
            "page_size": page_size,
            "total_count": total_count
        }

    except Exception as e:
        logging.exception("Error fetching documents from Supabase")
        raise HTTPException(status_code=500, detail=f"Internal server error fetching documents: {e}")


# --- Single File Download URL Endpoint (Uses corrected helper) ---
@app.get("/documents/{doc_pk_id}/download-url", tags=["Download"], response_model=BatchDownloadResponse)
async def get_single_download_url(
    doc_pk_id: int,
    current_user: Optional[dict] = Depends(get_current_user)
):
    logging.info(f"Request received for download URL for document PK: {doc_pk_id}")
    if doc_pk_id <= 0:
         raise HTTPException(status_code=400, detail="Invalid document ID provided.")
    try:
        # Fetch b2_file_id and a title for filename suggestion
        result = supabase.table("files").select("b2_file_id, document_title, document_id").eq("id", doc_pk_id).maybe_single().execute()
        if not result.data:
            logging.warning(f"Document PK {doc_pk_id} not found in database.")
            raise HTTPException(status_code=404, detail="Document not found")

        doc_data = result.data
        b2_file_id = doc_data.get("b2_file_id")
        doc_title = doc_data.get("document_title")
        doc_id_text = doc_data.get("document_id") # Fallback identifier
        suggested_filename_base = sanitize_filename(doc_title or doc_id_text or f"file_{doc_pk_id}")
        # Attempt to guess extension - THIS IS VERY BASIC, improve if needed
        # A 'file_format' column would be better
        extension = ".pdf" # Default assumption
        if '.' in suggested_filename_base: # Avoid adding .pdf if title has one
             base, dot, ext = suggested_filename_base.rpartition('.')
             if len(ext) <= 4 and len(ext) > 1: # Simple check
                  extension = dot + ext
                  suggested_filename_base = base

        suggested_filename = f"{suggested_filename_base}{extension}"


        if not b2_file_id:
            logging.warning(f"Document PK {doc_pk_id} ('{doc_title}') found, but 'b2_file_id' is missing or null.")
            raise HTTPException(status_code=404, detail="Downloadable file reference not found for this document")

        logging.info(f"Found b2_file_id: {b2_file_id} for PK: {doc_pk_id} ('{doc_title}')")
        # Generate short-lived URL (e.g., 5 minutes = 300 seconds)
        url_ttl = 300
        download_url = b2_get_download_url(b2_file_id, ttl=url_ttl) # Uses corrected helper

        if not download_url:
            logging.error(f"Failed to generate presigned URL for b2_file_id: {b2_file_id}")
            raise HTTPException(status_code=500, detail="Could not generate download URL")

        logging.info(f"Generated download URL for PK: {doc_pk_id} ('{doc_title}')")

        return {
            "url": download_url,
            "filename": suggested_filename, # Provide suggested filename
            "expires_in_seconds": url_ttl
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logging.exception(f"Error getting download URL for PK {doc_pk_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error generating download link.")


# --- Batch Download URL Endpoint (Uses corrected helper) ---
@app.post("/documents/batch-download-url", tags=["Download"], response_model=BatchDownloadResponse)
async def get_batch_download_url(
    request_data: BatchDownloadRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """
    Generates a pre-signed URL for a temporary ZIP file containing multiple documents.
    Accepts a list of document primary keys (PK_ID).
    """
    raw_doc_ids = request_data.document_ids
    if not raw_doc_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided.")

    # Validate and convert IDs to integers
    doc_pk_ids = []
    invalid_ids = []
    for raw_id in raw_doc_ids:
        try:
            pk_id = int(raw_id)
            if pk_id > 0:
                doc_pk_ids.append(pk_id)
            else:
                invalid_ids.append(str(raw_id))
        except (ValueError, TypeError):
            invalid_ids.append(str(raw_id))

    if invalid_ids:
        logging.warning(f"Invalid document IDs received in batch request: {invalid_ids}")
    if not doc_pk_ids:
         raise HTTPException(status_code=400, detail="No valid document IDs provided after validation.")

    logging.info(f"Request received for batch download URL for {len(doc_pk_ids)} document PKs: {doc_pk_ids}")

    # 1. Fetch B2 File IDs and Titles from Supabase
    files_to_zip = []
    try:
        result = supabase.table("files").select("id, b2_file_id, document_title, document_id")\
                       .in_("id", doc_pk_ids).execute()

        if result.data:
            found_ids = {item['id'] for item in result.data}
            for item in result.data:
                if item.get("b2_file_id"):
                    files_to_zip.append({
                        "pk_id": item['id'],
                        "b2_id": item['b2_file_id'],
                        "title": item.get('document_title'),
                        "doc_id": item.get('document_id') # Fallback identifier
                    })
                else:
                    logging.warning(f"Document PK {item['id']} found but missing b2_file_id, skipping.")
            missing_ids = set(doc_pk_ids) - found_ids
            if missing_ids:
                 logging.warning(f"Could not find database entries for requested PKs: {list(missing_ids)}")

    except Exception as e:
        logging.exception(f"Database error fetching batch details for PKs {doc_pk_ids}: {e}")
        raise HTTPException(status_code=500, detail="Error fetching document details for batch download.")

    if not files_to_zip:
        raise HTTPException(status_code=404, detail="No valid files found for the requested IDs to include in the ZIP.")

    # 2. Create ZIP in memory
    zip_buffer = io.BytesIO()
    files_added_count = 0
    errors_downloading = []

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file_info in files_to_zip:
            pk_id = file_info['pk_id']
            b2_id = file_info['b2_id']
            title = file_info['title']
            doc_id_text = file_info['doc_id']

            # Generate short-lived URL for individual file using corrected helper
            individual_url = b2_get_download_url(b2_id, ttl=120) # Short TTL just for download
            if not individual_url:
                logging.error(f"Failed to get download URL for b2_id {b2_id} (PK: {pk_id}), skipping.")
                errors_downloading.append(pk_id)
                continue

            # Download the file content
            try:
                response = requests.get(individual_url, stream=False, timeout=30) # Changed stream=False to get content directly
                response.raise_for_status()

                # Sanitize filename for ZIP entry
                base_name = sanitize_filename(title or doc_id_text or f"file_{pk_id}")
                extension = ".pdf" # Default assumption
                if '.' in base_name:
                     base, dot, ext = base_name.rpartition('.')
                     if len(ext) <= 4 and len(ext) > 1:
                          extension = dot + ext
                          base_name = base
                zip_entry_name = f"{base_name}{extension}"

                # Write content to ZIP
                zip_file.writestr(zip_entry_name, response.content) # Use response.content
                files_added_count += 1
                logging.info(f"Added PK {pk_id} ('{zip_entry_name}') to ZIP.")

            except requests.exceptions.RequestException as req_err:
                logging.error(f"Failed to download content for b2_id {b2_id} (PK: {pk_id}): {req_err}")
                errors_downloading.append(pk_id)
            except Exception as e:
                 logging.exception(f"Unexpected error processing file for b2_id {b2_id} (PK: {pk_id}): {e}")
                 errors_downloading.append(pk_id)

    if files_added_count == 0:
         logging.error(f"Failed to download or add any files to the ZIP for request: {doc_pk_ids}")
         raise HTTPException(status_code=500, detail="Could not process any files for the ZIP archive.")

    # 3. Upload ZIP to B2
    zip_buffer.seek(0) # Rewind buffer to the beginning
    zip_content = zip_buffer.getvalue()
    zip_filename_b2 = f"{B2_TEMP_ZIP_PREFIX}{uuid.uuid4()}.zip"
    suggested_download_filename = f"cairn_download_{files_added_count}_files.zip"
    uploaded_b2_file_id = None # Initialize

    try:
        logging.info(f"Uploading generated ZIP file to B2 as: {zip_filename_b2}")
        # Use upload_bytes which returns FileVersionInfo
        file_version_info = bucket.upload_bytes(
            data_bytes=zip_content,
            file_name=zip_filename_b2,
            content_type='application/zip'
        )
        uploaded_b2_file_id = file_version_info.id_ # Get the ID from the returned info
        if not uploaded_b2_file_id:
             raise Exception("B2 upload did not return a file ID.")
        logging.info(f"Successfully uploaded ZIP. B2 File ID: {uploaded_b2_file_id}")

    except b2_exceptions.B2Error as b2e:
         logging.exception(f"Failed to upload ZIP file '{zip_filename_b2}' to B2: {b2e}")
         raise HTTPException(status_code=500, detail="Failed to store generated ZIP file.")
    except Exception as e:
         logging.exception(f"Unexpected error uploading ZIP file '{zip_filename_b2}': {e}")
         raise HTTPException(status_code=500, detail="Internal error storing generated ZIP file.")

    # 4. Generate Pre-signed URL for the ZIP using the corrected helper
    zip_download_url = b2_get_download_url(uploaded_b2_file_id, ttl=ZIP_URL_TTL_SECONDS)

    if not zip_download_url:
        logging.error(f"Failed to generate presigned URL for uploaded ZIP: {zip_filename_b2} (ID: {uploaded_b2_file_id})")
        # Consider deleting the orphaned ZIP file from B2 here if possible
        raise HTTPException(status_code=500, detail="Could not generate final download URL for the ZIP file.")

    logging.info(f"Generated final download URL for ZIP: {zip_filename_b2}")
    if errors_downloading:
         logging.warning(f"Batch download complete, but errors occurred for PKs: {errors_downloading}")

    # 5. Return URL to Frontend
    return {
        "url": zip_download_url,
        "filename": suggested_download_filename,
        "expires_in_seconds": ZIP_URL_TTL_SECONDS
    }


# Example of running locally (if needed for testing)
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)
