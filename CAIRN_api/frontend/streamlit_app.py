import os
import streamlit as st
import requests # For making API calls
import pandas as pd
from dotenv import load_dotenv
# from PIL import Image # Removed unless used elsewhere
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import traceback # For detailed error logging

# ─── Load env & page setup ─────────────────────────────────────────────────────
load_dotenv()
# API Base URL from environment or default
API_BASE_URL = os.getenv("API_URL", "https://cairn-backend.onrender.com")
# Specific endpoint for fetching documents
DOCUMENTS_API_URL = f"{API_BASE_URL.rstrip('/')}/documents"

st.set_page_config(page_title="CAIRN Finder", layout="wide")

# --- Initialize Session State ---
if 'docs_df' not in st.session_state:
    st.session_state.docs_df = pd.DataFrame() # Stores the main DataFrame
if 'grid_response' not in st.session_state:
    st.session_state.grid_response = None # Stores the output from AgGrid

# ─── Header ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 5])
with col1:
    try:
        st.image("https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp", width=40)
    except Exception as img_err:
        st.warning(f"Could not load logo image: {img_err}")
with col2:
    st.title("CAIRN Document Finder")

# ─── Sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.header("Filters")
params = {} # Reset params dict for current run

# --- Text Input Filters ---
text_cols = [
    "document_id", "document_title", "local_backup_name", "tagger",
    "file_format", "rate_impact", "quality_check", "regulatory_body",
    "state_region", "docket_number", "document_type", "org_utility_name",
    "parent_document", "replaces_document", "document_url", "cairn_url",
    "processing_notes"
]
for col in text_cols:
    v = st.sidebar.text_input(col.replace("_", " ").title())
    if v: params[col] = v

# --- Date Input Filters ---
if d := st.sidebar.date_input("Published Date", value=None, key="published_date_filter"): params["published_date"] = d.isoformat()
if d := st.sidebar.date_input("Date Tagged", value=None, key="date_tagged_filter"): params["date_tagged"] = d.isoformat()
if d := st.sidebar.date_input("Last Synced At", value=None, key="last_synced_filter"): params["last_synced_at"] = d.isoformat()
if d := st.sidebar.date_input("Updated At", value=None, key="updated_at_filter"): params["updated_at"] = d.isoformat()

# --- List Input Filters (Comma-Separated Text) ---
list_cols = [
    "additional_keywords", "ders", "utility_reform",
    "customer_classes", "energy_resources",
    "related_documents", "relationship_types"
]
for col in list_cols:
    s = st.sidebar.text_input(col.replace("_", " ").title() + " (comma-separated)")
    if s: params[col] = s

# --- Boolean Input Filter ---
if st.sidebar.checkbox("Physical Climate Risk"): params["physical_climate_risk"] = "true"

# --- Pagination & Options ---
st.sidebar.header("Options")
params["page"] = st.sidebar.number_input("Page Number", min_value=1, value=1)
params["page_size"] = st.sidebar.number_input("Page Size", min_value=1, max_value=200, value=20)

# --- Load Button ---
load_button_pressed = st.sidebar.button("Load Documents", key="load_docs_button")

# ─── Main Area with Tabs ───────────────────────────────────────────────────────
about_tab, search_tab, tags_tab = st.tabs([
    "ℹ️ About CAIRN",
    "🔍 Search Documents",
    "🏷️ Tag Definitions"
])

# ─── About Tab Content ─────────────────────────────────────────────────────────
with about_tab:
    st.markdown("{Placeholder}") # Placeholder as requested

# ─── Search Tab Content ────────────────────────────────────────────────────────
with search_tab:
    st.info("Use the filters in the sidebar and click 'Load Documents' to fetch and display data here.")

    # --- Data Fetching Logic ---
    if load_button_pressed:
        with st.spinner('Fetching documents from CAIRN...'):
            try:
                active_params = {k: v for k, v in params.items() if v is not None and v != ''}
                # st.write("Sending Request to:", DOCUMENTS_API_URL) # Optional Debug
                # st.write("With Params:", active_params) # Optional Debug

                resp = requests.get(DOCUMENTS_API_URL, params=active_params, timeout=45)
                resp.raise_for_status()

                docs_data = resp.json()
                docs = docs_data.get("data", [])
                total_docs = docs_data.get("total_count", len(docs))
                current_page = active_params.get('page', 1)
                page_size = active_params.get('page_size', 20)
                total_pages = (total_docs + page_size - 1) // page_size if total_docs > 0 else 1

                st.write(f"Showing **{len(docs)}** of **{total_docs}** documents (Page {current_page} of {total_pages})")

                if not docs:
                    st.warning("No documents found matching your criteria.")
                    st.session_state.docs_df = pd.DataFrame()
                else:
                    df = pd.DataFrame(docs)
                    # --- Flatten list columns for display ---
                    list_cols_from_sidebar = [
                        "additional_keywords", "ders", "utility_reform", "customer_classes",
                        "energy_resources", "related_documents", "relationship_types"
                    ]
                    for lc in list_cols_from_sidebar:
                        if lc in df.columns and df[lc].apply(lambda x: isinstance(x, list)).any():
                            df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                    # --- Reorder & rename columns for display ---
                    cols_order_original = [
                        "id", "document_id", "document_title", "published_date", "org_utility_name",
                        "docket_number", "document_type", "document_subtype", "state_region",
                        "rate_impact", "utility_reform", "energy_resources", "customer_classes", "ders",
                        "physical_climate_risk", "additional_keywords", "document_url", "cairn_url",
                        "tagger", "date_tagged", "quality_check", "local_backup_name", "file_format",
                        "processing_notes", "document_author", "regulatory_body", "jurisdiction_type",
                        "parent_document", "related_documents", "replaces_document", "relationship_types",
                        "b2_file_id", "created_at", "updated_at", "last_synced_at",
                    ]
                    cols_to_display = [col for col in cols_order_original if col in df.columns]
                    df_ordered = df[cols_to_display]

                    rename_map = {
                        "id": "DB ID", "document_id": "File ID", "local_backup_name": "Local Backup Name",
                        "document_title": "Document Title", "published_date": "Published Date",
                        "document_author": "Document Author", "org_utility_name": "Org/Utility Name",
                        "docket_number": "Docket Number", "document_type": "Document Type",
                        "document_subtype": "Document Subtype", "document_url": "Document URL",
                        "cairn_url": "CAIRN URL", "b2_file_id": "B2 File ID", "rate_impact": "Rate Impact",
                        "utility_reform": "Utility Reform", "energy_resources": "Energy Resources",
                        "customer_classes": "Customer Classes", "ders": "DERs",
                        "physical_climate_risk": "Physical Climate Risk", "additional_keywords": "Additional Keywords",
                        "tagger": "Tagger", "date_tagged": "Date Tagged", "quality_check": "Quality Check",
                        "processing_notes": "Processing Notes", "state_region": "State/Region",
                        "regulatory_body": "Regulatory Body", "jurisdiction_type": "Jurisdiction Type",
                        "parent_document": "Parent Document", "related_documents": "Related Documents",
                        "replaces_document": "Replaces Document", "relationship_types": "Relationship Types",
                        "created_at": "Created At", "updated_at": "Updated At", "last_synced_at": "Last Synced At",
                        "file_format": "File Format",
                    }
                    df_renamed = df_ordered.rename(columns={k: v for k, v in rename_map.items() if k in df_ordered.columns})
                    st.session_state.docs_df = df_renamed # Update session state

            except requests.exceptions.RequestException as e:
                st.error(f"API Request Failed: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    st.error(f"Status Code: {e.response.status_code}")
                    st.error(f"Response Text: {e.response.text}")
                st.session_state.docs_df = pd.DataFrame()
            except Exception as e:
                st.error(f"An error occurred while processing data: {e}")
                st.error(traceback.format_exc())
                st.session_state.docs_df = pd.DataFrame()

    # --- Display AgGrid and Actions (Based on Session State) ---
    if not st.session_state.docs_df.empty:
        df_display_base = st.session_state.docs_df

        # --- Quick-search filter ---
        search = st.text_input("🔎 Quick Search current results", key="quick_search_input")
        if search:
            mask = df_display_base.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
            df_display_final = df_display_base[mask]
        else:
            df_display_final = df_display_base

        # <<< --- DEBUG LINE (Optional: Can be removed once grid displays correctly) --- >>>
        # st.subheader("Debug: DataFrame going into AgGrid")
        # st.dataframe(df_display_final)
        # <<< --- END DEBUG LINE --- >>>

        # --- Configure AgGrid ---
        gb = GridOptionsBuilder.from_dataframe(df_display_final)

        # *** FIX: Commented out the problematic valueGetter ***
        gb.configure_default_column(
            groupable=True,
            # valueGetter="(data.field == null ? '' : data.field)", # REMOVED - Let AgGrid handle defaults
            filter="agTextColumnFilter", filterParams={"debounceMs": 300},
            sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150
        )
        # --- End of Fix ---

        link_cols = ["Document URL", "CAIRN URL"]
        for link_col in link_cols:
             if link_col in df_display_final.columns:
                 gb.configure_column(link_col, cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''', minWidth=250)

        gb.configure_side_bar(filters_panel=True, columns_panel=True)
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=params.get('page_size', 20))
        gb.configure_selection(
            selection_mode="multiple", use_checkbox=True, header_checkbox=True, rowMultiSelectWithClick=False
        )
        gb.configure_grid_options(domLayout='normal')
        grid_opts = gb.build()

        # --- Render AgGrid ---
        st.session_state.grid_response = AgGrid(
            df_display_final,
            gridOptions=grid_opts,
            key='document_grid_main',
            enable_enterprise_modules=False,
            update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT,
            fit_columns_on_grid_load=False,
            height=600, width='100%',
            reload_data=False, # Data managed by session state
            allow_unsafe_jscode=True, # For links
            # Optional: Add this if issues persist, might help JS function handling
            # try_convert_js_functions_to_string=True
        )

        # --- Actions Section ---
        st.markdown("---")
        col_actions1, col_actions2 = st.columns(2)

        # --- Download Table View (CSV) ---
        with col_actions1:
            # Uses grid_response['data'] which reflects client-side filtering/sorting
            out_df_view = pd.DataFrame(st.session_state.grid_response["data"])
            if not out_df_view.empty:
                timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
                csv_filename = f"cairn_export_{timestamp}.csv"
                csv_data = out_df_view.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Download Table View (CSV)", data=csv_data,
                    file_name=csv_filename, mime="text/csv", key='csv_download_button'
                )
            else:
                st.button("⬇️ Download Table View (CSV)", disabled=True, key='csv_download_button_disabled')

        # --- Retrieve selected rows safely ---
        selected_rows_data = None
        grid_response_current = st.session_state.get('grid_response')
        if grid_response_current:
            selected_rows_data = grid_response_current.get("selected_rows")

        # --- Check if selected_rows_data is a non-empty list (FIX for ValueError) ---
        if isinstance(selected_rows_data, list) and selected_rows_data:
            # --- PDF Download Logic ---
            with col_actions2:
                sel_df = pd.DataFrame(selected_rows_data)
                if "DB ID" not in sel_df.columns:
                    st.error("Error: 'DB ID' column missing in selection.")
                    st.button("📄 Prepare PDF Download Link", disabled=True, key='pdf_download_button_disabled_no_id')
                else:
                    selected_doc_pks = sel_df["DB ID"].tolist()
                    num_selected = len(selected_doc_pks)
                    download_button_label = f"📄 Prepare PDF Download Link ({num_selected} selected)"

                    if st.button(download_button_label, key="pdf_download_trigger_button"):
                        with st.spinner("Generating download link... Please wait..."):
                            download_api_url = None
                            payload = None
                            headers = {"Accept": "application/json"}
                            full_proxy_url = None
                            download_filename = "download"

                            try:
                                if num_selected == 1:
                                    doc_pk = selected_doc_pks[0]
                                    download_api_url = f"{API_BASE_URL.rstrip('/')}/documents/{doc_pk}/download-url"
                                    download_resp = requests.get(download_api_url, headers=headers, timeout=30)
                                elif num_selected > 1:
                                    download_api_url = f"{API_BASE_URL.rstrip('/')}/documents/batch-download-url"
                                    payload = {"document_ids": selected_doc_pks}
                                    headers["Content-Type"] = "application/json"
                                    download_resp = requests.post(download_api_url, json=payload, headers=headers, timeout=180)
                                else:
                                    download_resp = None # Should not happen

                                if download_resp:
                                    download_resp.raise_for_status()
                                    download_data = download_resp.json()
                                    relative_proxy_url = download_data.get("url")
                                    download_filename = download_data.get("filename", "cairn_download")

                                    if relative_proxy_url:
                                        full_proxy_url = f"{API_BASE_URL.rstrip('/')}{relative_proxy_url}"
                                        st.success("Download link ready!")
                                        st.markdown(f"""
                                        Click link to download: <a href="{full_proxy_url}" target="_blank">{download_filename}</a>
                                        """, unsafe_allow_html=True)
                                        st.caption("Link may expire.")
                                    else:
                                        st.error("API did not return a valid download URL path.")
                                        st.json(download_data)

                            except requests.exceptions.RequestException as req_err:
                                st.error(f"API Error: {req_err}")
                                if hasattr(req_err, 'response') and req_err.response is not None:
                                    st.error(f"API Status: {req_err.response.status_code}")
                                    try:
                                        st.error("API Detail:")
                                        st.json(req_err.response.json())
                                    except ValueError:
                                        st.error(f"API Response: {req_err.response.text[:500]}...")
                            except Exception as gen_err:
                                st.error(f"Unexpected error: {gen_err}")
                                st.error(traceback.format_exc())

            # --- Detail pane for selected rows ---
            st.markdown("---")
            sel_df_details = pd.DataFrame(selected_rows_data).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
            st.markdown("### 📄 Selected Document Details")
            if len(sel_df_details) == 1:
                st.dataframe(sel_df_details.iloc[0])
            else:
                st.dataframe(sel_df_details, use_container_width=True)

        else:
            # --- Handle Case: No Rows Selected ---
            with col_actions2:
                 st.button("📄 Prepare PDF Download Link", disabled=True, key='pdf_download_button_disabled_no_selection')
            st.markdown("---")
            st.caption("Select rows in the table to view details or prepare PDF download.")

    # --- Handle case where Load was pressed but no results found ---
    elif load_button_pressed and st.session_state.docs_df.empty:
        pass # Warning already shown during fetch attempt

    # --- Initial state (before Load is pressed) ---
    # No grid or actions displayed until data is loaded.

# ─── Tag Definitions Tab Content ───────────────────────────────────────────────
with tags_tab:
    st.markdown("{Placeholder}") # Placeholder as requested

# ─── Optional Footer ───────────────────────────────────────────────────────────
# st.markdown("---")
# st.caption("CAIRN Project | Powered by Streamlit")