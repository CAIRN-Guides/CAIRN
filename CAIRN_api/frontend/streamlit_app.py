# frontend/streamlit_app.py
# Full drop-in replacement code - v1.11.1 (Fix DataFrame truth‑value bug)

import os
import io
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv
from PIL import Image  # Keep if used elsewhere
from datetime import date  # Added for date conversion check
import traceback  # For logging detailed errors if needed

# Make sure AgGrid is installed: pip install streamlit-aggrid
try:
    from st_aggrid.shared import JsCode
except ImportError:
    try:
        from st_aggrid.grid_options_builder import JsCode
    except ImportError:
        st.error("Could not import JsCode from streamlit‑aggrid. Please ensure streamlit‑aggrid is installed correctly.")
        st.stop()

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, ColumnsAutoSizeMode

# --- Constants ---
BASIC_COLUMNS_TO_SHOW = ["File ID", "Document Title", "Org/Utility Name", "Document Type", "Published Date"]
API_TIMEOUT_SECONDS = 45  # Timeout for search requests
DOWNLOAD_API_TIMEOUT_SECONDS = 30  # Timeout for single-download link generation

# ─── Load Environment Variables & Page Setup ──────────────────────────────────
load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000")
AUTH_HEADERS = {}
if 'user_token' in st.session_state:
    AUTH_HEADERS = {"Authorization": f"Bearer {st.session_state['user_token']}"}

st.set_page_config(page_title="CAIRN Finder", layout="wide")

# --- Helper Functions ---

def handle_single_download(doc_pk_id, doc_title, tab_prefix):
    if not doc_pk_id or str(doc_pk_id).strip() == "":
        st.warning(f"Cannot generate download link: missing document ID (PK_ID={doc_pk_id}).")
        return

    button_label = f"⬇️ Download: {doc_title[:40]}..."
    button_key = f"download_single_{tab_prefix}_{doc_pk_id}"
    link_key = f"download_link_{tab_prefix}_{doc_pk_id}"

    if link_key in st.session_state:
        info = st.session_state[link_key]
        url = info.get("url")
        filename = info.get("filename")
        if url:
            filename_attr = f'download="{filename}"' if filename else "download"
            st.markdown(
                f'✅ Link ready: <a href="{url}" target="_blank" {filename_attr}>Click to download "{doc_title[:50]}..."</a>',
                unsafe_allow_html=True
            )
        del st.session_state[link_key]

    if st.button(button_label, key=button_key):
        if link_key in st.session_state:
            del st.session_state[link_key]
        endpoint = f"{API_URL}/documents/{doc_pk_id}/download-url"
        try:
            with st.spinner(f"Generating link for '{doc_title[:30]}...'"):
                resp = requests.get(endpoint, headers=AUTH_HEADERS, timeout=DOWNLOAD_API_TIMEOUT_SECONDS)
                resp.raise_for_status()
                data = resp.json()
                url = data.get("url")
                filename = data.get("filename")
                if url:
                    st.session_state[link_key] = {"url": url, "filename": filename}
                    st.rerun()
                else:
                    st.error("API did not return a valid download link.")
                    st.session_state.pop(link_key, None)
        except Exception as e:
            st.error(f"Download Link Failed: {e}")
            st.session_state.pop(link_key, None)

def handle_batch_download(doc_pk_ids, tab_prefix):
    if not doc_pk_ids:
        st.warning("No documents selected for batch download.")
        return

    button_key = f"batch_download_btn_{tab_prefix}"
    link_key = f"batch_download_link_{tab_prefix}"

    if link_key in st.session_state:
        info = st.session_state[link_key]
        st.download_button(
            label="⬇️ Click here to save ZIP",
            data=info["data"],
            file_name=info["filename"],
            mime="application/zip",
            key=button_key + "_dl"
        )
        del st.session_state[link_key]
        return

    if st.button(f"⬇️ Download {len(doc_pk_ids)} as ZIP", key=button_key):
        try:
            with st.spinner("Building ZIP…"):
                resp = requests.post(
                    f"{API_URL}/documents/download-zip",
                    json={"doc_ids": doc_pk_ids},
                    headers=AUTH_HEADERS,
                    timeout=60
                )
                resp.raise_for_status()
                content = resp.content
                st.session_state[link_key] = {
                    "data": content,
                    "filename": f"cairn_{tab_prefix}_selected.zip"
                }
                st.rerun()
        except Exception as e:
            st.error(f"Batch ZIP download failed: {e}")

# ─── Header Display ───────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 6])
with col1:
    try:
        st.image(
            "https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/"
            "CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp",
            width=60
        )
    except:
        st.caption("CAIRN Logo")
with col2:
    st.title("CAIRN Document Finder")

# ─── Sidebar Filters Setup ───────────────────────────────────────────────────
st.sidebar.header("Filters")
params = {}

# Text input filters
text_cols = [
    "document_id", "document_title", "local_backup_name", "tagger", "file_format",
    "rate_impact", "quality_check", "regulatory_body", "state_region", "docket_number",
    "document_type", "org_utility_name", "parent_document", "replaces_document",
    "document_url", "cairn_url", "processing_notes"
]
for col in text_cols:
    key = f"filter_{col}"
    st.session_state.setdefault(key, "")
    val = st.sidebar.text_input(col.replace("_", " ").title(), value=st.session_state[key], key=f"input_{col}")
    st.session_state[key] = val
    if val:
        params[col] = val

# Date filters
date_fields = ["published_date", "date_tagged", "last_synced_at", "updated_at"]
for col in date_fields:
    key = f"filter_{col}"
    st.session_state.setdefault(key, None)
    current_val = None
    if st.session_state[key]:
        try:
            current_val = date.fromisoformat(st.session_state[key])
        except:
            pass
    d = st.sidebar.date_input(col.replace("_", " ").title(), value=current_val, key=f"input_{col}")
    if d:
        params[col] = d.isoformat()
        st.session_state[key] = d.isoformat()
    else:
        st.session_state[key] = None

# List filters
list_cols = [
    "additional_keywords", "ders", "utility_reform", "customer_classes",
    "energy_resources", "related_documents", "relationship_types"
]
for col in list_cols:
    key = f"filter_{col}"
    st.session_state.setdefault(key, "")
    raw = st.sidebar.text_input(
        col.replace("_", " ").title() + " (comma‑sep)",
        value=st.session_state[key],
        key=f"input_{col}"
    )
    st.session_state[key] = raw
    if raw:
        params[col] = [x.strip() for x in raw.split(",") if x.strip()]

# Boolean filter
st.session_state.setdefault("filter_physical_climate_risk", False)
phy = st.sidebar.checkbox("Physical Climate Risk", value=st.session_state["filter_physical_climate_risk"], key="input_physical_climate_risk")
st.session_state["filter_physical_climate_risk"] = phy
if phy:
    params["physical_climate_risk"] = True

# Pagination
st.sidebar.header("Options")
st.session_state.setdefault("page", 1)
st.session_state.setdefault("page_size", 20)
st.session_state.page = st.sidebar.number_input("Page Number", min_value=1, value=st.session_state.page, key="input_page")
st.session_state.page_size = st.sidebar.number_input("Page Size", min_value=1, max_value=200, value=st.session_state.page_size, key="input_page_size")
params["page"], params["page_size"] = st.session_state.page, st.session_state.page_size

load_button_pressed = st.sidebar.button("Load Documents", type="primary")

# ─── Main Area with Tabs ───────────────────────────────────────────────────────
about_tab, basic_tab, advanced_tab, tags_tab = st.tabs([
    "ℹ️ About CAIRN",
    "🔍 Search (Basic)",
    "🔬 Search (Advanced)",
    "🏷️ Tag Definitions"
])

# ─── Data Loading Logic ────────────────────────────────────────────────────────
if load_button_pressed:
    with st.spinner('Fetching documents from CAIRN API...'):
        try:
            resp = requests.get(
                f"{API_URL}/documents",
                params=params,
                headers=AUTH_HEADERS,
                timeout=API_TIMEOUT_SECONDS
            )
            resp.raise_for_status()
            payload = resp.json()
            docs = payload.get("data", [])
            st.session_state.total_docs = payload.get("total_count", len(docs))
            st.session_state.current_page_for_display = params.get("page", 1)
            page_size = params.get("page_size", 20)
            st.session_state.total_pages = (
                (st.session_state.total_docs + page_size - 1) // page_size
                if st.session_state.total_docs > 0 else 1
            )

            if not docs:
                st.session_state.search_results_df = pd.DataFrame()
                st.session_state.api_error = None
                st.session_state.data_message = "No documents found matching your criteria."
            else:
                df = pd.DataFrame(docs)
                if 'id' not in df.columns:
                    st.session_state.search_results_df = pd.DataFrame()
                    st.session_state.api_error = "Critical Error: 'id' column missing from API response."
                    st.error(st.session_state.api_error)
                else:
                    # flatten list fields
                    for lc in list_cols:
                        if lc in df.columns:
                            df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)
                    # rename columns
                    rename_map = {
                        "id": "PK_ID", "document_id": "File ID", "local_backup_name": "Local Backup Name",
                        "document_title": "Document Title", "published_date": "Published Date",
                        "org_utility_name": "Org/Utility Name", "docket_number": "Docket Number",
                        "document_type": "Document Type", "document_subtype": "Document Subtype",
                        "document_url": "Document URL", "cairn_url": "CAIRN URL",
                        "rate_impact": "Rate Impact", "utility_reform": "Utility Reform",
                        "energy_resources": "Energy Resources", "customer_classes": "Customer Classes",
                        "ders": "DERs", "physical_climate_risk": "Physical Climate Risk",
                        "additional_keywords": "Additional Keywords", "tagger": "Tagger",
                        "date_tagged": "Date Tagged", "quality_check": "Quality Check",
                        "processing_notes": "Processing Notes", "state_region": "State/Region",
                        "regulatory_body": "Regulatory Body", "jurisdiction_type": "Jurisdiction Type",
                        "parent_document": "Parent Document", "related_documents": "Related Documents",
                        "replaces_document": "Replaces Document", "relationship_types": "Relationship Types",
                        "document_author": "Document Author", "source_file_id": "source_file_id",
                        "b2_file_id": "b2_file_id"
                    }
                    cols = [c for c in rename_map if c in df.columns]
                    df = df[cols].rename(columns=rename_map)
                    if 'PK_ID' not in df.columns or df['PK_ID'].isnull().any():
                        st.session_state.search_results_df = pd.DataFrame()
                        st.session_state.api_error = "Critical Error: PK_ID issue in processed data."
                        st.error(st.session_state.api_error)
                    else:
                        df['PK_ID'] = df['PK_ID'].astype(str)
                        st.session_state.search_results_df = df
                        st.session_state.api_error = None
                        st.session_state.data_message = None

        except Exception as e:
            st.session_state.search_results_df = pd.DataFrame()
            st.session_state.api_error = f"API Request Failed: {e}"
            st.session_state.data_message = None

# ─── About Tab ────────────────────────────────────────────────────────────────
with about_tab:
    st.markdown("""
    ## What is CAIRN?
    ... [About content here] ...
    """)

# ─── Basic Search Tab ─────────────────────────────────────────────────────────
with basic_tab:
    st.info("Basic search view. Use sidebar filters and click 'Load Documents'.")
    if st.session_state.get('api_error'):
        st.error(st.session_state.api_error)
    if st.session_state.get('data_message'):
        st.warning(st.session_state.data_message)

    df_basic = st.session_state.search_results_df if 'search_results_df' in st.session_state else pd.DataFrame()
    if not df_basic.empty:
        st.write(
            f"Showing **{len(df_basic)}** of **{st.session_state.total_docs}** documents "
            f"(Page {st.session_state.current_page_for_display} of {st.session_state.total_pages})"
        )
        display_cols = ["PK_ID"] + BASIC_COLUMNS_TO_SHOW
        display_cols = [c for c in display_cols if c in df_basic.columns]
        df_view = df_basic[display_cols].copy()

        term = st.text_input("🔎 Quick Search basic results", key="quick_search_input_basic")
        if term:
            mask = df_view.apply(
                lambda r: r.astype(str).str.contains(term, case=False, na=False).any(),
                axis=1
            )
            df_view = df_view[mask]
            st.write(f"Showing {len(df_view)} rows matching quick search.")

        if df_view.empty:
            st.caption("No rows to display.")
        else:
            df_view['PK_ID'] = df_view['PK_ID'].astype(str)
            gb = GridOptionsBuilder.from_dataframe(df_view)
            gb.configure_default_column(
                sortable=True, resizable=True, wrapText=True, autoHeight=True,
                minWidth=150, filter=True, floatingFilter=True
            )
            gb.configure_column("PK_ID", hide=True)
            gb.configure_column("Document Title", minWidth=300)
            gb.configure_column("Org/Utility Name", minWidth=200)
            gb.configure_side_bar(filters_panel=False, columns_panel=True)
            gb.configure_pagination(
                paginationAutoPageSize=False,
                paginationPageSize=st.session_state.page_size
            )
            gb.configure_selection(
                selection_mode="multiple",
                use_checkbox=True,
                header_checkbox=True
            )
            opts = gb.build()

            grid = AgGrid(
                df_view,
                gridOptions=opts,
                key='grid_basic',
                height=600, width='100%',
                columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
                update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                allow_unsafe_jscode=True,
                enable_enterprise_modules=False
            )

            selected = grid.get("selected_rows") or []
            _data = grid.get("data")
            displayed = _data if _data is not None else pd.DataFrame()

            st.markdown("---")
            csv_bytes = displayed.to_csv(index=False).encode('utf-8') if not displayed.empty else b""
            st.download_button(
                label="📄 Download Basic View as CSV",
                data=csv_bytes,
                file_name="cairn_basic_export.csv",
                mime="text/csv",
                disabled=displayed.empty,
                key="csv_basic"
            )
            st.markdown("---")

            col1, col2 = st.columns([1, 3])
            with col1:
                if len(selected) == 1:
                    row = selected[0]
                    handle_single_download(row.get("PK_ID"), row.get("Document Title"), "basic")
                elif len(selected) > 1:
                    ids = [int(r.get("PK_ID")) for r in selected]
                    handle_batch_download(ids, "basic")
                else:
                    st.caption("Select one or more rows to enable download.")
            with col2:
                if selected:
                    sel_df = pd.DataFrame(selected).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                    st.dataframe(
                        sel_df if len(sel_df) > 1 else sel_df.iloc[0],
                        use_container_width=True,
                        height=200
                    )

# frontend/streamlit_app.py
# Full drop-in replacement code - v1.11.1 (Fix DataFrame truth‑value bug)

import os
import io
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv
from PIL import Image  # Keep if used elsewhere
from datetime import date  # Added for date conversion check
import traceback  # For logging detailed errors if needed

# Make sure AgGrid is installed: pip install streamlit-aggrid
try:
    from st_aggrid.shared import JsCode
except ImportError:
    try:
        from st_aggrid.grid_options_builder import JsCode
    except ImportError:
        st.error("Could not import JsCode from streamlit‑aggrid. Please ensure streamlit‑aggrid is installed correctly.")
        st.stop()

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, ColumnsAutoSizeMode

# --- Constants ---
BASIC_COLUMNS_TO_SHOW = ["File ID", "Document Title", "Org/Utility Name", "Document Type", "Published Date"]
API_TIMEOUT_SECONDS = 45  # Timeout for search requests
DOWNLOAD_API_TIMEOUT_SECONDS = 30  # Timeout for single-download link generation

# ─── Load Environment Variables & Page Setup ──────────────────────────────────
load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000")
AUTH_HEADERS = {}
if 'user_token' in st.session_state:
    AUTH_HEADERS = {"Authorization": f"Bearer {st.session_state['user_token']}"}

st.set_page_config(page_title="CAIRN Finder", layout="wide")

# --- Helper Functions ---

def handle_single_download(doc_pk_id, doc_title, tab_prefix):
    if not doc_pk_id or str(doc_pk_id).strip() == "":
        st.warning(f"Cannot generate download link: missing document ID (PK_ID={doc_pk_id}).")
        return

    button_label = f"⬇️ Download: {doc_title[:40]}..."
    button_key = f"download_single_{tab_prefix}_{doc_pk_id}"
    link_key = f"download_link_{tab_prefix}_{doc_pk_id}"

    if link_key in st.session_state:
        info = st.session_state[link_key]
        url = info.get("url")
        filename = info.get("filename")
        if url:
            filename_attr = f'download="{filename}"' if filename else "download"
            st.markdown(
                f'✅ Link ready: <a href="{url}" target="_blank" {filename_attr}>Click to download "{doc_title[:50]}..."</a>',
                unsafe_allow_html=True
            )
        del st.session_state[link_key]

    if st.button(button_label, key=button_key):
        if link_key in st.session_state:
            del st.session_state[link_key]
        endpoint = f"{API_URL}/documents/{doc_pk_id}/download-url"
        try:
            with st.spinner(f"Generating link for '{doc_title[:30]}...'"):
                resp = requests.get(endpoint, headers=AUTH_HEADERS, timeout=DOWNLOAD_API_TIMEOUT_SECONDS)
                resp.raise_for_status()
                data = resp.json()
                url = data.get("url")
                filename = data.get("filename")
                if url:
                    st.session_state[link_key] = {"url": url, "filename": filename}
                    st.rerun()
                else:
                    st.error("API did not return a valid download link.")
                    st.session_state.pop(link_key, None)
        except Exception as e:
            st.error(f"Download Link Failed: {e}")
            st.session_state.pop(link_key, None)

def handle_batch_download(doc_pk_ids, tab_prefix):
    if not doc_pk_ids:
        st.warning("No documents selected for batch download.")
        return

    button_key = f"batch_download_btn_{tab_prefix}"
    link_key = f"batch_download_link_{tab_prefix}"

    if link_key in st.session_state:
        info = st.session_state[link_key]
        st.download_button(
            label="⬇️ Click here to save ZIP",
            data=info["data"],
            file_name=info["filename"],
            mime="application/zip",
            key=button_key + "_dl"
        )
        del st.session_state[link_key]
        return

    if st.button(f"⬇️ Download {len(doc_pk_ids)} as ZIP", key=button_key):
        try:
            with st.spinner("Building ZIP…"):
                resp = requests.post(
                    f"{API_URL}/documents/download-zip",
                    json={"doc_ids": doc_pk_ids},
                    headers=AUTH_HEADERS,
                    timeout=60
                )
                resp.raise_for_status()
                content = resp.content
                st.session_state[link_key] = {
                    "data": content,
                    "filename": f"cairn_{tab_prefix}_selected.zip"
                }
                st.rerun()
        except Exception as e:
            st.error(f"Batch ZIP download failed: {e}")

# ─── Header Display ───────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 6])
with col1:
    try:
        st.image(
            "https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/"
            "CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp",
            width=60
        )
    except:
        st.caption("CAIRN Logo")
with col2:
    st.title("CAIRN Document Finder")

# ─── Sidebar Filters Setup ───────────────────────────────────────────────────
st.sidebar.header("Filters")
params = {}

# Text input filters
text_cols = [
    "document_id", "document_title", "local_backup_name", "tagger", "file_format",
    "rate_impact", "quality_check", "regulatory_body", "state_region", "docket_number",
    "document_type", "org_utility_name", "parent_document", "replaces_document",
    "document_url", "cairn_url", "processing_notes"
]
for col in text_cols:
    key = f"filter_{col}"
    st.session_state.setdefault(key, "")
    val = st.sidebar.text_input(col.replace("_", " ").title(), value=st.session_state[key], key=f"input_{col}")
    st.session_state[key] = val
    if val:
        params[col] = val

# Date filters
date_fields = ["published_date", "date_tagged", "last_synced_at", "updated_at"]
for col in date_fields:
    key = f"filter_{col}"
    st.session_state.setdefault(key, None)
    current_val = None
    if st.session_state[key]:
        try:
            current_val = date.fromisoformat(st.session_state[key])
        except:
            pass
    d = st.sidebar.date_input(col.replace("_", " ").title(), value=current_val, key=f"input_{col}")
    if d:
        params[col] = d.isoformat()
        st.session_state[key] = d.isoformat()
    else:
        st.session_state[key] = None

# List filters
list_cols = [
    "additional_keywords", "ders", "utility_reform", "customer_classes",
    "energy_resources", "related_documents", "relationship_types"
]
for col in list_cols:
    key = f"filter_{col}"
    st.session_state.setdefault(key, "")
    raw = st.sidebar.text_input(
        col.replace("_", " ").title() + " (comma‑sep)",
        value=st.session_state[key],
        key=f"input_{col}"
    )
    st.session_state[key] = raw
    if raw:
        params[col] = [x.strip() for x in raw.split(",") if x.strip()]

# Boolean filter
st.session_state.setdefault("filter_physical_climate_risk", False)
phy = st.sidebar.checkbox("Physical Climate Risk", value=st.session_state["filter_physical_climate_risk"], key="input_physical_climate_risk")
st.session_state["filter_physical_climate_risk"] = phy
if phy:
    params["physical_climate_risk"] = True

# Pagination
st.sidebar.header("Options")
st.session_state.setdefault("page", 1)
st.session_state.setdefault("page_size", 20)
st.session_state.page = st.sidebar.number_input("Page Number", min_value=1, value=st.session_state.page, key="input_page")
st.session_state.page_size = st.sidebar.number_input("Page Size", min_value=1, max_value=200, value=st.session_state.page_size, key="input_page_size")
params["page"], params["page_size"] = st.session_state.page, st.session_state.page_size

load_button_pressed = st.sidebar.button("Load Documents", type="primary")

# ─── Main Area with Tabs ───────────────────────────────────────────────────────
about_tab, basic_tab, advanced_tab, tags_tab = st.tabs([
    "ℹ️ About CAIRN",
    "🔍 Search (Basic)",
    "🔬 Search (Advanced)",
    "🏷️ Tag Definitions"
])

# ─── Data Loading Logic ────────────────────────────────────────────────────────
if load_button_pressed:
    with st.spinner('Fetching documents from CAIRN API...'):
        try:
            resp = requests.get(
                f"{API_URL}/documents",
                params=params,
                headers=AUTH_HEADERS,
                timeout=API_TIMEOUT_SECONDS
            )
            resp.raise_for_status()
            payload = resp.json()
            docs = payload.get("data", [])
            st.session_state.total_docs = payload.get("total_count", len(docs))
            st.session_state.current_page_for_display = params.get("page", 1)
            page_size = params.get("page_size", 20)
            st.session_state.total_pages = (
                (st.session_state.total_docs + page_size - 1) // page_size
                if st.session_state.total_docs > 0 else 1
            )

            if not docs:
                st.session_state.search_results_df = pd.DataFrame()
                st.session_state.api_error = None
                st.session_state.data_message = "No documents found matching your criteria."
            else:
                df = pd.DataFrame(docs)
                if 'id' not in df.columns:
                    st.session_state.search_results_df = pd.DataFrame()
                    st.session_state.api_error = "Critical Error: 'id' column missing from API response."
                    st.error(st.session_state.api_error)
                else:
                    # flatten list fields
                    for lc in list_cols:
                        if lc in df.columns:
                            df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)
                    # rename columns
                    rename_map = {
                        "id": "PK_ID", "document_id": "File ID", "local_backup_name": "Local Backup Name",
                        "document_title": "Document Title", "published_date": "Published Date",
                        "org_utility_name": "Org/Utility Name", "docket_number": "Docket Number",
                        "document_type": "Document Type", "document_subtype": "Document Subtype",
                        "document_url": "Document URL", "cairn_url": "CAIRN URL",
                        "rate_impact": "Rate Impact", "utility_reform": "Utility Reform",
                        "energy_resources": "Energy Resources", "customer_classes": "Customer Classes",
                        "ders": "DERs", "physical_climate_risk": "Physical Climate Risk",
                        "additional_keywords": "Additional Keywords", "tagger": "Tagger",
                        "date_tagged": "Date Tagged", "quality_check": "Quality Check",
                        "processing_notes": "Processing Notes", "state_region": "State/Region",
                        "regulatory_body": "Regulatory Body", "jurisdiction_type": "Jurisdiction Type",
                        "parent_document": "Parent Document", "related_documents": "Related Documents",
                        "replaces_document": "Replaces Document", "relationship_types": "Relationship Types",
                        "document_author": "Document Author", "source_file_id": "source_file_id",
                        "b2_file_id": "b2_file_id"
                    }
                    cols = [c for c in rename_map if c in df.columns]
                    df = df[cols].rename(columns=rename_map)
                    if 'PK_ID' not in df.columns or df['PK_ID'].isnull().any():
                        st.session_state.search_results_df = pd.DataFrame()
                        st.session_state.api_error = "Critical Error: PK_ID issue in processed data."
                        st.error(st.session_state.api_error)
                    else:
                        df['PK_ID'] = df['PK_ID'].astype(str)
                        st.session_state.search_results_df = df
                        st.session_state.api_error = None
                        st.session_state.data_message = None

        except Exception as e:
            st.session_state.search_results_df = pd.DataFrame()
            st.session_state.api_error = f"API Request Failed: {e}"
            st.session_state.data_message = None

# ─── About Tab ────────────────────────────────────────────────────────────────
with about_tab:
    st.markdown("""
    ## What is CAIRN?
    ... [About content here] ...
    """)

# ─── Basic Search Tab ─────────────────────────────────────────────────────────
with basic_tab:
    st.info("Basic search view. Use sidebar filters and click 'Load Documents'.")
    if st.session_state.get('api_error'):
        st.error(st.session_state.api_error)
    if st.session_state.get('data_message'):
        st.warning(st.session_state.data_message)

    df_basic = st.session_state.search_results_df if 'search_results_df' in st.session_state else pd.DataFrame()
    if not df_basic.empty:
        st.write(
            f"Showing **{len(df_basic)}** of **{st.session_state.total_docs}** documents "
            f"(Page {st.session_state.current_page_for_display} of {st.session_state.total_pages})"
        )
        display_cols = ["PK_ID"] + BASIC_COLUMNS_TO_SHOW
        display_cols = [c for c in display_cols if c in df_basic.columns]
        df_view = df_basic[display_cols].copy()

        term = st.text_input("🔎 Quick Search basic results", key="quick_search_input_basic")
        if term:
            mask = df_view.apply(
                lambda r: r.astype(str).str.contains(term, case=False, na=False).any(),
                axis=1
            )
            df_view = df_view[mask]
            st.write(f"Showing {len(df_view)} rows matching quick search.")

        if df_view.empty:
            st.caption("No rows to display.")
        else:
            df_view['PK_ID'] = df_view['PK_ID'].astype(str)
            gb = GridOptionsBuilder.from_dataframe(df_view)
            gb.configure_default_column(
                sortable=True, resizable=True, wrapText=True, autoHeight=True,
                minWidth=150, filter=True, floatingFilter=True
            )
            gb.configure_column("PK_ID", hide=True)
            gb.configure_column("Document Title", minWidth=300)
            gb.configure_column("Org/Utility Name", minWidth=200)
            gb.configure_side_bar(filters_panel=False, columns_panel=True)
            gb.configure_pagination(
                paginationAutoPageSize=False,
                paginationPageSize=st.session_state.page_size
            )
            gb.configure_selection(
                selection_mode="multiple",
                use_checkbox=True,
                header_checkbox=True
            )
            opts = gb.build()

            grid = AgGrid(
                df_view,
                gridOptions=opts,
                key='grid_basic',
                height=600, width='100%',
                columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
                update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                allow_unsafe_jscode=True,
                enable_enterprise_modules=False
            )

            selected = grid.get("selected_rows") or []
            _data = grid.get("data")
            displayed = _data if _data is not None else pd.DataFrame()

            st.markdown("---")
            csv_bytes = displayed.to_csv(index=False).encode('utf-8') if not displayed.empty else b""
            st.download_button(
                label="📄 Download Basic View as CSV",
                data=csv_bytes,
                file_name="cairn_basic_export.csv",
                mime="text/csv",
                disabled=displayed.empty,
                key="csv_basic"
            )
            st.markdown("---")

            col1, col2 = st.columns([1, 3])
            with col1:
                if len(selected) == 1:
                    row = selected[0]
                    handle_single_download(row.get("PK_ID"), row.get("Document Title"), "basic")
                elif len(selected) > 1:
                    ids = [int(r.get("PK_ID")) for r in selected]
                    handle_batch_download(ids, "basic")
                else:
                    st.caption("Select one or more rows to enable download.")
            with col2:
                if selected:
                    sel_df = pd.DataFrame(selected).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                    st.dataframe(
                        sel_df if len(sel_df) > 1 else sel_df.iloc[0],
                        use_container_width=True,
                        height=200
                    )

# ─── Advanced Search Tab ──────────────────────────────────────────────────────
with advanced_tab:
    st.info("Advanced search view with all columns.")
    if st.session_state.get('api_error'):
        st.error(st.session_state.api_error)
    if st.session_state.get('data_message'):
        st.warning(st.session_state.data_message)

    df_adv = st.session_state.search_results_df if 'search_results_df' in st.session_state else pd.DataFrame()
    if not df_adv.empty:
        st.write(
            f"Showing **{len(df_adv)}** of **{st.session_state.total_docs}** documents "
            f"(Page {st.session_state.current_page_for_display} of {st.session_state.total_pages})"
        )
        df_view = df_adv.copy()

        term = st.text_input("🔎 Quick Search advanced results", key="quick_search_input_advanced")
        if term:
            mask = df_view.apply(
                lambda r: r.astype(str).str.contains(term, case=False, na=False).any(),
                axis=1
            )
            df_view = df_view[mask]
            st.write(f"Showing {len(df_view)} rows matching quick search.")

        if df_view.empty:
            st.caption("No rows to display.")
        else:
            df_view['PK_ID'] = df_view['PK_ID'].astype(str)
            gb = GridOptionsBuilder.from_dataframe(df_view)
            gb.configure_default_column(
                sortable=True, resizable=True, wrapText=True, autoHeight=True,
                minWidth=150, filter=True, floatingFilter=True
            )
            gb.configure_column("PK_ID", hide=True)
            link_renderer = JsCode('''
                function(params) {
                    return params.value
                        ? '<a href="'+params.value+'" target="_blank">'+params.value+'</a>'
                        : '';
                }
            ''')
            if "Document URL" in df_view.columns:
                gb.configure_column("Document URL", cellRenderer=link_renderer, minWidth=250)
            if "CAIRN URL" in df_view.columns:
                gb.configure_column("CAIRN URL", cellRenderer=link_renderer, minWidth=250)
            gb.configure_side_bar(filters_panel=True, columns_panel=True)
            gb.configure_pagination(
                paginationAutoPageSize=False,
                paginationPageSize=st.session_state.page_size
            )
            gb.configure_selection(
                selection_mode="multiple",
                use_checkbox=True,
                header_checkbox=True
            )
            opts = gb.build()

            grid = AgGrid(
                df_view,
                gridOptions=opts,
                key='grid_advanced',
                height=600, width='100%',
                columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
                update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                allow_unsafe_jscode=True,
                enable_enterprise_modules=False
            )

            selected = grid.get("selected_rows") or []
            _data = grid.get("data")
            displayed = _data if _data is not None else pd.DataFrame()

            st.markdown("---")
            csv_bytes = displayed.to_csv(index=False).encode('utf-8') if not displayed.empty else b""
            st.download_button(
                label="📄 Download Advanced View as CSV",
                data=csv_bytes,
                file_name="cairn_advanced_export.csv",
                mime="text/csv",
                disabled=displayed.empty,
                key="csv_advanced"
            )
            st.markdown("---")

            col1, col2 = st.columns([1, 3])
            with col1:
                if len(selected) == 1:
                    row = selected[0]
                    handle_single_download(row.get("PK_ID"), row.get("Document Title"), "advanced")
                elif len(selected) > 1:
                    ids = [int(r.get("PK_ID")) for r in selected]
                    handle_batch_download(ids, "advanced")
                else:
                    st.caption("Select one or more rows to enable download.")
            with col2:
                if selected:
                    sel_df = pd.DataFrame(selected).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                    st.dataframe(
                        sel_df if len(sel_df) > 1 else sel_df.iloc[0],
                        use_container_width=True,
                        height=200
                    )

# ─── Tags Tab ─────────────────────────────────────────────────────────────────
with tags_tab:
    st.info("Definitions of tags used to categorize documents.")
    tag_data = {
        'Tag Name (Filter)': [
            # ... your tag names ...
        ],
        'Description': [
            # ... your descriptions ...
        ],
        'Common Examples / Format': [
            # ... your examples/formats ...
        ]
    }
    try:
        lens = {k: len(v) for k, v in tag_data.items()}
        if len(set(lens.values())) > 1:
            st.error(f"Error creating Tag Definitions table: {lens}")
        else:
            df_tags = pd.DataFrame(tag_data)
            st.dataframe(df_tags, use_container_width=True, height=600)
    except Exception as e:
        st.error(f"Unexpected error displaying tags: {e}")

# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption("CAIRN Project v1.11.1 | Powered by Streamlit")
