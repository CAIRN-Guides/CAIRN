import os
import logging
from typing import List, Optional, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client
from b2sdk.v2 import B2Api, InMemoryAccountInfo, Bucket

# ─── Load environment ──────────────────────────────────────────────────────────
load_dotenv()  # loads backend/.env

SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
B2_KEY_ID       = os.getenv("B2_APP_KEY_ID")
B2_KEY          = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME  = os.getenv("B2_BUCKET_NAME")

if not all([SUPABASE_URL, SUPABASE_KEY, B2_KEY_ID, B2_KEY, B2_BUCKET_NAME]):
    raise RuntimeError("Missing one or more required env vars in backend/.env")

# ─── Clients ──────────────────────────────────────────────────────────────────
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

_info = InMemoryAccountInfo()
_b2   = B2Api(_info)
_b2.authorize_account("production", B2_KEY_ID, B2_KEY)
bucket: Bucket = _b2.get_bucket_by_name(B2_BUCKET_NAME)

# ─── Schemas ──────────────────────────────────────────────────────────────────
class DocumentOut(BaseModel):
    # All your files.* columns
    id: int
    created_at:       Optional[str]
    document_id:      Optional[str]
    local_backup_name:Optional[str]
    published_date:   Optional[str]
    date_tagged:      Optional[str]
    last_synced_at:   Optional[str]
    b2_file_id:       Optional[str]
    b2_temp_url:      Optional[str]
    updated_at:       Optional[str]
    source_file_id:   Optional[str]
    tags_json:        Optional[Any]
    additional_keywords: Optional[List[str]]
    cairn_url:        Optional[str]
    ders:             Optional[List[str]]
    tagger:           Optional[str]
    file_format:      Optional[str]
    rate_impact:      Optional[str]
    document_url:     Optional[str]
    state_region:     Optional[str]
    docket_number:    Optional[str]
    document_type:    Optional[str]
    quality_check:    Optional[str]
    document_title:   Optional[str]
    utility_reform:   Optional[List[str]]
    parent_document:  Optional[str]
    regulatory_body:  Optional[str]
    customer_classes: Optional[List[str]]
    document_subtype: Optional[str]
    energy_resources: Optional[List[str]]
    org_utility_name: Optional[str]
    processing_notes: Optional[str]
    jurisdiction_type:Optional[str]
    related_documents:Optional[List[str]]
    replaces_document:Optional[str]
    relationship_types:Optional[List[str]]
    physical_climate_risk: Optional[bool]
    # runtime-only
    download_url:     Optional[str] = None

class DocumentsResponse(BaseModel):
    data:      List[DocumentOut]
    page:      int
    page_size: int

# ─── App & CORS ────────────────────────────────────────────────────────────────

# Load allowed origins from environment variable set in Render
# Default to an empty list if not set, preventing any cross-origin requests by default
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",") if origin.strip()]
# If the env var was empty or just contained commas/whitespace, ALLOWED_ORIGINS will be []

app = FastAPI(
    title="CAIRN Document Finder API",
    version="1.0",
    description="Search & retrieve all metadata fields plus presigned B2 URLs"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS, # Use the loaded list from environment variable
    allow_credentials=True,       # Often needed, set depending on auth needs
    allow_methods=["GET", "OPTIONS"], # Add "OPTIONS" for browser preflight requests
    allow_headers=["*"],          # Allows all headers, you could restrict if needed
)

# ─── Helper: B2 presign ─────────────────────────────────────────────────────────
def b2_get_download_url(file_id: str, ttl: int = 3600) -> Optional[str]:
    try:
        return bucket.get_download_url_for_fileid(file_id, valid_duration_in_seconds=ttl)
    except Exception as e:
        logging.error(f"[B2] presign error for {file_id}: {e}")
        return None

# ─── /documents endpoint ───────────────────────────────────────────────────────
@app.get("/documents", response_model=DocumentsResponse)
def get_documents(
    # text-based filters
    document_id:      Optional[str] = Query(None),
    document_title:   Optional[str] = Query(None),
    local_backup_name:Optional[str] = Query(None),
    tagger:           Optional[str] = Query(None),
    file_format:      Optional[str] = Query(None),
    rate_impact:      Optional[str] = Query(None),
    quality_check:    Optional[str] = Query(None),
    regulatory_body:  Optional[str] = Query(None),
    state_region:     Optional[str] = Query(None),
    docket_number:    Optional[str] = Query(None),
    document_type:    Optional[str] = Query(None),
    org_utility_name: Optional[str] = Query(None),
    parent_document:  Optional[str] = Query(None),
    replaces_document:Optional[str] = Query(None),
    document_url:     Optional[str] = Query(None),
    cairn_url:        Optional[str] = Query(None),
    processing_notes: Optional[str] = Query(None),
    # date filters (ISO date)
    published_date:   Optional[str] = Query(None),
    date_tagged:      Optional[str] = Query(None),
    last_synced_at:   Optional[str] = Query(None),
    updated_at:       Optional[str] = Query(None),
    # array filters
    additional_keywords: Optional[List[str]] = Query(None),
    ders:                 Optional[List[str]] = Query(None),
    utility_reform:       Optional[List[str]] = Query(None),
    customer_classes:     Optional[List[str]] = Query(None),
    energy_resources:     Optional[List[str]] = Query(None),
    related_documents:    Optional[List[str]] = Query(None),
    relationship_types:   Optional[List[str]] = Query(None),
    # boolean filter
    physical_climate_risk: Optional[bool] = Query(None),
    # pagination & URL
    page:                int  = Query(1, ge=1),
    page_size:           int  = Query(20, ge=1, le=200),
    include_download_url: bool = False,
):
    try:
        q = supabase.table("files").select("*")

        # simple eq filters
        for fld, val in {
            "document_id": document_id,
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
            if val is not None:
                q = q.eq(fld, val)

        # array contains filters
        for fld, vals in {
            "additional_keywords": additional_keywords,
            "ders": ders,
            "utility_reform": utility_reform,
            "customer_classes": customer_classes,
            "energy_resources": energy_resources,
            "related_documents": related_documents,
            "relationship_types": relationship_types,
        }.items():
            if vals:
                q = q.contains(fld, vals)

        # boolean
        if physical_climate_risk is not None:
            q = q.eq("physical_climate_risk", physical_climate_risk)

        # pagination & ordering
        start, end = (page - 1) * page_size, page * page_size - 1
        rows = q.order("id", desc=False).range(start, end).execute().data or []

        # attach download_url if requested
        if include_download_url:
            for r in rows:
                fid = r.get("b2_file_id")
                r["download_url"] = b2_get_download_url(fid) if fid else None

        return {"data": rows, "page": page, "page_size": page_size}
    except Exception as e:
        logging.exception("Error in /documents")
        raise HTTPException(status_code=502, detail=str(e))
