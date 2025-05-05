import os
import re
import logging
from typing import List, Optional, Any, Dict

import requests
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from supabase import create_client, Client
from b2sdk.v2 import B2Api, InMemoryAccountInfo, exception as b2_exceptions

# ─── Load environment ──────────────────────────────────────────────────────────
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
B2_KEY_ID = os.getenv("B2_APP_KEY_ID")
B2_KEY = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
SIGNED_URL_TTL = int(os.getenv("SIGNED_URL_TTL_SECONDS", "600"))

if not all([SUPABASE_URL, SUPABASE_KEY, B2_KEY_ID, B2_KEY, B2_BUCKET_NAME]):
    raise RuntimeError("Missing required env vars for Supabase/B2 clients")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ─── Initialize Supabase & B2 ─────────────────────────────────────────────────
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
_info = InMemoryAccountInfo()
b2_api = B2Api(_info)
b2_api.authorize_account("production", B2_KEY_ID, B2_KEY)
bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)

# Capture a reusable auth token for signed URLs
AUTH_TOKEN = b2_api.account_info.get_account_auth_token()
DOWNLOAD_URL_BASE = _info.get_download_url()

# ─── FastAPI setup ─────────────────────────────────────────────────────────────
app = FastAPI(title="CAIRN Document Finder API", version="2.0",
              description="Search & retrieve document metadata with signed URLs from Backblaze B2.")

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["http://localhost:8501", "http://127.0.0.1:8501"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ─── Models ────────────────────────────────────────────────────────────────────
class DocumentOut(BaseModel):
    id: int
    created_at: Optional[str]
    document_id: Optional[str]
    document_title: Optional[str]
    b2_file_id: Optional[str]

class DocumentsResponse(BaseModel):
    data: List[DocumentOut]
    page: int
    page_size: int
    total_count: int

class SignedUrlItem(BaseModel):
    url: str
    filename: str
    expires_in_seconds: int = SIGNED_URL_TTL

class BatchSignedUrlsRequest(BaseModel):
    document_ids: List[int] = Field(..., description="List of document PKs to generate signed URLs for.")

class BatchSignedUrlsResponse(BaseModel):
    urls: List[SignedUrlItem]

# ─── Helpers ────────────────────────────────────────────────────────────────────
def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Clean and truncate filename to safe characters."""
    if not name:
        return "file"
    clean = re.sub(r"[^\w\-\. ]", "_", name).strip()
    if len(clean) > max_length:
        base, dot, ext = clean.rpartition('.')
        if dot:
            clean = base[: max_length - len(ext) - 1] + '.' + ext
        else:
            clean = clean[:max_length]
    return clean or "file"


def b2_get_download_url(file_id: str, ttl: int = SIGNED_URL_TTL) -> Optional[str]:
    """Generate a signed download URL for a Backblaze B2 file."""
    try:
        info = bucket.get_file_info_by_id(file_id)
        return f"{DOWNLOAD_URL_BASE}/file/{B2_BUCKET_NAME}/{info.file_name}?Authorization={AUTH_TOKEN}"
    except b2_exceptions.B2Error as e:
        logging.error(f"B2Error generating signed URL for {file_id}: {e}")
    except Exception as e:
        logging.exception(f"Error in b2_get_download_url for {file_id}")
    return None

async def get_current_user(token: Optional[str] = None):
    # stub for future auth
    return None

# ─── Endpoints ──────────────────────────────────────────────────────────────────
@app.get("/documents", response_model=DocumentsResponse, tags=["Documents"])
def list_documents(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: Any = Depends(get_current_user)
):
    """List documents with paging and dynamic filters."""
    try:
        query = supabase.table("files").select("*", count="exact")
        for key, value in request.query_params.multi_items():
            if key in ("page", "page_size"): continue
            if "," in value:
                query = query.cs(key, value.split(","))
            else:
                query = query.eq(key, value)
        start = (page - 1) * page_size
        query = query.order("id", desc=False).range(start, start + page_size - 1)
        res = query.execute()
        return {
            "data": res.data or [],
            "page": page,
            "page_size": page_size,
            "total_count": res.count or 0
        }
    except Exception as e:
        logging.exception("Error fetching documents")
        raise HTTPException(500, f"Internal error: {e}")

@app.get("/documents/{doc_pk}/download-url", response_model=SignedUrlItem, tags=["Download"])
def single_download_url(
    doc_pk: int, current_user: Any = Depends(get_current_user)
) -> SignedUrlItem:
    """Generate a signed download URL for a single document."""
    if doc_pk <= 0:
        raise HTTPException(400, "Invalid document ID")
    res = supabase.table("files").select("b2_file_id,document_title,document_id").eq("id", doc_pk).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "Document not found")
    fid = res.data.get("b2_file_id")
    if not fid:
        raise HTTPException(404, "No file attached to this document")
    title = res.data.get("document_title") or res.data.get("document_id") or f"file_{doc_pk}"
    base = sanitize_filename(title)
    ext = os.path.splitext(base)[1] or ".pdf"
    filename = f"{os.path.splitext(base)[0]}{ext}"
    url = b2_get_download_url(fid)
    if not url:
        raise HTTPException(500, "Failed to generate download URL")
    return {"url": url, "filename": filename, "expires_in_seconds": SIGNED_URL_TTL}

@app.post("/documents/batch-signed-urls", response_model=BatchSignedUrlsResponse, tags=["Download"])
def batch_signed_urls(
    body: BatchSignedUrlsRequest, current_user: Any = Depends(get_current_user)
) -> BatchSignedUrlsResponse:
    """Return a list of signed URLs for multiple documents."""
    ids = [i for i in body.document_ids if isinstance(i, int) and i > 0]
    if not ids:
        raise HTTPException(400, "No valid document IDs provided")
    res = supabase.table("files").select("id,b2_file_id,document_title,document_id").in_("id", ids).execute()
    items = []
    for row in res.data or []:
        fid = row.get("b2_file_id")
        if not fid:
            logging.warning(f"Skipping {row['id']}: no file attached")
            continue
        title = row.get("document_title") or row.get("document_id") or f"file_{row['id']}"
        base = sanitize_filename(title)
        ext = os.path.splitext(base)[1] or ".pdf"
        filename = f"{os.path.splitext(base)[0]}{ext}"
        url = b2_get_download_url(fid)
        if url:
            items.append({"url": url, "filename": filename, "expires_in_seconds": SIGNED_URL_TTL})
    if not items:
        raise HTTPException(404, "No downloadable files found for provided IDs")
    return {"urls": items}

# ─── Run for local testing ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
