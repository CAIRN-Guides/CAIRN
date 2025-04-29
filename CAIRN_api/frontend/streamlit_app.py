# app.py

import os
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# ─── Load env & page setup ─────────────────────────────────────────────────────
load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000/documents")

st.set_page_config(page_title="CAIRN Finder", layout="wide")
st.title("📚 CAIRN Document Finder")

# ─── Sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.header("Filters")
params = {}

# text inputs
text_cols = [
    "document_id", "document_title", "local_backup_name", "tagger",
    "file_format", "rate_impact", "quality_check", "regulatory_body",
    "state_region", "docket_number", "document_type", "org_utility_name",
    "parent_document", "replaces_document", "document_url", "cairn_url",
    "processing_notes"
]
for col in text_cols:
    v = st.sidebar.text_input(col.replace("_"," ").title())
    if v:
        params[col] = v

# date inputs
if d := st.sidebar.date_input("Published Date", value=None):
    params["published_date"] = d.isoformat()
if d := st.sidebar.date_input("Date Tagged", value=None):
    params["date_tagged"] = d.isoformat()
if d := st.sidebar.date_input("Last Synced At", value=None):
    params["last_synced_at"] = d.isoformat()
if d := st.sidebar.date_input("Updated At", value=None):
    params["updated_at"] = d.isoformat()

# list inputs
list_cols = [
    "additional_keywords", "ders", "utility_reform",
    "customer_classes", "energy_resources",
    "related_documents", "relationship_types"
]
for col in list_cols:
    s = st.sidebar.text_input(col.replace("_"," ").title() + " (comma-separated)")
    if s:
        params[col] = [x.strip() for x in s.split(",") if x.strip()]

# boolean
if st.sidebar.checkbox("Physical Climate Risk"):
    params["physical_climate_risk"] = True

# pagination & options
st.sidebar.header("Options")
params["page"]      = st.sidebar.number_input("Page Number", min_value=1, value=1)
params["page_size"] = st.sidebar.number_input("Page Size",   min_value=1, max_value=200, value=20)
params["include_download_url"] = st.sidebar.checkbox("Include Download URL", value=False)

# ─── Fetch & display ───────────────────────────────────────────────────────────
if st.sidebar.button("Load Documents"):
    resp = requests.get(API_URL, params=params)
    if resp.status_code != 200:
        st.error(f"API Error {resp.status_code}: {resp.text}")
        st.stop()

    docs = resp.json().get("data", [])
    st.write(f"Showing **{len(docs)}** documents (Page {params['page']})")
    if not docs:
        st.info("No documents found.")
        st.stop()

    # ─── Build DataFrame & flatten list columns ───────────────────────────────
    df = pd.DataFrame(docs)
    for lc in list_cols:
        if lc in df.columns:
            df[lc] = df[lc].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)

    # ─── Reorder & rename columns to match your exact headlines ───────────────
    cols_order = [
        "document_id", "local_backup_name", "tag_id", "document_title",
        "published_date", "document_author", "org_utility_name",
        "docket_number", "document_type", "document_subtype",
        "document_url", "cairn_url", "rate_impact", "utility_reform",
        "energy_resources", "customer_classes", "ders",
        "physical_climate_risk", "additional_keywords", "tagger",
        "date_tagged", "quality_check", "processing_notes",
        "state_region", "regulatory_body", "jurisdiction_type",
        "parent_document", "related_documents", "replaces_document",
        "relationship_types"
    ]
    df = df.reindex(columns=cols_order)

    rename_map = {
        "document_id":           "File ID",
        "local_backup_name":     "Local Backup Name",
        "tag_id":                "Tag ID",
        "document_title":        "Document Title",
        "published_date":        "Published Date",
        "document_author":       "Document Author",
        "org_utility_name":      "Org/Utility Name",
        "docket_number":         "Docket Number",
        "document_type":         "Document Type",
        "document_subtype":      "Document Subtype",
        "document_url":          "Document URL",
        "cairn_url":             "cairn_url",
        "rate_impact":           "Rate Impact",
        "utility_reform":        "Utility Reform",
        "energy_resources":      "Energy Resources",
        "customer_classes":      "Customer Classes",
        "ders":                  "DERs",
        "physical_climate_risk": "Physical Climate Risk",
        "additional_keywords":   "Additional Keywords",
        "tagger":                "Tagger",
        "date_tagged":           "Date Tagged",
        "quality_check":         "Quality Check",
        "processing_notes":      "Processing Notes",
        "state_region":          "State/Region",
        "regulatory_body":       "Regulatory Body",
        "jurisdiction_type":     "Jurisdiction Type",
        "parent_document":       "Parent Document",
        "related_documents":     "Related Documents",
        "replaces_document":     "Replaces Document",
        "relationship_types":    "Relationship Types",
    }
    df.rename(columns=rename_map, inplace=True)

    # ─── Quick-search across all fields ───────────────────────────────────────
    search = st.text_input("🔎 Quick Search all fields")
    if search:
        mask = df.apply(lambda row: row.astype(str)
                                  .str.contains(search, case=False, na=False)
                                  .any(), axis=1)
        df = df[mask]

    # ─── Configure AgGrid ────────────────────────────────────────────────────
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        filter="agTextColumnFilter",
        sortable=True,
        resizable=True,
        wrapText=True,
        autoHeight=True,
        minWidth=150
    )
    gb.configure_side_bar()  # adds filter/sorting panel & column chooser
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)
    gb.configure_selection(selection_mode="multiple", use_checkbox=True)
    grid_opts = gb.build()

    grid_response = AgGrid(
        df,
        gridOptions=grid_opts,
        enable_enterprise_modules=False,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=False,
        height=500,
    )

    # ─── Download current view as CSV ────────────────────────────────────────
    out_df = pd.DataFrame(grid_response["data"])
    csv = out_df.to_csv(index=False)
    st.download_button(
        "⬇️ Download current view as CSV",
        data=csv,
        file_name="cairn_documents.csv",
        mime="text/csv"
    )

    # ─── Detail pane for selected rows ───────────────────────────────────────
    selected = grid_response["selected_rows"]
    if selected:
        sel_df = pd.DataFrame(selected).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
        st.markdown("### 📄 Selected Documents")
        st.dataframe(sel_df, use_container_width=True)
