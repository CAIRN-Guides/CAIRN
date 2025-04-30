import os
import logging
import time
from typing import List, Optional, Any
import numpy as np

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client
from b2sdk.v2 import B2Api, InMemoryAccountInfo, Bucket

from llama_cloud_services import LlamaParse
from llama_index.core.node_parser import SentenceSplitter
import cohere
import faiss

# ─── Load environment ──────────────────────────────────────────────────────────
load_dotenv()  # loads backend/.env

SUPABASE_URL        = os.getenv("SUPABASE_URL")
SUPABASE_KEY        = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
B2_KEY_ID           = os.getenv("B2_APP_KEY_ID")
B2_KEY              = os.getenv("B2_APP_KEY")
B2_BUCKET_NAME      = os.getenv("B2_BUCKET_NAME")

LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")
COHERE_API_KEY      = os.getenv("COHERE_API_KEY")

if not all([
    SUPABASE_URL,
    SUPABASE_KEY,
    B2_KEY_ID,
    B2_KEY,
    B2_BUCKET_NAME,
    LLAMA_CLOUD_API_KEY,
    COHERE_API_KEY
]):
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

# TODO: formalize this
class TagResponse(BaseModel):
    overview: Optional[str]
    content: Optional[str]

# ─── App & CORS ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CAIRN Document Finder API",
    version="1.0",
    description="Search & retrieve all metadata fields plus presigned B2 URLs"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production!
    allow_methods=["GET"],
    allow_headers=["*"],
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

# ─── /generate_tags endpoint ───────────────────────────────────────────────────────
@app.get("/generate_tags")
async def generate_tags():

    # TODO: make available for all docs
    DOC_NAME = 'PSE_IRP_ElectricChapters_3.31.2025.pdf'
    
    # TODO: move these prompts somewhere else
    OVERVIEW_QUERY = f"""
    Using the document (named {DOC_NAME}), find the following fields, listed below. They will be listed as follows: 'Field Name (additional explanation)'.
    Output each answer as follows: 'Field Name: answer', using the provided field name, with each on a new line.
    If you don't know or if there isn't enough information, just put 'unknown'. Here are the fields:
    Document Title (Full title of the document. Include subtitles, if they are present.)
    Published Date (When the document was officially published. Answer in format MM/DD/YYYY. Use the document name if the information is not in the info provided.)
    Org/Utility Name (Primary utility organization associated with document. Examples may be: Pacific Gas & Electric.)
    Docket Number (Official proceeding identifier.)
    Document Type (Primary classification of document. Examples may include: Rate Case, Compliance Filing, Resource Plan, Investigation, etc. These should be 1-2 words long.)
    File format (Type of file. Use the document name.)
    """

    CONTENT_QUERY = f"""
    Using the document (named {DOC_NAME}), find the following fields, listed below. They will be listed as follows: 'Field Name (additional explanation)'.
    Output each answer as follows: 'Field Name: answer', using the provided field name, with each on a new line.
    If you don't know or if there isn't enough information, just put 'unknown'. Here are the fields:
    Rate Impact (Does the document discuss impacts on energy bills? Only return Y for yes, N for no, or otherwise return unknown.)
    Energy Resources (Which sources of energy do the document primarily discuss? Examples might include Solar, Battery Storage, Natural Gas, or Thermal Energy. Return the answers, separated by commas.)
    Customer Classes (What types of customers are discussed? Examples might include Residential, Commercial, or Industrial. Return the answers, separated by commas.)
    Physical Climate Risk (Is the primary purpose of the document discussing physical climate risk (wildfires, heat, etc.)? Return Y for yes, N for no, or otherwise return unknown.)
    """

    result = await LlamaParse().aparse(f"./{DOC_NAME}")

    # sentence splitter
    text_nodes = await result.aget_text_nodes()
    full_text = text_nodes[0].text

    splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    chunks = splitter.split_text(full_text)

    # embedding
    co = cohere.Client(COHERE_API_KEY)

    def batch_embed(texts, batch_size=50, delay_secs=10):
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]

            try:
                response = co.embed(
                    texts=batch,
                    model="embed-english-v3.0",
                    input_type="search_document"
                )
                embeddings.extend(response.embeddings)

            except cohere.errors.TooManyRequestsError as e:
                print(f"Rate limit hit, waiting before retrying: {e}")
                time.sleep(60)
                continue

            time.sleep(delay_secs)

        return embeddings
    
    tagging_embeddings = batch_embed(chunks)

    # indexing
    index = faiss.IndexFlatL2(len(tagging_embeddings[0]))
    index.add(np.array(tagging_embeddings))

    # query embedding
    overview_query_embedding = co.embed(
        texts=[OVERVIEW_QUERY],
        model="embed-english-v3.0",
        input_type="search_query"
    ).embeddings[0]

    _, idx = index.search(np.array([overview_query_embedding]), k=10)
    overview_chunks = [chunks[i] for i in idx[0]]

    content_query_embedding = co.embed(
        texts=[CONTENT_QUERY],
        model="embed-english-v3.0",
        input_type="search_query"
    ).embeddings[0]

    _, idx = index.search(np.array([content_query_embedding]), k=10)
    content_chunks = [chunks[i] for i in idx[0]]

    # LLM
    OVERVIEW_CONTEXT = "\n\n".join(overview_chunks)

    overview_response = co.chat(
        model="command-r",
        message=f"Answer the question based on the following context:\n\n{OVERVIEW_CONTEXT}\n\nQuestion: {OVERVIEW_QUERY}\nAnswer:",
        max_tokens=300,
        temperature=0
    ).text.strip()

    CONTENT_CONTEXT = "\n\n".join(content_chunks)

    content_response = co.chat(
        model="command-r",
        message=f"Answer the question based on the following context:\n\n{CONTENT_CONTEXT}\n\nQuestion: {CONTENT_QUERY}\nAnswer:",
        max_tokens=300,
        temperature=0
    ).text.strip()

    return {
        "overview": overview_response,
        "content": content_response
    }