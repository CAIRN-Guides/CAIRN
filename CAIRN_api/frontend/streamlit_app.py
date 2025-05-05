import os
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv
from PIL import Image  # for optional logo
from datetime import date
import traceback

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, ColumnsAutoSizeMode
try:
    from st_aggrid.shared import JsCode
except ImportError:
    from st_aggrid.grid_options_builder import JsCode

# ─── Configuration ─────────────────────────────────────────────────────────────
load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000")
SIGNED_URL_TIMEOUT = int(os.getenv("DOWNLOAD_API_TIMEOUT_SECONDS", "60"))
BASIC_COLUMNS = ["File ID", "Document Title", "Org/Utility Name", "Document Type", "Published Date"]

st.set_page_config(page_title="CAIRN Finder", layout="wide")

# Authentication header if using token
AUTH_HEADERS = {}
if 'user_token' in st.session_state:
    AUTH_HEADERS = {"Authorization": f"Bearer {st.session_state['user_token']}"}

# ─── Helper: Batch Signed URLs ─────────────────────────────────────────────────
def handle_batch_download(pks: list[int], key: str):
    """
    Generate and display signed URLs for given PK list under a unique session key.
    """
    session_key = f"batch_urls_{key}"
    btn_label = f"⬇️ Generate download links for {len(pks)} file{'s' if len(pks)>1 else ''}"

    # Trigger generation
    if session_key not in st.session_state:
        if st.button(btn_label, key=f"btn_{key}"):
            try:
                with st.spinner("Requesting signed URLs..."):
                    resp = requests.post(
                        f"{API_URL}/documents/batch-signed-urls",
                        headers={**AUTH_HEADERS, "Content-Type": "application/json"},
                        json={"document_ids": pks},
                        timeout=SIGNED_URL_TIMEOUT,
                    )
                    resp.raise_for_status()
                    urls = resp.json().get("urls", [])
                    if not urls:
                        st.error("No downloadable links returned.")
                    else:
                        st.session_state[session_key] = urls
            except Exception as e:
                st.error(f"Error generating links: {e}")

    # Display links if available
    if session_key in st.session_state:
        st.markdown("**Download Links:**")
        for item in st.session_state[session_key]:
            url = item.get("url")
            fn = item.get("filename", url)
            st.markdown(
                f"- <a href='{url}' target='_blank' download='{fn}'>{fn}</a>",
                unsafe_allow_html=True,
            )
        if st.button("Clear Links", key=f"clear_{key}"):
            del st.session_state[session_key]
            st.experimental_rerun()
        st.markdown("---")

# ─── Sidebar Filters ────────────────────────────────────────────────────────────
st.sidebar.header("Filters")
params: dict[str, str] = {}
# Text filters
text_fields = [
    "document_id", "document_title", "org_utility_name", "docket_number",
    "document_type", "state_region"
]
for f in text_fields:
    val = st.sidebar.text_input(f.replace('_', ' ').title(), key=f)
    if val:
        params[f] = val
# Date filter example
pub_date = st.sidebar.date_input("Published Date", key="published_date")
if pub_date:
    params["published_date"] = pub_date.isoformat()
# Pagination
st.sidebar.header("Pagination")
page = st.sidebar.number_input("Page", min_value=1, value=1, key="page")
size = st.sidebar.number_input("Page Size", min_value=1, max_value=100, value=20, key="page_size")
params.update({"page": page, "page_size": size})

# Load button
load = st.sidebar.button("Load Documents")

# ─── Fetch Data ────────────────────────────────────────────────────────────────
if load:
    st.session_state.df = pd.DataFrame()
    try:
        with st.spinner("Fetching documents..."):
            r = requests.get(
                f"{API_URL}/documents",
                params=params,
                headers=AUTH_HEADERS,
                timeout=API_TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            data = r.json()
            docs = data.get("data", [])
            df = pd.DataFrame(docs)
            if df.empty:
                st.warning("No documents found.")
            else:
                # normalize list fields
                list_cols = [c for c in df.columns if isinstance(df[c].iloc[0], list)]
                for c in list_cols:
                    df[c] = df[c].apply(lambda x: ", ".join(x))
                # rename PK
                df.rename(columns={"id": "PK_ID"}, inplace=True)
                df["PK_ID"] = df["PK_ID"].astype(int)
                st.session_state.df = df
                st.session_state.total = data.get("total_count", len(df))
                st.session_state.page = data.get("page", page)
                st.session_state.size = data.get("page_size", size)
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        traceback.print_exc()

# ─── Main UI ──────────────────────────────────────────────────────────────────
st.title("CAIRN Document Finder")

if "df" in st.session_state and not st.session_state.df.empty:
    df = st.session_state.df
    st.write(
        f"Showing {len(df)} of {st.session_state.total} documents (Page {st.session_state.page}/{(st.session_state.total-1)//st.session_state.size+1})"
    )
    # Quick search
    q = st.text_input("Quick search")
    if q:
        mask = df.apply(lambda row: row.astype(str).str.contains(q, case=False).any(), axis=1)
        df = df[mask]
    # Prepare view
    view = df[["PK_ID"] + BASIC_COLUMNS].copy()
    view["PK_ID"] = view["PK_ID"].astype(int)
    # AgGrid
    gb = GridOptionsBuilder.from_dataframe(view)
    gb.configure_default_column(filter=True, sortable=True)
    gb.configure_selection("multiple", use_checkbox=True)
    grid_opts = gb.build()
    grid = AgGrid(
        view, gridOptions=grid_opts,
        height=400, update_mode=GridUpdateMode.SELECTION_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
    )
    selected = grid['data']
    handle_batch_download(selected['PK_ID'].tolist(), "main")
else:
    st.info("Use the sidebar to load documents.")
