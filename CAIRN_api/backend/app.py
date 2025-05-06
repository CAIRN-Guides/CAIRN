# backend/main.py

import os
import io
import uuid
import re
import zipfile
import logging
from typing import List, Optional, Any, Dict
from urllib.parse import quote_plus, urljoin

import requests
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse  # Added StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from supabase import create_client, Client
from b2sdk.v2 import B2Api, InMemoryAccountInfo, Bucket
from b2sdk.v2 import exception as b2_exceptions

# ─── Load environment ──────────────────────────────────────────────────────────
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
B2_KEY_ID = os.getenv("B2_APP_KEY_ID")
B2_KEY = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
B2_TEMP_ZIP_PREFIX = os.getenv("B2_TEMP_ZIP_PREFIX", "temp-zips/")
ZIP_URL_TTL_SECONDS = int(os.getenv("ZIP_URL_TTL_SECONDS", "600"))

if not all([SUPABASE_URL, SUPABASE_KEY, B2_KEY_ID, B2_KEY, B2_BUCKET_NAME]):
    raise RuntimeError("Missing one or more required env vars in backend/.env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ─── Initialize Supabase & B2 Clients ─────────────────────────────────────────
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Initialize B2 API with persistent info
    _info = InMemoryAccountInfo()
    b2_api = B2Api(_info)
    b2_api.authorize_account("production", B2_KEY_ID, B2_KEY)
    bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)
    
    # Store some important info we'll need later
    DOWNLOAD_URL_BASE = _info.get_download_url().rstrip("/")
    
    logging.info("✅ Supabase and B2 clients initialized successfully.")
    logging.info(f"Using B2 download base: {DOWNLOAD_URL_BASE}")
except Exception as e:
    logging.exception("FATAL: Failed to initialize Supabase or B2 client.")
    raise RuntimeError(f"Client initialization failed: {e}")

# ─── Schemas ──────────────────────────────────────────────────────────────────
class DocumentOut(BaseModel):
    id: int
    created_at: Optional[str] = None
    document_id: Optional[str] = None
    document_title: Optional[str] = None 
    b2_file_id: Optional[str] = None
    # Add other fields as needed

class DocumentsResponse(BaseModel):
    data: List[DocumentOut]
    page: int
    page_size: int
    total_count: int

class BatchDownloadRequest(BaseModel):
    document_ids: List[Any] = Field(..., description="List of document PKs to zip.")

class BatchDownloadResponse(BaseModel):
    url: str
    filename: str
    expires_in_seconds: int

# ─── CORS & App Setup ──────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["http://localhost:8501", "http://127.0.0.1:8501"]

app = FastAPI(
    title="CAIRN Document Finder API",
    version="1.5",
    description="Search & retrieve document metadata with Backblaze B2 download support."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Strip bad chars, collapse underscores, truncate if too long."""
    if not name:
        return "unknown"
    clean = re.sub(r"[^\w\-.]", "_", name)
    clean = re.sub(r"_+", "_", clean).strip("_.")
    if len(clean) > max_length:
        base, dot, ext = clean.rpartition(".")
        if dot and len(ext) < 10:
            clean = base[: max_length - len(ext) - 1] + "." + ext
        else:
            clean = clean[:max_length]
    return clean or "file"

<<<<<<< HEAD
def b2_get_download_url(file_id: str, ttl_seconds: int = 3600) -> Optional[str]:
    """
    Generate a direct download URL for a B2 file ID.
    Uses the file_id directly to generate a URL that works with the B2 API.
    """
=======
def b2_get_download_url(file_id: str, ttl: int = 3600) -> Optional[str]:
    """Generates a presigned download URL for a B2 file ID."""
>>>>>>> parent of 7f8a1b4 (backend helper function fix)
    if not file_id:
        logging.warning("Empty file_id in b2_get_download_url")
        return None
    
    try:
<<<<<<< HEAD
        # Simple approach - directly build a URL to download by ID
        download_url = f"{DOWNLOAD_URL_BASE}/b2api/v1/b2_download_file_by_id?fileId={file_id}"
        
        # Include the Auth token in the header when we make the request
        headers = {"Authorization": b2_api.account_info.get_account_auth_token()}
        
        logging.info(f"Generated direct download URL for file {file_id}")
        
        # Test the URL by making a HEAD request
        response = requests.head(download_url, headers=headers, timeout=5)
        if response.status_code not in (200, 302):
            logging.warning(f"Download URL test failed with status {response.status_code}")
            return None
            
        return download_url
        
=======
        logging.info(f"Attempting to generate presigned URL for b2_file_id: {file_id} with TTL: {ttl}")
        if not isinstance(bucket, Bucket):
            logging.error("B2 Bucket object is not initialized correctly.")
            return None
        # Use get_download_url which allows setting content disposition
        # file_info = bucket.get_file_info_by_id(file_id) # Get file info if needed for name
        url = bucket.get_download_url_for_fileid(file_id, valid_duration_in_seconds=ttl)
        logging.info(f"Successfully generated URL for b2_file_id: {file_id}")
        return url
    except b2_exceptions.B2Error as b2e:
        logging.error(f"[B2 SDK Error] Presign URL error for {file_id}: {b2e}")
        return None
>>>>>>> parent of 7f8a1b4 (backend helper function fix)
    except Exception as e:
        logging.exception(f"Failed to generate download URL for {file_id}: {e}")
        return None

async def get_current_user(token: Optional[str] = None):
    # Placeholder for future auth implementation
    return None

# ─── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/documents", response_model=DocumentsResponse, tags=["Documents"])
def list_documents(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: Any = Depends(get_current_user),
):
    """
    List documents with filtering based on query parameters.
    Supports dynamic filtering on any field.
    """
    try:
        query = supabase.table("files").select("*", count="exact")

        # Apply all query params as filters (except pagination)
        for key, value in request.query_params.multi_items():
            if key in ("page", "page_size"):
                continue

            # Handle comma-separated values as array filters
            if "," in value:
                vals = value.split(",")
                query = query.cs(key, vals)
            else:
                query = query.eq(key, value)

        # Apply pagination
        start = (page - 1) * page_size
        query = query.order("id", desc=False).range(start, start + page_size - 1)

        result = query.execute()
        docs = result.data or []
        total = result.count or 0

        logging.info(f"Found {len(docs)} documents (page {page}/{page_size}, total={total})")
        return {
            "data": docs,
            "page": page,
            "page_size": page_size,
            "total_count": total
        }

    except Exception as e:
        logging.exception("Error fetching documents")
        raise HTTPException(status_code=500, detail=f"Internal error fetching documents: {str(e)}")

<<<<<<< HEAD
@app.get("/documents/{doc_pk}/download-url", response_model=BatchDownloadResponse, tags=["Download"])
async def single_download_url(
    doc_pk: int, current_user: Any = Depends(get_current_user)
=======

# --- Existing Single File Download URL Endpoint (Unchanged) ---
@app.get("/documents/{doc_pk_id}/download-url", tags=["Download"], response_model=BatchDownloadResponse)
async def get_single_download_url(
    doc_pk_id: int,
    current_user: Optional[dict] = Depends(get_current_user)
>>>>>>> parent of 7f8a1b4 (backend helper function fix)
):
    """Generate download URL for a single document"""
    logging.info(f"Single download URL requested for PK: {doc_pk}")
    if doc_pk <= 0:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    # Get document details from Supabase
    res = (
        supabase.table("files")
        .select("b2_file_id,document_title,document_id")
        .eq("id", doc_pk)
        .maybe_single()
        .execute()
    )
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found")

    b2_id = res.data.get("b2_file_id")
    if not b2_id:
        raise HTTPException(status_code=404, detail="No B2 file attached to this document")

    # Create a good filename
    title = res.data.get("document_title") or res.data.get("document_id") or f"file_{doc_pk}"
    base = sanitize_filename(title)
    ext = ".pdf"  # Default
    if "." in base and 1 < len(base.rsplit(".", 1)[1]) <= 4:
        name, _, e = base.rpartition(".")
        ext = "." + e
        base = name
    filename = f"{base}{ext}"

    # Try to use the file ID to download directly
    # With B2, this requires the auth token in the headers
    try:
        # Create a special download endpoint to proxy the request through our server
        # This avoids exposing the auth token to the frontend
        proxy_url = f"/api/b2-proxy/{b2_id}/{filename}"
        logging.info(f"Created proxy URL for file {b2_id}")
        
        return {
            "url": proxy_url,
            "filename": filename,
            "expires_in_seconds": 300
        }
        
    except Exception as e:
        logging.exception(f"Error generating download URL for {b2_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate download link")

<<<<<<< HEAD
# Fixed proxy endpoint for B2 downloads
@app.get("/api/b2-proxy/{file_id}/{filename}")
async def proxy_b2_download(file_id: str, filename: str):
=======

# --- NEW: Batch Download URL Endpoint ---
@app.post("/documents/batch-download-url", tags=["Download"], response_model=BatchDownloadResponse)
async def get_batch_download_url(
    request_data: BatchDownloadRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
>>>>>>> parent of 7f8a1b4 (backend helper function fix)
    """
    Proxy B2 downloads through our server.
    This allows us to include auth headers without exposing them to the client.
    """
    try:
        # Construct the download URL
        download_url = f"{DOWNLOAD_URL_BASE}/b2api/v1/b2_download_file_by_id?fileId={file_id}"
        auth_token = b2_api.account_info.get_account_auth_token()
        headers = {"Authorization": auth_token}
        
        # Make a request to B2 with proper auth
        session = requests.Session()
        
        # Special handling for ZIP files to ensure proper content type
        is_zip = filename.lower().endswith('.zip')
        content_type = "application/zip" if is_zip else "application/octet-stream"
        
        try:
            # Stream the response to avoid loading the entire file into memory
            response = session.get(download_url, headers=headers, stream=True)
            response.raise_for_status()  # Raise exception for 4XX/5XX status codes
            
            # Get content info from the headers
            if 'Content-Type' in response.headers:
                content_type = response.headers['Content-Type']
            content_length = response.headers.get('Content-Length')
            
            # Create response headers with proper content disposition
            resp_headers = {
                "Content-Disposition": f'attachment; filename="{filename}"',
            }
            if content_length:
                resp_headers["Content-Length"] = content_length
                
            # Log the download attempt
            logging.info(f"Streaming {filename} ({content_type}, size: {content_length})")
            
            # Use a StreamingResponse to efficiently transfer the file without loading it all into memory
            return StreamingResponse(
                response.iter_content(chunk_size=8192),
                headers=resp_headers,
                media_type=content_type
            )
            
        except requests.RequestException as e:
            logging.error(f"Request to B2 failed: {str(e)}")
            raise HTTPException(status_code=502, detail=f"B2 download failed: {str(e)}")
            
    except Exception as e:
        logging.exception(f"Error proxying download for {file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download file: {str(e)}")

@app.post("/documents/batch-download-url", response_model=BatchDownloadResponse, tags=["Download"])
async def batch_download_url(
    body: BatchDownloadRequest, current_user: Any = Depends(get_current_user)
):
    """Batch download multiple documents as a ZIP file"""
    raw_ids = body.document_ids or []
    valid_ids, bad = [], []
    
    # Validate IDs
    for x in raw_ids:
        try:
            i = int(x)
            if i > 0:
                valid_ids.append(i)
            else:
                bad.append(x)
        except Exception:
            bad.append(x)
            
    if not valid_ids:
        raise HTTPException(status_code=400, detail="No valid document IDs provided")
        
    logging.info(f"Batch ZIP for IDs: {valid_ids}, dropped: {bad}")

    # Fetch document details from Supabase
    db_res = (
        supabase.table("files")
        .select("id,b2_file_id,document_title,document_id")
        .in_("id", valid_ids)
        .execute()
    )
    
    to_zip = []
    found = {r["id"] for r in db_res.data or []}
    
    for r in db_res.data or []:
        if r.get("b2_file_id"):
            to_zip.append(r)
        else:
            logging.warning(f"Skipping PK {r['id']}: no b2_file_id")

    missing = set(valid_ids) - found
    if missing:
        logging.warning(f"Missing from DB: {missing}")
        
    if not to_zip:
        raise HTTPException(status_code=404, detail="No files to add to ZIP")

    # Build ZIP in memory
    buf = io.BytesIO()
    added = 0
    errors = []
    
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        for r in to_zip:
            fid = r["b2_file_id"]
            pk = r["id"]
            title = r.get("document_title") or r.get("document_id") or f"file_{pk}"
            entry_base = sanitize_filename(title)
            
            # Determine file extension
            ext = ".pdf"  # Default
            if "." in entry_base and 1 < len(entry_base.rsplit(".", 1)[1]) <= 4:
                n, _, e = entry_base.rpartition(".")
                ext = "." + e
                entry_base = n
            entry_name = f"{entry_base}{ext}"

            # Direct download with authentication
            download_url = f"{DOWNLOAD_URL_BASE}/b2api/v1/b2_download_file_by_id?fileId={fid}"
            headers = {"Authorization": b2_api.account_info.get_account_auth_token()}

            # Download file and add to ZIP
            try:
                response = requests.get(download_url, headers=headers, timeout=30)
                response.raise_for_status()
                
                z.writestr(entry_name, response.content)
                added += 1
                logging.info(f"Added {entry_name} to ZIP")
            except Exception as e:
                logging.exception(f"Error downloading file for PK {pk}: {e}")
                errors.append(pk)

    if added == 0:
        raise HTTPException(status_code=500, detail="Failed to fetch any files for ZIP")

    # Upload ZIP to B2
    buf.seek(0)
    zip_bytes = buf.read()
    zip_filename = f"{B2_TEMP_ZIP_PREFIX}{uuid.uuid4()}.zip"
    
    try:
        # Upload the ZIP file to B2
        file_info = bucket.upload_bytes(
            data_bytes=zip_bytes,
            file_name=zip_filename,
            content_type="application/zip"
        )
        zip_file_id = file_info.id_
        
        # Create a proxy URL for the ZIP download
        suggested_name = f"cairn_documents_{added}_files.zip"
        proxy_url = f"/api/b2-proxy/{zip_file_id}/{suggested_name}"
        logging.info(f"Created ZIP file in B2 with ID {zip_file_id}")
        
    except Exception as e:
        logging.exception(f"Error uploading ZIP file to B2: {e}")
        raise HTTPException(status_code=500, detail="Failed to store generated ZIP file")

    suggested_name = f"cairn_documents_{added}_files.zip"
    logging.info(f"Batch ZIP ready: {suggested_name}, contains {added} files, had {len(errors)} errors")
    
    return {
        "url": proxy_url,
        "filename": suggested_name,
        "expires_in_seconds": ZIP_URL_TTL_SECONDS
    }

# For local testing
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)