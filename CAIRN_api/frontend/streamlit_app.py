import os
import streamlit as st
import requests
from dotenv import load_dotenv

# ─── Load .env ──────────────────────────────────────────────────────────────────
load_dotenv()  # expects frontend/.env
API_URL = os.getenv("API_URL", "http://localhost:8000/documents")

st.set_page_config(page_title="CAIRN Finder", layout="wide")
st.title("📚 CAIRN Document Finder")

# ─── Sidebar: one input per column ──────────────────────────────────────────────
st.sidebar.header("Filters")

# Text inputs
text_cols = [
    "document_id", "document_title", "local_backup_name", "tagger",
    "file_format", "rate_impact", "quality_check", "regulatory_body",
    "state_region", "docket_number", "document_type", "org_utility_name",
    "parent_document", "replaces_document", "document_url", "cairn_url",
    "processing_notes"
]
params = {}
for col in text_cols:
    val = st.sidebar.text_input(col.replace("_", " ").title())
    if val:
        params[col] = val

# Date inputs
if pub := st.sidebar.date_input("Published Date", value=None):
    params["published_date"] = pub.isoformat()
if dt := st.sidebar.date_input("Date Tagged", value=None):
    params["date_tagged"] = dt.isoformat()
if ls := st.sidebar.date_input("Last Synced At", value=None):
    params["last_synced_at"] = ls.isoformat()
if up := st.sidebar.date_input("Updated At", value=None):
    params["updated_at"] = up.isoformat()

# Array/list inputs (comma-separated)
list_cols = [
    "additional_keywords", "ders", "utility_reform",
    "customer_classes", "energy_resources",
    "related_documents", "relationship_types"
]
for col in list_cols:
    s = st.sidebar.text_input(col.replace("_", " ").title() + " (comma-separated)")
    if s:
        params[col] = [x.strip() for x in s.split(",") if x.strip()]

# Boolean
if st.sidebar.checkbox("Physical Climate Risk"):
    params["physical_climate_risk"] = True

# Pagination & URL toggle
st.sidebar.header("Options")
params["page"] = st.sidebar.number_input("Page Number", min_value=1, value=1)
params["page_size"] = st.sidebar.number_input("Page Size", min_value=1, max_value=200, value=20)
params["include_download_url"] = st.sidebar.checkbox("Include Download URL", value=False)

# ─── Fetch & display ───────────────────────────────────────────────────────────
if st.sidebar.button("Load Documents"):
    resp = requests.get(API_URL, params=params)
    if resp.status_code != 200:
        st.error(f"API Error {resp.status_code}: {resp.text}")
    else:
        docs = resp.json().get("data", [])
        st.write(f"Showing **{len(docs)}** documents (Page {params['page']})")
        for d in docs:
            st.markdown("---")
            st.subheader(d.get("document_title") or d.get("document_id"))
            for k, v in d.items():
                st.write(f"**{k}**: {v}")
        st.markdown("---")
