# backend/main.py

import os
import io
import uuid
import re
import zipfile
import logging
from typing import List, Optional, Any
from urllib.parse import quote_plus

import requests
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from supabase import create_client, Client
from b2sdk.v2 import B2Api, InMemoryAccountInfo, Bucket
from b2sdk.v2 import exception as b2_exceptions
from fastapi import FastAPI, HTTPException, Query, Depends, Request
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

    _info = InMemoryAccountInfo()
    b2_api: B2Api = B2Api(_info)
    b2_api.authorize_account("production", B2_KEY_ID, B2_KEY)
    bucket: Bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)

    logging.info("✅ Supabase and B2 clients initialized successfully.")
except Exception as e:
    logging.exception("FATAL: Failed to initialize Supabase or B2 client.")
    raise RuntimeError(f"Client initialization failed: {e}")

# ─── Schemas ──────────────────────────────────────────────────────────────────
class DocumentOut(BaseModel):
    id: int
    b2_file_id: Optional[str] = None
    document_title: Optional[str] = None
    document_id: Optional[str] = None
    # ... plus your other fields (omitted here for brevity) ...

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
    version="1.3",
    description="Search & retrieve document metadata. Single & batch ZIP download endpoints."
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

def b2_get_download_url(file_id: str, ttl: int = 3600) -> Optional[str]:
    """
    Generates a presigned URL for a B2 file ID by:
      1) getting the base download-by-id URL from the session
      2) requesting a short‑lived auth token from the raw API (with correct signature)
      3) stitching them together
    """
    if not file_id:
        logging.warning("Empty b2_file_id in b2_get_download_url")
        return None

    try:
        # 1) Base download URL (no token yet)
        base_download_url = b2_api.session.get_download_url_by_id(file_id)

        # 2) Fetch the auth token using the exact positional args API expects:
        api_url = b2_api.raw_api.api_url
        acct_token = b2_api.raw_api.account_auth_token
        auth_info = b2_api.raw_api.get_download_authorization(
            api_url,
            acct_token,
            bucket.id_,   # your bucket ID
            "",           # file_name_prefix (empty = this exact file)
            ttl           # valid_duration_in_seconds
        )
        token = auth_info["authorizationToken"]

        # 3) Return the full presigned URL
        return f"{base_download_url}?Authorization={token}"

    except b2_exceptions.B2Error as e:
        logging.error(f"[B2Error] presigning {file_id}: {e}")
        return None
    except Exception as e:
        logging.exception(f"[Unexpected] b2_get_download_url failed for {file_id}: {e}")
        return None

async def get_current_user(token: Optional[str] = None):
    return None  # placeholder—no auth for now

# ─── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/documents", response_model=DocumentsResponse, tags=["Documents"])
def list_documents(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current_user: Any = Depends(get_current_user),
):
    """
    Dynamically applies **any** query params (e.g. org_utility_name, document_type, etc.)
    as filters.  Paginate with `page` & `page_size`.
    """
    try:
        query = supabase.table("files").select("*", count="exact")

        # Pull every ?key=value (or ?key=a,b) except page/page_size
        for key, value in request.query_params.multi_items():
            if key in ("page", "page_size"):
                continue

            # if user passed commas, treat as an array filter
            if "," in value:
                vals = value.split(",")
                query = query.cs(key, vals)
            else:
                query = query.eq(key, value)

        # apply pagination & ordering
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
        raise HTTPException(status_code=500, detail="Internal error fetching documents")

@app.get("/documents/{doc_pk}/download-url", response_model=BatchDownloadResponse, tags=["Download"])
async def single_download_url(
    doc_pk: int, current_user: Any = Depends(get_current_user)
):
    logging.info(f"Single download URL requested for PK: {doc_pk}")
    if doc_pk <= 0:
        raise HTTPException(status_code=400, detail="Invalid document ID")

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

    title = res.data.get("document_title") or res.data.get("document_id") or f"file_{doc_pk}"
    base = sanitize_filename(title)
    ext = ".pdf"
    if "." in base and 1 < len(base.rsplit(".", 1)[1]) <= 4:
        name, _, e = base.rpartition(".")
        ext = "." + e
        base = name
    filename = f"{base}{ext}"

    url = b2_get_download_url(b2_id, ttl=300)
    if not url:
        logging.error(f"Could not generate URL for PK {doc_pk}")
        raise HTTPException(status_code=500, detail="Failed to generate download link")

    return {"url": url, "filename": filename, "expires_in_seconds": 300}

@app.post("/documents/batch-download-url", response_model=BatchDownloadResponse, tags=["Download"])
async def batch_download_url(
    body: BatchDownloadRequest, current_user: Any = Depends(get_current_user)
):
    raw_ids = body.document_ids or []
    valid_ids, bad = [], []
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

    # fetch b2 IDs & titles
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

    # build ZIP in memory
    buf = io.BytesIO()
    added = 0
    errors = []
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        for r in to_zip:
            fid = r["b2_file_id"]
            pk = r["id"]
            title = r.get("document_title") or r.get("document_id") or f"file_{pk}"
            entry_base = sanitize_filename(title)
            ext = ".pdf"
            if "." in entry_base and 1 < len(entry_base.rsplit(".", 1)[1]) <= 4:
                n, _, e = entry_base.rpartition(".")
                ext = "." + e
                entry_base = n
            entry_name = f"{entry_base}{ext}"

            url = b2_get_download_url(fid, ttl=120)
            if not url:
                logging.error(f"Couldn’t presign PK {pk}")
                errors.append(pk)
                continue

            try:
                rdata = requests.get(url, timeout=30).content
                z.writestr(entry_name, rdata)
                added += 1
                logging.info(f"Added {entry_name}")
            except Exception as e:
                logging.exception(f"Error grabbing PK {pk}: {e}")
                errors.append(pk)

    if added == 0:
        raise HTTPException(status_code=500, detail="Failed to fetch any files for ZIP")

    # upload ZIP back to B2
    buf.seek(0)
    zip_bytes = buf.read()
    b2_name = f"{B2_TEMP_ZIP_PREFIX}{uuid.uuid4()}.zip"
    try:
        fv = bucket.upload_bytes(zip_bytes, b2_name, content_type="application/zip")
        zip_id = fv.id_
    except Exception as e:
        logging.exception("Uploading ZIP failed")
        raise HTTPException(status_code=500, detail="Failed storing ZIP in B2")

    final_url = b2_get_download_url(zip_id, ttl=ZIP_URL_TTL_SECONDS)
    if not final_url:
        raise HTTPException(status_code=500, detail="Failed to presign final ZIP")

    suggested_name = f"cairn_{added}_files.zip"
    logging.info(f"Batch ZIP ready: {suggested_name}, errors: {errors}")
    return {"url": final_url, "filename": suggested_name, "expires_in_seconds": ZIP_URL_TTL_SECONDS}
