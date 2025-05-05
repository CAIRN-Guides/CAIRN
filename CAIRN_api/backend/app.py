# backend/main.py
import os
import logging
import uuid # Keep for potential future use (e.g., job IDs)
from typing import List, Optional, Any

from fastapi import FastAPI, HTTPException, Query, Depends # Added Depends for potential auth later
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse # Can be useful, though dict return often sufficient
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client
from b2sdk.v2 import B2Api, InMemoryAccountInfo, Bucket, exception as b2_exceptions

# ─── Load environment ──────────────────────────────────────────────────────────
load_dotenv() # loads backend/.env

SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
B2_KEY_ID       = os.getenv("B2_APP_KEY_ID")
B2_KEY          = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME  = os.getenv("B2_BUCKET_NAME")

if not all([SUPABASE_URL, SUPABASE_KEY, B2_KEY_ID, B2_KEY, B2_BUCKET_NAME]):
    raise RuntimeError("Missing one or more required env vars in backend/.env")

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ─── Clients ──────────────────────────────────────────────────────────────────
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    _info = InMemoryAccountInfo()
    _b2   = B2Api(_info)
    _b2.authorize_account("production", B2_KEY_ID, B2_KEY)
    bucket: Bucket = _b2.get_bucket_by_name(B2_BUCKET_NAME)
    logging.info("Successfully initialized Supabase and Backblaze B2 clients.")
except Exception as e:
    logging.exception("FATAL: Failed to initialize Supabase or B2 client.")
    raise RuntimeError(f"Client initialization failed: {e}") from e


# ─── Schemas ──────────────────────────────────────────────────────────────────
# Keep your existing DocumentOut and DocumentsResponse schemas
class DocumentOut(BaseModel):
    # All your files.* columns MUST INCLUDE 'id' for frontend selection
    id: int # Crucial: Ensure this is selected and returned
    created_at:       Optional[str] = None
    document_id:      Optional[str] = None
    local_backup_name:Optional[str] = None
    published_date:   Optional[str] = None
    date_tagged:      Optional[str] = None
    last_synced_at:   Optional[str] = None
    b2_file_id:       Optional[str] = None # Needed for download
    b2_temp_url:      Optional[str] = None # We won't use this directly anymore
    updated_at:       Optional[str] = None
    source_file_id:   Optional[str] = None
    tags_json:        Optional[Any] = None
    additional_keywords: Optional[List[str]] = None
    cairn_url:        Optional[str] = None
    ders:             Optional[List[str]] = None
    tagger:           Optional[str] = None
    file_format:      Optional[str] = None
    rate_impact:      Optional[str] = None
    document_url:     Optional[str] = None
    state_region:     Optional[str] = None
    docket_number:    Optional[str] = None
    document_type:    Optional[str] = None
    quality_check:    Optional[str] = None
    document_title:   Optional[str] = None
    utility_reform:   Optional[List[str]] = None
    parent_document:  Optional[str] = None
    regulatory_body:  Optional[str] = None
    customer_classes: Optional[List[str]] = None
    document_subtype: Optional[str] = None
    energy_resources: Optional[List[str]] = None
    org_utility_name: Optional[str] = None
    processing_notes: Optional[str] = None
    jurisdiction_type:Optional[str] = None
    related_documents:Optional[List[str]] = None
    replaces_document:Optional[str] = None
    relationship_types:Optional[List[str]] = None
    physical_climate_risk: Optional[bool] = None
    # runtime-only - we generate this on demand now
    # download_url:     Optional[str] = None # Remove if only generated on demand

class DocumentsResponse(BaseModel):
    data:        List[DocumentOut]
    page:        int
    page_size:   int
    total_count: int # Add total count for pagination info

# ─── App & CORS ────────────────────────────────────────────────────────────────

ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",") if origin.strip()]
# Fallback for local development if ALLOWED_ORIGINS is empty
if not ALLOWED_ORIGINS:
     ALLOWED_ORIGINS = ["http://localhost:8501"] # Default Streamlit port

app = FastAPI(
    title="CAIRN Document Finder API",
    version="1.1", # Incremented version
    description="Search & retrieve document metadata. Provides endpoints for generating B2 download URLs."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"], # Added POST for potential future use
    allow_headers=["*"],
)

# ─── Helper: B2 presign ─────────────────────────────────────────────────────────
# This existing helper is suitable, just ensure it uses the correct method
# and we will call it with a specific, short TTL.
def b2_get_download_url(file_id: str, ttl: int = 3600) -> Optional[str]:
    """Generates a presigned download URL for a B2 file ID."""
    if not file_id:
        logging.warning("b2_get_download_url called with empty file_id")
        return None
    try:
        logging.info(f"Attempting to generate presigned URL for b2_file_id: {file_id} with TTL: {ttl}")
        # Ensure bucket object is valid
        if not isinstance(bucket, Bucket):
             logging.error("B2 Bucket object is not initialized correctly.")
             return None
        url = bucket.get_download_url_for_fileid(file_id, valid_duration_in_seconds=ttl)
        logging.info(f"Successfully generated URL for b2_file_id: {file_id}")
        return url
    except b2_exceptions.B2Error as b2e:
        logging.error(f"[B2 SDK Error] Presign URL error for {file_id}: {b2e}")
        # Specific handling can be added based on B2Error types if needed
        return None
    except Exception as e:
        logging.exception(f"[Unexpected Error] Presign URL failed for {file_id}: {e}")
        return None

# --- Placeholder for Authentication ---
# Replace with your actual auth dependency if/when needed
async def get_current_user(token: Optional[str] = None):
    return None # No auth enforced for now

# ─── API Endpoints ────────────────────────────────────────────────────────────

# --- Existing /documents endpoint ---
@app.get("/documents", response_model=DocumentsResponse, tags=["Documents"])
def get_documents(
    # ... (keep all existing filter parameters) ...
    document_id:       Optional[str] = Query(None),
    document_title:    Optional[str] = Query(None),
    local_backup_name: Optional[str] = Query(None),
    tagger:            Optional[str] = Query(None),
    file_format:       Optional[str] = Query(None),
    rate_impact:       Optional[str] = Query(None),
    quality_check:     Optional[str] = Query(None),
    regulatory_body:   Optional[str] = Query(None),
    state_region:      Optional[str] = Query(None),
    docket_number:     Optional[str] = Query(None),
    document_type:     Optional[str] = Query(None),
    org_utility_name:  Optional[str] = Query(None),
    parent_document:   Optional[str] = Query(None),
    replaces_document: Optional[str] = Query(None),
    document_url:      Optional[str] = Query(None),
    cairn_url:         Optional[str] = Query(None),
    processing_notes:  Optional[str] = Query(None),
    published_date:    Optional[str] = Query(None),
    date_tagged:       Optional[str] = Query(None),
    last_synced_at:    Optional[str] = Query(None),
    updated_at:        Optional[str] = Query(None),
    additional_keywords: Optional[List[str]] = Query(None),
    ders:              Optional[List[str]] = Query(None),
    utility_reform:    Optional[List[str]] = Query(None),
    customer_classes:  Optional[List[str]] = Query(None),
    energy_resources:  Optional[List[str]] = Query(None),
    related_documents: Optional[List[str]] = Query(None),
    relationship_types:Optional[List[str]] = Query(None),
    physical_climate_risk: Optional[bool] = Query(None),
    # --- Pagination ---
    page:              int  = Query(1, ge=1),
    page_size:         int  = Query(20, ge=1, le=200),
    # --- REMOVED include_download_url ---
    # include_download_url: bool = False, # Remove this, URLs generated on demand
    current_user:      Optional[dict] = Depends(get_current_user) # Add for potential future auth
):
    # Add authorization checks here if current_user is implemented

    try:
        # Select all columns needed, ESPECIALLY 'id' and 'b2_file_id'
        # Using count='exact' is efficient for getting total count for pagination
        query = supabase.table("files").select("*", count='exact')

        # --- Apply filters (same logic as before) ---
        # simple eq filters
        for fld, val in {
            "document_id": document_id,
            # ... include all eq filter fields ...
             "document_title": document_title,
             "local_backup_name": local_backup_name,
             "tagger": tagger,
             "file_format": file_format,
             "rate_impact": rate_impact,
             "quality_check": quality_check,
             "regulatory_body": regulatory_body,
             "state_region": state_region,
             "docket_number": docket_number,
             "document_type": document_type,
             "org_utility_name": org_utility_name,
             "parent_document": parent_document,
             "replaces_document": replaces_document,
             "document_url": document_url,
             "cairn_url": cairn_url,
             "processing_notes": processing_notes,
             "published_date": published_date,
             "date_tagged": date_tagged,
             "last_synced_at": last_synced_at,
             "updated_at": updated_at,
        }.items():
            if val is not None and val != "": # Check for empty strings too
                query = query.eq(fld, val)

        # array contains filters
        for fld, vals in {
            "additional_keywords": additional_keywords,
            # ... include all array filter fields ...
             "ders": ders,
             "utility_reform": utility_reform,
             "customer_classes": customer_classes,
             "energy_resources": energy_resources,
             "related_documents": related_documents,
             "relationship_types": relationship_types,
        }.items():
            if vals: # Check if list is not empty
                # Supabase 'cs' (contains) expects a string representation of a list like '{"val1","val2"}'
                # Or use 'overlaps' if appropriate for your schema and needs
                query = query.cs(fld, vals) # Assuming 'contains' operator works like this

        # boolean
        if physical_climate_risk is not None:
            query = query.eq("physical_climate_risk", physical_climate_risk)

        # pagination & ordering
        start_index = (page - 1) * page_size
        # end_index = start_index + page_size - 1 # Supabase range is inclusive
        query = query.order("id", desc=False).range(start_index, start_index + page_size - 1)

        # Execute query
        result = query.execute()

        docs = result.data or []
        total_count = result.count if result.count is not None else 0

        # *** REMOVED on-load URL generation block ***

        logging.info(f"Found {len(docs)} documents for page {page} (Total: {total_count}). Filters: {Query(...)!=Query(None)}") # Basic logging

        return {
            "data": docs,
            "page": page,
            "page_size": page_size,
            "total_count": total_count
        }

    except Exception as e:
        logging.exception("Error fetching documents from Supabase")
        raise HTTPException(status_code=500, detail=f"Internal server error fetching documents: {e}")


# --- NEW: Single File Download URL Endpoint ---
@app.get("/documents/{doc_pk_id}/download-url", tags=["Download"])
async def get_single_download_url(
    doc_pk_id: int,
    current_user: Optional[dict] = Depends(get_current_user) # Add for potential future auth
):
    """
    Generates a short-lived B2 pre-signed URL for downloading a single document file.
    Requires the document's primary key ID.
    """
    # Add authorization checks here if current_user is implemented

    logging.info(f"Request received for download URL for document PK: {doc_pk_id}")
    if doc_pk_id <= 0:
         raise HTTPException(status_code=400, detail="Invalid document ID provided.")

    try:
        # Fetch only the b2_file_id using the primary key (id column)
        result = supabase.table("files").select("b2_file_id, document_title").eq("id", doc_pk_id).maybe_single().execute()

        if not result.data:
            logging.warning(f"Document PK {doc_pk_id} not found in database.")
            raise HTTPException(status_code=404, detail="Document not found")

        doc_data = result.data
        b2_file_id = doc_data.get("b2_file_id")
        doc_title = doc_data.get("document_title", f"file_{doc_pk_id}") # Get title for logging

        if not b2_file_id:
            logging.warning(f"Document PK {doc_pk_id} ('{doc_title}') found, but 'b2_file_id' is missing or null.")
            raise HTTPException(status_code=404, detail="Downloadable file reference not found for this document")

        logging.info(f"Found b2_file_id: {b2_file_id} for PK: {doc_pk_id} ('{doc_title}')")

        # Generate short-lived URL (e.g., 5 minutes = 300 seconds)
        download_url = b2_get_download_url(b2_file_id, ttl=300)

        if not download_url:
            logging.error(f"Failed to generate presigned URL for b2_file_id: {b2_file_id}")
            raise HTTPException(status_code=500, detail="Could not generate download URL")

        logging.info(f"Generated download URL for PK: {doc_pk_id} ('{doc_title}')")
        # Optional: Log the download attempt (user, doc_id, timestamp) here for auditing/limits

        return JSONResponse(content={"url": download_url}) # Use JSONResponse for clarity

    except HTTPException as he:
        # Re-raise HTTP exceptions directly
        raise he
    except Exception as e:
        # Catch Supabase or other unexpected errors
        logging.exception(f"Error getting download URL for PK {doc_pk_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error generating download link.")

# --- Add endpoints for Zipping later if needed ---
@app.post("/documents/download-zip", tags=["Download"])
async def download_documents_zip(
    doc_ids: List[int] = Body(..., embed=True),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    Fetches each document’s B2-presigned URL, downloads it,
    zips them together, and streams back a single ZIP file.
    """
    if not doc_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for pk in doc_ids:
            # 1) retrieve b2_file_id and title
            result = supabase.table("files")\
                .select("b2_file_id, document_title")\
                .eq("id", pk).maybe_single().execute()
            data = result.data or {}
            file_id = data.get("b2_file_id")
            title   = data.get("document_title", f"document_{pk}")
            if not file_id:
                continue  # skip
            # 2) get a short‐lived URL
            url = b2_get_download_url(file_id, ttl=300)
            if not url:
                continue
            # 3) stream file content
            resp = requests.get(url, stream=True, timeout=30)
            resp.raise_for_status()
            # 4) write into the zip under a safe name
            name = f"{title[:40].replace(' ','_') or pk}.pdf"
            zf.writestr(name, resp.content)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="cairn_selected.zip"'}
    )
# Example of running locally (if needed for testing)
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)