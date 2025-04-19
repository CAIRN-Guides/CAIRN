"""
sheet_to_supabase.py
───────────────────────────────────────────────────────────────────────────────
Sync a Google‑Sheet tagging worksheet into a three‑table Supabase schema:

  • files       – one row per document
  • tags        – one row per unique tag string
  • file_tags   – many‑to‑many link between the two

HOW TO RUN (30 sec):

  1.  pip install -r requirements.txt
  2.  cp .env.example .env          # then fill in the Supabase URL + service role key
  3.  drop your Google service‑account JSON next to this script
      (default name: cairn_google_creds.json)  …OR…
      set GOOGLE_CREDS_FILE=/path/to/key.json in .env
  4.  python sheet_to_supabase.py

Requires Python ≥ 3.10
"""

from __future__ import annotations
import os, logging
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from supabase import create_client, Client

# ════════════════════════════════════════════════════════════════════════════
# 1 · Load environment variables + constants
# ════════════════════════════════════════════════════════════════════════════
load_dotenv()  # reads .env in project root

# ── Supabase credentials ──
SUPABASE_URL = os.getenv("SUPABASE_URL")            # e.g. https://xxxx.supabase.co
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # **service‑role** key recommended

# ── Google service‑account JSON ──
# Priority: (1) .env   (2) file named cairn_google_creds.json alongside this script.
CREDS_FILE = os.getenv(
    "GOOGLE_CREDS_FILE",
    str(Path(__file__).with_name("cairn_google_creds.json"))
)

# ── Google‑Sheet location ──
SHEET_NAME     = "CAIRN_Labels_Gsheets_Input"   # change if your sheet is named differently
WORKSHEET_NAME = "Document_Tags"

# ── Identifier columns ──
DOC_ID_COL   = "Document ID"
FILENAME_COL = "Local Backup Name"

# ── Date columns stored on `files` (db_column : sheet header) ──
DATE_COLS = {
    "published_date": "Published Date",
    "date_tagged":    "Date Tagged",
}

# ── Tag columns (all strings become tags) ──
TAG_COLS = [
    "Additional Keywords",
    "Energy Resources",
    "Customer Classes",
    "State/Region",
    "Regulatory Body",
    "Rate Impact",
    "Utility Reform",
    "DERs",
    "Physical Climate Risk",
    "Quality Check",
]

MULTI_VALUE_TAGS = {"Additional Keywords", "Energy Resources", "Customer Classes"}

TAG_SPLITTER = {col: ("," if col in MULTI_VALUE_TAGS else None) for col in TAG_COLS}

# ════════════════════════════════════════════════════════════════════════════
# 2 · Helper functions
# ════════════════════════════════════════════════════════════════════════════
_iso_now = lambda: datetime.now(timezone.utc).isoformat()


def _split_tags(row: pd.Series) -> set[str]:
    """Return a set of cleaned tag strings for this sheet row."""
    tags: set[str] = set()
    for col in TAG_COLS:
        raw = str(row.get(col, "")).strip()
        if not raw:
            continue
        delim = TAG_SPLITTER.get(col)
        if delim:
            parts = [p.strip() for p in raw.split(delim) if p.strip()]
            tags.update(parts)
        else:
            tags.add(raw)
    return tags


def _parse_date(val) -> str | None:
    """Convert cell to YYYY‑MM‑DD or None (silences obvious placeholder rows)."""
    ignore = {"date", "when tagging was completed", ""}
    if val is None or str(val).strip().lower() in ignore:
        return None
    try:
        return pd.to_datetime(val).date().isoformat()
    except Exception:
        logging.debug("Date parse failed for value: %s", val)
        return None


# ════════════════════════════════════════════════════════════════════════════
# 3 · Initialise external clients
# ════════════════════════════════════════════════════════════════════════════
def init_supabase() -> Client:
    if not (SUPABASE_URL and SUPABASE_KEY):
        raise RuntimeError("Supabase creds missing in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def init_gspread() -> gspread.Client:
    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]
    if not Path(CREDS_FILE).exists():
        raise FileNotFoundError(
            f"Google creds not found → {CREDS_FILE}\n"
            "Drop the JSON key here or set GOOGLE_CREDS_FILE in .env"
        )
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)
    return gspread.authorize(creds)


# ════════════════════════════════════════════════════════════════════════════
# 4 · Core sync logic
# ════════════════════════════════════════════════════════════════════════════
def sync():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    supabase = init_supabase()
    gs       = init_gspread()

    # 4.1 Pull sheet into DataFrame
    ws = gs.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    df = pd.DataFrame(ws.get_all_records())
    df = df.dropna(subset=[DOC_ID_COL])                      # skip completely empty rows
    df[DOC_ID_COL] = df[DOC_ID_COL].astype(str).str.strip()

    # Remove the helper description row (Published Date == "Date")
    if "Published Date" in df.columns:
        df = df[df["Published Date"].str.strip().ne("Date")]

    logging.info("Rows to process: %s", len(df))

    # 4.2 Cache existing tags
    tag_rows = supabase.table("tags").select("id", "tag_name").execute().data or []
    tag_cache: dict[str, int] = {t["tag_name"]: t["id"] for t in tag_rows}

    # 4.3 Main loop
    for _, row in df.iterrows():
        doc_id = row[DOC_ID_COL]

        # file payload
        file_payload = {
            "document_id":       doc_id,
            "local_backup_name": row.get(FILENAME_COL),
            "last_synced_at":    _iso_now(),
        }
        for db_col, header in DATE_COLS.items():
            file_payload[db_col] = _parse_date(row.get(header))

        file_resp = supabase.table("files").upsert(
            file_payload,
            on_conflict="document_id",
            returning="representation",
        ).execute()
        file_id = file_resp.data[0]["id"]

        # tag handling
        tag_names = _split_tags(row)
        new_tags  = [{"tag_name": t} for t in tag_names if t not in tag_cache]
        if new_tags:
            inserted = supabase.table("tags").insert(
                new_tags, returning="representation"
            ).execute().data
            tag_cache.update({t["tag_name"]: t["id"] for t in inserted})

        link_rows = [
            {"file_id": file_id, "tag_id": tag_cache[t]}
            for t in tag_names
        ]
        if link_rows:
            supabase.table("file_tags").upsert(
                link_rows,
                ignore_duplicates=True,
                returning="minimal",
            ).execute()

    logging.info("✓ Sync complete")


# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        sync()
    except Exception as exc:
        logging.error("❌ Sync failed: %s", exc)
        raise
