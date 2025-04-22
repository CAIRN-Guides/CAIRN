#!/usr/bin/env python
"""
cairn_full_sync.py —  
  • Sync Google Sheets → Supabase (files, tags, file_tags, tags_json)  
  • Sync Supabase files → Backblaze B2 (upload & presign)  
"""

from __future__ import annotations
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from supabase import Client, create_client           # pip install supabase-py
from b2sdk.v2 import (                               # pip install b2sdk
    B2Api,
    InMemoryAccountInfo,
    Bucket,
    UploadSourceLocalFile,
)

# ───────────────────────────────────────────────────────────────────────────────
# 1 · CONFIGURATION
# ───────────────────────────────────────────────────────────────────────────────
load_dotenv()

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Google Sheets
SHEET_NAME     = os.getenv("GSHEET_NAME", "CAIRN_Labels_Gsheets_Input")
WORKSHEET_NAME = os.getenv("GSHEET_WORKSHEET", "Document_Tags")
CREDS_FILE     = Path(os.getenv("GOOGLE_CREDS_FILE", "cairn_google_creds.json"))

# Local folder where your PDFs live (named by File ID)
BACKUP_DIR = Path(os.getenv(
    "LOCAL_BACKUPS_DIR",
    r"C:\Users\shugs\OneDrive\Desktop\Cairn (W)\CAIRN_PDF_Testing_3.2025\CAIRN_B2_Upload_Test_4.21.25"
))

# B2
B2_KEY_ID  = os.getenv("B2_APP_KEY_ID")
B2_KEY     = os.getenv("B2_APP_KEY")
B2_BUCKET  = os.getenv("B2_BUCKET")
URL_TTL    = int(os.getenv("B2_URL_TTL", str(7 * 24 * 3600)))  # seconds
SYNC_DAYS  = int(os.getenv("SYNC_WINDOW_DAYS", "30"))
PAGE_SIZE  = int(os.getenv("LOAD_CHUNK", "100"))

# Sheet ↔ Supabase column mapping
COL_DOC_ID       = "Tag ID"
COL_FILE_ID      = "File ID"
COL_LOCAL_FNAME  = "Local Backup Name"
DATE_COLS        = {"published_date": "Published Date", "date_tagged": "Date Tagged"}
TAG_COLS         = [
    "Additional Keywords","Energy Resources","Customer Classes",
    "State/Region","Regulatory Body","Rate Impact","Utility Reform",
    "DERs","Physical Climate Risk","Quality Check",
]
MULTI_VALUE_TAGS = {"Additional Keywords","Energy Resources","Customer Classes"}
TAG_SPLITTER     = {c: ("," if c in MULTI_VALUE_TAGS else None) for c in TAG_COLS}

# ───────────────────────────────────────────────────────────────────────────────
# 2 · HELPERS
# ───────────────────────────────────────────────────────────────────────────────
_iso_now = lambda: datetime.now(timezone.utc).isoformat()

def _jsonable(v):
    """
    Convert any pandas NA/NaT/NaN to None, leave everything else alone.
    """
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    return v

def _clean(d: dict) -> dict:
    return {k: _jsonable(v) for k, v in d.items()}

def _parse_date(val) -> str | None:
    if val is None or str(val).strip().lower() in ("", "date", "when tagging was completed"):
        return None
    try:
        dt = pd.to_datetime(val).date()
        return None if pd.isna(dt) else dt.isoformat()
    except Exception:
        return None

def _split_tags(row: pd.Series) -> set[str]:
    tags: set[str] = set()
    for col in TAG_COLS:
        raw = str(row.get(col, "")).strip()
        if not raw:
            continue
        delim = TAG_SPLITTER[col]
        if delim:
            parts = [p.strip() for p in raw.split(delim) if p.strip()]
            tags.update(parts)
        else:
            tags.add(raw)
    return tags

# ───────────────────────────────────────────────────────────────────────────────
# 3 · CLIENT INITIALIZERS
# ───────────────────────────────────────────────────────────────────────────────
def init_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def init_gspread() -> gspread.Client:
    if not CREDS_FILE.exists():
        raise FileNotFoundError(f"Google creds not found: {CREDS_FILE}")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=scopes)
    return gspread.authorize(creds)

def init_b2() -> Bucket:
    info = InMemoryAccountInfo()
    api  = B2Api(info)
    api.authorize_account("production", B2_KEY_ID, B2_KEY)
    return api.get_bucket_by_name(B2_BUCKET)

# ───────────────────────────────────────────────────────────────────────────────
# 4 · SHEET → SUPABASE TAG SYNC
# ───────────────────────────────────────────────────────────────────────────────
def sync_sheet_tags(sb: Client, gs: gspread.Client):
    ws = gs.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    df = pd.DataFrame(ws.get_all_records()).replace(r"^\s*$", pd.NA, regex=True)
    df = df.dropna(subset=[COL_DOC_ID])
    df[COL_DOC_ID] = df[COL_DOC_ID].astype(str).str.strip()
    logging.info("Sheet rows to process: %d", len(df))

    # cache existing tags
    existing = sb.table("tags").select("id,tag_name").execute().data or []
    tag_cache = {t["tag_name"]: t["id"] for t in existing}

    for _, row in df.iterrows():
        doc_id = row[COL_DOC_ID]
        file_payload = {
            "document_id":       doc_id,
            "source_file_id":    _jsonable(row.get(COL_FILE_ID)),
            "local_backup_name": _jsonable(row.get(COL_LOCAL_FNAME)),
            "last_synced_at":    _iso_now(),
        }
        for db_col, hdr in DATE_COLS.items():
            file_payload[db_col] = _parse_date(row.get(hdr))
        file_payload = _clean(file_payload)

        resp = (
            sb.table("files")
              .upsert(file_payload, on_conflict="document_id", returning="representation")
              .execute()
        )
        file_pk = resp.data[0]["id"]

        # tags ↔ files
        tag_names = _split_tags(row)
        new = [ {"tag_name":t} for t in tag_names if t not in tag_cache ]
        if new:
            inserted = sb.table("tags").insert(new, returning="representation").execute().data
            tag_cache.update({t["tag_name"]: t["id"] for t in inserted})

        links = [{"file_id": file_pk, "tag_id": tag_cache[t]} for t in tag_names]
        if links:
            sb.table("file_tags").upsert(links, ignore_duplicates=True).execute()

    logging.info("✅ Sheet→Supabase tags synced")

# ───────────────────────────────────────────────────────────────────────────────
# 5 · FLATTEN TAGS INTO JSONB COLUMN
# ───────────────────────────────────────────────────────────────────────────────
def sync_tags_json(sb: Client):
    rows = sb.table("file_tags").select("file_id,tag_id").execute().data or []
    if not rows:
        return
    tags = sb.table("tags").select("id,tag_name").execute().data or []
    name_map = {t["id"]: t["tag_name"] for t in tags}

    from collections import defaultdict
    by_file: dict[int, list[str]] = defaultdict(list)
    for r in rows:
        by_file[r["file_id"]].append(name_map[r["tag_id"]])

    for file_id, tag_list in by_file.items():
        sb.table("files").update({"tags_json": tag_list}).eq("id", file_id).execute()

    logging.info("✅ tags_json populated on %d files", len(by_file))

# ───────────────────────────────────────────────────────────────────────────────
# 6 · SUPABASE → B2 SYNC
# ───────────────────────────────────────────────────────────────────────────────
def rows_for_b2(sb: Client) -> Iterable[dict]:
    cutoff = (datetime.utcnow() - timedelta(days=SYNC_DAYS)).isoformat()
    page = (sb.table("files")
              .select("*")
              .or_(f"b2_file_id.is.null,updated_at.gt.{cutoff}")
              .limit(PAGE_SIZE)
              .execute().data) or []
    while page:
        yield from page
        last = page[-1]["id"]
        page = (sb.table("files")
                  .select("*")
                  .gt("id", last)
                  .or_(f"b2_file_id.is.null,updated_at.gt.{cutoff}")
                  .limit(PAGE_SIZE)
                  .execute().data) or []

def find_local(file_id: str) -> Path | None:
    p = BACKUP_DIR / file_id
    if p.exists(): return p
    for ext in (".pdf", ".PDF"):
        q = p.with_suffix(ext)
        if q.exists(): return q
    matches = list(BACKUP_DIR.glob(f"{file_id}*"))
    return matches[0] if matches else None

def ensure_on_b2(bucket: Bucket, name: str, path: Path) -> str:
    try:
        return bucket.get_file_info_by_name(name).id_
    except:
        logging.info("Uploading %s …", name)
        bucket.upload(UploadSourceLocalFile(str(path)), file_name=name)
        time.sleep(1)
        return bucket.get_file_info_by_name(name).id_

def presign(bucket: Bucket, file_name: str) -> str:
    return bucket.get_download_url(filename=file_name)  # no more kwargs

def sync_files_b2(sb: Client, bucket: Bucket):
    for row in rows_for_b2(sb):
        pk  = row["id"]
        fid = row.get("source_file_id")
        if not fid:
            logging.warning("file %d missing source_file_id → skipping", pk)
            continue

        lp = find_local(fid)
        if not lp:
            logging.warning("no local file for %s → skipping", fid)
            continue

        b2id = row.get("b2_file_id") or ensure_on_b2(bucket, fid, lp)
        url  = presign(bucket, fid)

        sb.table("files").update({
            "b2_file_id":     b2id,
            "b2_temp_url":    url,
            "last_synced_at": _iso_now(),
        }).eq("id", pk).execute()

        logging.info("↺ %s (id %d) → B2 %s", fid, pk, b2id)

    logging.info("✅ Supabase→B2 sync complete")

# ───────────────────────────────────────────────────────────────────────────────
# 7 · ORCHESTRATION
# ───────────────────────────────────────────────────────────────────────────────
def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    sb     = init_supabase()
    gs     = init_gspread()
    bucket = init_b2()

    sync_sheet_tags(sb, gs)
    sync_tags_json(sb)
    sync_files_b2(sb, bucket)

if __name__ == "__main__":
    main()
