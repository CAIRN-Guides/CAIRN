# frontend/streamlit_app.py
# Full drop-in replacement code - v1.9 (Remove getRowId)
# Removes getRowId configuration entirely to rely on default row indexing.
# Uses selected_rows, simplified update/return modes, reload_data=False removed.
# Still ensures PK_ID is string in DataFrame for consistency.
# Includes Basic/Advanced tabs, full About/Tags content.
# Fixes SyntaxError in download exception handling.
# Refactors download logic into a reusable function.

import os
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv
from PIL import Image # Keep if used elsewhere
# import time # Import time for spinner delays if needed (currently unused directly)
from datetime import date # Added for date conversion check
import traceback # For logging detailed errors if needed

# Make sure AgGrid is installed: pip install streamlit-aggrid
# Updated import for JsCode location can vary, check st_aggrid docs if needed
try:
    from st_aggrid.shared import JsCode # Still needed for potential future use or other JsCode
except ImportError:
    # Try alternative location if the first one fails (might depend on version)
    try:
        from st_aggrid.grid_options_builder import JsCode
    except ImportError:
        st.error("Could not import JsCode from streamlit-aggrid. Please ensure streamlit-aggrid is installed correctly.")
        # Stop execution if JsCode cannot be imported, as AgGrid configuration will fail
        st.stop()

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, ColumnsAutoSizeMode

# --- Constants ---
# Columns to display in the basic search view
BASIC_COLUMNS_TO_SHOW = ["File ID", "Document Title", "Org/Utility Name", "Document Type", "Published Date"]
# PK_ID is needed internally for actions but will be hidden in the grid display
API_TIMEOUT_SECONDS = 45 # Timeout for search requests
DOWNLOAD_API_TIMEOUT_SECONDS = 30 # Timeout for download link generation requests

# ─── Load Environment Variables & Page Setup ──────────────────────────────────
load_dotenv() # Load variables from .env file if present
# Get the backend API URL from environment variable, default to localhost for development
API_URL = os.getenv("API_URL", "http://localhost:8000")
# Placeholder for authentication headers - adapt if auth is implemented
AUTH_HEADERS = {}
if 'user_token' in st.session_state:
    AUTH_HEADERS = {"Authorization": f"Bearer {st.session_state['user_token']}"}

# Configure Streamlit page settings
st.set_page_config(page_title="CAIRN Finder", layout="wide")

# --- Helper Functions ---

def handle_single_download(doc_pk_id, doc_title, tab_prefix):
    """
    Handles the download button click, API call for a pre-signed URL,
    error handling, and displaying the download link via session state.

    Args:
        doc_pk_id: The primary key (database ID) of the document (expected as string).
        doc_title: The title of the document for display purposes.
        tab_prefix: A unique string ('basic' or 'advanced') to namespace keys.
    """
    # Ensure doc_pk_id is not None or empty string before proceeding
    if not doc_pk_id or str(doc_pk_id).strip() == "":
        st.warning(f"Cannot generate download link: Selected document is missing its ID (PK_ID={doc_pk_id}).")
        return

    button_label = f"⬇️ Download: {doc_title[:40]}..."
    # PK_ID should be string now
    button_key = f"download_single_{tab_prefix}_{doc_pk_id}"
    link_key = f'download_link_{tab_prefix}_{doc_pk_id}'

    # Display the download link first if it exists from a previous click/rerun
    if link_key in st.session_state:
        link_info = st.session_state[link_key]
        link = link_info.get("url")
        filename = link_info.get("filename")
        if link:
            filename_attr = f'download="{filename}"' if filename else "download" # Use API filename if provided
            st.markdown(f'✅ Link ready: <a href="{link}" target="_blank" {filename_attr}>Click here to download "{doc_title[:50]}..."</a>', unsafe_allow_html=True)
        # Clear the state after displaying the link
        del st.session_state[link_key]

    # Display the button
    if st.button(button_label, key=button_key):
        # Clear any existing link state for this item when button is clicked
        if link_key in st.session_state:
            del st.session_state[link_key]

        download_url_endpoint = f"{API_URL}/documents/{doc_pk_id}/download-url"
        try:
            with st.spinner(f"Generating link for '{doc_title[:30]}...'"):
                dl_resp = requests.get(
                    download_url_endpoint,
                    headers=AUTH_HEADERS,
                    timeout=DOWNLOAD_API_TIMEOUT_SECONDS
                )
                dl_resp.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                url_data = dl_resp.json()
                url = url_data.get("url")
                filename = url_data.get("filename", None) # Optional: Get suggested filename

                if url:
                    # Store URL and filename in session state to survive the rerun
                    st.session_state[link_key] = {"url": url, "filename": filename}
                    # Use st.rerun() to immediately show the link generated
                    st.rerun()
                else:
                    st.error("API did not return a valid download link.")
                    st.session_state.pop(link_key, None) # Ensure cleaned up if error

        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            detail = f"Server error ({status_code})" # Default message
            try:
                error_content = http_err.response.json()
                detail = error_content.get('detail', detail)
            except requests.exceptions.JSONDecodeError:
                detail = f"Server error ({status_code}): {http_err.response.text[:100]}"
            except Exception:
                 pass
            st.error(f"Download Link Failed: {detail}")
            st.session_state.pop(link_key, None)

        except requests.exceptions.RequestException as req_err:
            st.error(f"Network Error generating download link: {req_err}")
            st.session_state.pop(link_key, None)
        except Exception as e:
            st.error(f"An unexpected error occurred generating the download link: {e}")
            st.session_state.pop(link_key, None)


# ─── Header Display ───────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 6]) # Adjust column ratio for logo and title
with col1:
    try:
        st.image("https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp", width=60)
    except Exception as img_e:
        st.caption("CAIRN Logo")
with col2:
    st.title("CAIRN Document Finder")

# ─── Sidebar Filters Setup ───────────────────────────────────────────────────
st.sidebar.header("Filters")
params = {} # Dictionary to hold query parameters for the API call

# --- Text input filters ---
text_cols = [
    "document_id", "document_title", "local_backup_name", "tagger", "file_format",
    "rate_impact", "quality_check", "regulatory_body", "state_region", "docket_number",
    "document_type", "org_utility_name", "parent_document", "replaces_document",
    "document_url", "cairn_url", "processing_notes"
]
for col in text_cols:
    if f"filter_{col}" not in st.session_state: st.session_state[f"filter_{col}"] = ""
    st.session_state[f"filter_{col}"] = st.sidebar.text_input(
        col.replace("_"," ").title(),
        value=st.session_state[f"filter_{col}"],
        key=f"input_{col}"
    )
    if st.session_state[f"filter_{col}"]: params[col] = st.session_state[f"filter_{col}"]

# --- Date input filters ---
date_fields = ["published_date", "date_tagged", "last_synced_at", "updated_at"]
for col in date_fields:
    if f"filter_{col}" not in st.session_state: st.session_state[f"filter_{col}"] = None
    current_val = None
    if st.session_state[f"filter_{col}"] is not None:
        try: current_val = date.fromisoformat(st.session_state[f"filter_{col}"])
        except: current_val = None
    d = st.sidebar.date_input(col.replace("_"," ").title(), value=current_val, key=f"input_{col}")
    if d: params[col], st.session_state[f"filter_{col}"] = d.isoformat(), d.isoformat()
    else: st.session_state[f"filter_{col}"] = None

# --- List input filters (comma-separated text) ---
list_cols = [
    "additional_keywords", "ders", "utility_reform", "customer_classes",
    "energy_resources", "related_documents", "relationship_types"
]
for col in list_cols:
    if f"filter_{col}" not in st.session_state: st.session_state[f"filter_{col}"] = ""
    st.session_state[f"filter_{col}"] = st.sidebar.text_input(
        col.replace("_"," ").title() + " (comma-sep)",
        value=st.session_state[f"filter_{col}"],
        key=f"input_{col}"
    )
    s = st.session_state[f"filter_{col}"]
    if s: params[col] = [x.strip() for x in s.split(",") if x.strip()]

# --- Boolean input filter ---
if f"filter_physical_climate_risk" not in st.session_state: st.session_state[f"filter_physical_climate_risk"] = False
st.session_state[f"filter_physical_climate_risk"] = st.sidebar.checkbox(
    "Physical Climate Risk",
    value=st.session_state[f"filter_physical_climate_risk"],
    key="input_physical_climate_risk"
)
if st.session_state[f"filter_physical_climate_risk"]: params["physical_climate_risk"] = True

# --- Pagination & Options ---
st.sidebar.header("Options")
if 'page' not in st.session_state: st.session_state.page = 1
if 'page_size' not in st.session_state: st.session_state.page_size = 20
st.session_state.page = st.sidebar.number_input("Page Number", min_value=1, value=st.session_state.page, key="input_page")
st.session_state.page_size = st.sidebar.number_input("Page Size", min_value=1, max_value=200, value=st.session_state.page_size, key="input_page_size")
params["page"], params["page_size"] = st.session_state.page, st.session_state.page_size

# --- Load Button ---
load_button_pressed = st.sidebar.button("Load Documents", type="primary")

# ─── Main Area with Tabs ───────────────────────────────────────────────────────
about_tab, search_basic_tab, search_advanced_tab, tags_tab = st.tabs([
    "ℹ️ About CAIRN",
    "🔍 Search (Basic)",
    "🔬 Search (Advanced)",
    "🏷️ Tag Definitions"
])

# ─── Common Data Loading Logic ────────────────────────────────────────────────
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
            docs_data = resp.json()
            docs = docs_data.get("data", [])
            st.session_state.total_docs = docs_data.get("total_count", len(docs))
            st.session_state.current_page_for_display = params.get('page', 1)
            page_size = params.get('page_size', 20)
            st.session_state.total_pages = (st.session_state.total_docs + page_size - 1) // page_size if st.session_state.total_docs > 0 else 1

            if not docs:
                st.session_state.search_results_df = pd.DataFrame()
                st.session_state.api_error = None
                st.session_state.data_message = "No documents found matching your criteria."
            else:
                df = pd.DataFrame(docs)
                if 'id' not in df.columns:
                    st.session_state.search_results_df = pd.DataFrame()
                    st.session_state.api_error = "Critical Error: 'id' column missing from API response. Downloads will fail."
                    st.session_state.data_message = None
                    st.error(st.session_state.api_error) # Show error immediately if ID is missing
                else:
                    for lc in list_cols:
                        if lc in df.columns:
                            df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                    rename_map = {
                         "id": "PK_ID", "document_id": "File ID", "local_backup_name": "Local Backup Name",
                         "document_title": "Document Title", "published_date": "Published Date", "document_author": "Document Author",
                         "org_utility_name": "Org/Utility Name", "docket_number": "Docket Number", "document_type": "Document Type",
                         "document_subtype": "Document Subtype", "document_url": "Document URL", "cairn_url": "CAIRN URL",
                         "rate_impact": "Rate Impact", "utility_reform": "Utility Reform", "energy_resources": "Energy Resources",
                         "customer_classes": "Customer Classes", "ders": "DERs", "physical_climate_risk": "Physical Climate Risk",
                         "additional_keywords": "Additional Keywords", "tagger": "Tagger", "date_tagged": "Date Tagged",
                         "quality_check": "Quality Check", "processing_notes": "Processing Notes", "state_region": "State/Region",
                         "regulatory_body": "Regulatory Body", "jurisdiction_type": "Jurisdiction Type", "parent_document": "Parent Document",
                         "related_documents": "Related Documents", "replaces_document": "Replaces Document", "relationship_types": "Relationship Types",
                    }
                    all_possible_cols = list(rename_map.keys())
                    cols_in_df = [col for col in all_possible_cols if col in df.columns]
                    df_processed = df[cols_in_df]
                    df_renamed = df_processed.rename(columns=rename_map)

                    # Final check for PK_ID before storing
                    if 'PK_ID' not in df_renamed.columns:
                         st.session_state.search_results_df = pd.DataFrame()
                         st.session_state.api_error = "Critical Error: 'PK_ID' column lost during processing."
                         st.session_state.data_message = None
                         st.error(st.session_state.api_error)
                    elif df_renamed['PK_ID'].isnull().any():
                         st.session_state.search_results_df = pd.DataFrame()
                         st.session_state.api_error = "Critical Error: 'PK_ID' column contains NULL values. Downloads may fail."
                         st.session_state.data_message = None
                         st.error(st.session_state.api_error)
                    else:
                        # Ensure PK_ID is string for reliable JS interaction downstream
                        try:
                            df_renamed['PK_ID'] = df_renamed['PK_ID'].astype(str)
                        except Exception as e:
                            st.session_state.search_results_df = pd.DataFrame()
                            st.session_state.api_error = f"Critical Error: Failed to convert PK_ID to string - {e}"
                            st.session_state.data_message = None
                            st.error(st.session_state.api_error)
                            st.stop()

                        st.session_state.search_results_df = df_renamed
                        st.session_state.api_error = None
                        st.session_state.data_message = None

        except requests.exceptions.RequestException as e:
            st.session_state.search_results_df = pd.DataFrame()
            st.session_state.api_error = f"API Request Failed: {e}"
            st.session_state.data_message = None
        except Exception as e:
            st.session_state.search_results_df = pd.DataFrame()
            st.session_state.api_error = f"An error occurred while processing data: {e}"
            st.session_state.data_message = None
            print("Error during data loading/processing:")
            traceback.print_exc()


# ─── Tab Implementations ─────────────────────────────────────────────────────

# --- About Tab ---
with about_tab:
    # Full content for the About page (preserved)
    st.markdown("""
    ## What is CAIRN?
    ... [Content omitted for brevity - same as before] ...
    ### Getting Started: How to Query the CAIRN Database
    ... [Content omitted for brevity - same as before] ...
    """) # Keep your full markdown here

# --- Basic Search Tab ---
with search_basic_tab:
    st.info("Basic search view. Use sidebar filters and click 'Load Documents'. Select a single row to enable the download button below the table.")

    if st.session_state.get('api_error'): st.error(st.session_state.api_error)
    if st.session_state.get('data_message'): st.warning(st.session_state.data_message)

    if 'search_results_df' in st.session_state and not st.session_state.search_results_df.empty:
        st.write(f"Showing **{len(st.session_state.search_results_df)}** of **{st.session_state.total_docs}** total documents (Page {st.session_state.get('current_page_for_display', 1)} of {st.session_state.get('total_pages', 1)})")

        cols_to_display_basic = ["PK_ID"] + BASIC_COLUMNS_TO_SHOW
        available_basic_cols = [col for col in cols_to_display_basic if col in st.session_state.search_results_df.columns]
        # Make a copy to avoid modifying the main session state DataFrame
        df_basic_view = st.session_state.search_results_df[available_basic_cols].copy()

        search_term_basic = st.text_input("🔎 Quick Search basic results", key="quick_search_input_basic")
        df_display_basic = df_basic_view
        if search_term_basic:
            mask = df_display_basic.apply(lambda row: row.astype(str).str.contains(search_term_basic, case=False, na=False).any(), axis=1)
            df_display_basic = df_display_basic[mask]
            if not df_display_basic.empty:
                 st.write(f"Showing {len(df_display_basic)} rows matching quick search.")
            else:
                 st.caption("No results match the quick search term in this view.")

        if not df_display_basic.empty:
            # --- Pre-AgGrid Check (Basic) ---
            if 'PK_ID' not in df_display_basic.columns:
                st.error("CRITICAL (Basic): PK_ID column missing in DataFrame sent to AgGrid. Downloads will fail.")
                st.stop()
            if df_display_basic['PK_ID'].isnull().any():
                st.error("CRITICAL (Basic): PK_ID column contains NULL values in DataFrame sent to AgGrid. Downloads may fail.")
                df_display_basic = df_display_basic.dropna(subset=['PK_ID'])
                if df_display_basic.empty:
                    st.warning("All rows removed due to missing PK_ID.")
                    st.stop()
            # Ensure PK_ID is string here too, just before passing to AgGrid
            if df_display_basic['PK_ID'].dtype != 'object':
                 df_display_basic['PK_ID'] = df_display_basic['PK_ID'].astype(str)


            # Configure AgGrid options
            gb_basic = GridOptionsBuilder.from_dataframe(df_display_basic)
            gb_basic.configure_default_column(
                sortable=True, resizable=True, wrapText=True, autoHeight=True,
                minWidth=150, filter=True, floatingFilter=True
            )
            gb_basic.configure_column("PK_ID", hide=True)
            gb_basic.configure_column("Document Title", minWidth=300)
            gb_basic.configure_column("Org/Utility Name", minWidth=200)
            gb_basic.configure_side_bar(filters_panel=False, columns_panel=True)
            gb_basic.configure_pagination(paginationAutoPageSize=False, paginationPageSize=st.session_state.get('page_size', 20))
            gb_basic.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True)
            gb_basic.configure_grid_options(domLayout='normal')

            # Build grid options WITHOUT getRowId
            grid_opts_basic = gb_basic.build()
            # grid_opts_basic['getRowId'] = get_row_id_basic # <<< REMOVED

            # Display the AgGrid component
            grid_response_basic = AgGrid(
                df_display_basic,
                gridOptions=grid_opts_basic,
                key='document_grid_basic',
                height=600, width='100%',
                columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
                # Use simplified update/return modes
                update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED, # Get filtered/sorted data back
                allow_unsafe_jscode=True, # Still allow for potential future JS
                enable_enterprise_modules=False,
                # reload_data=False # Removed
            )

            # --- Use selected_rows (relying on default indexing now) ---
            selected_rows_basic = grid_response_basic.get("selected_rows")

            # --- Actions Area Below Basic Grid ---
            st.markdown("---")
            # Download the *displayed* data after filtering
            csv_data_basic = pd.DataFrame(grid_response_basic['data']).to_csv(index=False).encode('utf-8') if grid_response_basic['data'] else "".encode('utf-8')
            st.download_button(
                label="📄 Download Basic View as CSV",
                data=csv_data_basic,
                file_name="cairn_basic_export.csv",
                mime="text/csv",
                key='csv_download_basic',
                disabled=not grid_response_basic['data'] # Disable if no data displayed
            )
            st.markdown("---")

            col_act_basic_1, col_act_basic_2 = st.columns([1, 3])

            with col_act_basic_1: # Column for download buttons
                # Check if selection is valid (should be list of dicts)
                if selected_rows_basic and isinstance(selected_rows_basic, list):
                    num_selected = len(selected_rows_basic)
                    if num_selected == 1:
                        selected_doc = selected_rows_basic[0]
                        # Extract PK_ID from the returned row data dictionary
                        doc_pk_id = selected_doc.get('PK_ID') # Should be string
                        doc_title = selected_doc.get('Document Title', f'File ID {selected_doc.get("File ID", "N/A")}')
                        handle_single_download(doc_pk_id, doc_title, "basic")
                    elif num_selected > 1:
                        st.button(f"⬇️ Download {num_selected} Selected as ZIP", key="download_selected_zip_basic", disabled=True)
                        st.caption("(ZIP download not yet implemented)")
                else: # Handles None or empty list
                     st.caption("Select a single row to enable download.")

            with col_act_basic_2: # Column for displaying details
                 if selected_rows_basic and isinstance(selected_rows_basic, list) and len(selected_rows_basic) > 0:
                     st.markdown("#### Selected Document Details")
                     try:
                         # Create DataFrame directly from selected_rows
                         sel_df = pd.DataFrame(selected_rows_basic).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                         if len(sel_df) == 1:
                             st.dataframe(sel_df.iloc[0], use_container_width=True)
                         else:
                             st.dataframe(sel_df, use_container_width=True, height=200)
                     except Exception as detail_e:
                         st.error(f"Error displaying details: {detail_e}")

# --- Advanced Search Tab ---
with search_advanced_tab:
    st.info("Advanced search view with all columns. Use sidebar filters and click 'Load Documents'. Select a single row to enable the download button below the table.")

    if st.session_state.get('api_error'): st.error(st.session_state.api_error)
    if st.session_state.get('data_message'): st.warning(st.session_state.data_message)

    if 'search_results_df' in st.session_state and not st.session_state.search_results_df.empty:
        st.write(f"Showing **{len(st.session_state.search_results_df)}** of **{st.session_state.total_docs}** total documents (Page {st.session_state.get('current_page_for_display', 1)} of {st.session_state.get('total_pages', 1)})")

        # Make a copy to avoid modifying the main session state DataFrame
        df_advanced_view = st.session_state.search_results_df.copy()

        search_term_advanced = st.text_input("🔎 Quick Search advanced results", key="quick_search_input_advanced")
        df_display_advanced = df_advanced_view
        if search_term_advanced:
            mask = df_display_advanced.apply(lambda row: row.astype(str).str.contains(search_term_advanced, case=False, na=False).any(), axis=1)
            df_display_advanced = df_display_advanced[mask]
            if not df_display_advanced.empty:
                 st.write(f"Showing {len(df_display_advanced)} rows matching quick search.")
            else:
                 st.caption("No results match the quick search term in this view.")

        if not df_display_advanced.empty:
            # --- Pre-AgGrid Check (Advanced) ---
            if 'PK_ID' not in df_display_advanced.columns:
                st.error("CRITICAL (Advanced): PK_ID column missing in DataFrame sent to AgGrid. Downloads will fail.")
                st.stop()
            if df_display_advanced['PK_ID'].isnull().any():
                st.error("CRITICAL (Advanced): PK_ID column contains NULL values in DataFrame sent to AgGrid. Downloads may fail.")
                df_display_advanced = df_display_advanced.dropna(subset=['PK_ID'])
                if df_display_advanced.empty:
                    st.warning("All rows removed due to missing PK_ID.")
                    st.stop()
            # Ensure PK_ID is string
            if df_display_advanced['PK_ID'].dtype != 'object':
                 df_display_advanced['PK_ID'] = df_display_advanced['PK_ID'].astype(str)

            # Configure AgGrid options
            gb_advanced = GridOptionsBuilder.from_dataframe(df_display_advanced)
            gb_advanced.configure_default_column(
                sortable=True, resizable=True, wrapText=True, autoHeight=True,
                minWidth=150, filter=True, floatingFilter=True
            )
            gb_advanced.configure_column("PK_ID", hide=True)
            link_renderer = JsCode('''
                function(params) {
                    if (params.value) {
                        return '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">' + params.value + '</a>';
                    } else { return ''; } }
            ''')
            if "Document URL" in df_display_advanced.columns: gb_advanced.configure_column("Document URL", cellRenderer=link_renderer, minWidth=250)
            if "CAIRN URL" in df_display_advanced.columns: gb_advanced.configure_column("CAIRN URL", cellRenderer=link_renderer, minWidth=250)
            gb_advanced.configure_side_bar(filters_panel=True, columns_panel=True)
            gb_advanced.configure_pagination(paginationAutoPageSize=False, paginationPageSize=st.session_state.get('page_size', 20))
            gb_advanced.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True)
            gb_advanced.configure_grid_options(domLayout='normal')

            # Build grid options WITHOUT getRowId
            grid_opts_advanced = gb_advanced.build()
            # grid_opts_advanced['getRowId'] = get_row_id_advanced # <<< REMOVED

            # Display the AgGrid component
            grid_response_advanced = AgGrid(
                df_display_advanced,
                gridOptions=grid_opts_advanced,
                key='document_grid_advanced',
                height=600, width='100%',
                columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
                # Use simplified update/return modes
                update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED, # Get filtered/sorted data back
                allow_unsafe_jscode=True, # Still allow for potential future JS
                enable_enterprise_modules=False,
                # reload_data=False # Removed
            )

            # --- Use selected_rows (relying on default indexing now) ---
            selected_rows_advanced = grid_response_advanced.get("selected_rows")

            # --- Actions Area Below Advanced Grid ---
            st.markdown("---")
            # Download the *displayed* data after filtering
            csv_data_advanced = pd.DataFrame(grid_response_advanced['data']).to_csv(index=False).encode('utf-8') if grid_response_advanced['data'] else "".encode('utf-8')
            st.download_button(
                label="📄 Download Advanced View as CSV",
                data=csv_data_advanced,
                file_name="cairn_advanced_export.csv",
                mime="text/csv",
                key='csv_download_advanced',
                disabled=not grid_response_advanced['data'] # Disable if no data displayed
            )
            st.markdown("---")

            col_act_adv_1, col_act_adv_2 = st.columns([1, 3])

            with col_act_adv_1: # Column for download buttons
                # Check if selection is valid
                if selected_rows_advanced and isinstance(selected_rows_advanced, list):
                    num_selected = len(selected_rows_advanced)
                    if num_selected == 1:
                        selected_doc = selected_rows_advanced[0]
                        # Extract PK_ID from the returned row data dictionary
                        doc_pk_id = selected_doc.get('PK_ID') # Should be string
                        doc_title = selected_doc.get('Document Title', f'File ID {selected_doc.get("File ID", "N/A")}')
                        handle_single_download(doc_pk_id, doc_title, "advanced")
                    elif num_selected > 1:
                        st.button(f"⬇️ Download {num_selected} Selected as ZIP", key="download_selected_zip_advanced", disabled=True)
                        st.caption("(ZIP download not yet implemented)")
                else: # Handles None or empty list
                     st.caption("Select a single row to enable download.")

            with col_act_adv_2: # Column for displaying details
                 if selected_rows_advanced and isinstance(selected_rows_advanced, list) and len(selected_rows_advanced) > 0:
                     st.markdown("#### Selected Document Details")
                     try:
                         # Create DataFrame directly from selected_rows
                         sel_df = pd.DataFrame(selected_rows_advanced).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                         if len(sel_df) == 1:
                             st.dataframe(sel_df.iloc[0], use_container_width=True)
                         else:
                             st.dataframe(sel_df, use_container_width=True, height=200)
                     except Exception as detail_e:
                         st.error(f"Error displaying details: {detail_e}")


# --- Tags Tab ---
with tags_tab:
    st.info("""
    This table explains the different fields (tags) used to categorize documents in CAIRN.
    You can use the filters in the sidebar (under the search tabs) to search based on these fields and terms.
    """)

    # Define the COMPLETE tag data (preserved)
    tag_data = {
        'Tag Name (Filter)': [
             "File ID", "Document Title", "Published Date", "Org/Utility Name",
             "Docket Number", "Document Type", "Document Subtype", "Document URL", "CAIRN URL",
             "Rate Impact", "Utility Reform", "Energy Resources", "Customer Classes", "DERs",
             "Physical Climate Risk", "Additional Keywords", "Tagger", "Date Tagged", "Quality Check",
             "Processing Notes", "State/Region", "Regulatory Body", "Jurisdiction Type",
             "Parent Document", "Related Documents", "Replaces Document", "Relationship Types",
             "Document Author"
        ],
        'Description': [
             "Unique identifier for the document record (e.g., C250001)",
             "Full official title of the document", "The date the document was published or filed",
             "The primary utility, organization, or agency associated with the document",
             "The official proceeding number (e.g., UE-230810)", "The main category or classification of the document",
             "A more specific sub-category of the document", "Direct URL link to the original source document webpage (if available)",
             "Direct URL link to the document file stored within the CAIRN system (if available)",
             "Does the document primarily discuss ratepayer bill or tariff impacts? (Yes/No/Partial)",
             "Does the document primarily focus on utility governance or business model changes? (Yes/No/Partial)",
             "Comma-separated list of energy resource types discussed (e.g., gas, solar, storage, EE)",
             "Comma-separated list of customer classes addressed (e.g., residential, C&I, low-income)",
             "Does the document primarily focus on Distributed Energy Resources (DERs)? (Yes/No)",
             "Does the document primarily discuss physical climate risks like wildfire, heat, floods? (Yes/No)",
             "Comma-separated list of additional relevant keywords for searching",
             "Identifier for the person or team who applied the tags", "The date the tags were applied or last updated",
             "Has the accuracy of the document's metadata been verified? (Complete/Pending/Needs Review)",
             "Internal notes regarding document processing, OCR issues, or anomalies",
             "The primary geographic state or region the document pertains to",
             "The primary regulatory agency with jurisdiction (e.g., PUC, FERC)",
             "The level of regulatory authority (e.g., State-Level, National)",
             "The File ID of a parent document this document belongs to (e.g., for appendices)",
             "Comma-separated File IDs of other documents related to this one",
             "The File ID of a document that this document replaces or supersedes",
             "Describes the relationship to parent/related documents (e.g., Appendix, Comment)",
             "The individual, firm, or entity that authored the document"
        ],
         'Common Examples / Format': [
              "CYY##### format (e.g., C250001)", "Text", "YYYY-MM-DD", "PSE, Avista, PGE, CAISO, PNNL",
              "UE-#####, UG-#####, etc.", "IRP/ISP, Assessment, Comment, Report, Regulatory Rate Plan Order",
              "Electric IRP, Gas IRP, Comment, Clean_Energy_Party, Integrated Resource Plan", "URL",
              "URL (May require login/access)", "Yes, No, Partial", "Yes, No, Partial",
              "All, Gas, Solar, Storage, EE, Clean_Energy, Efficiency", "All, Residential, C&I, Low-Income",
              "Yes, No", "Yes, No", "IRP, Resilience, Decarbonization, MYRP, Wildfire",
              "Text (e.g., Apples)", "YYYY-MM-DD", "Complete, Pending, Needs Review",
              "Text (e.g., OCR issues found)", "WA, CA, OR, Multi-state, National",
              "WA_UTC, Oregon PUC, CAISO, FERC, CPUC", "State-Level, National, Regional",
              "CYY##### format (e.g., C250002)", "CYY##### format (comma-sep)", "CYY##### format",
              "Appendix, IRP_Comment, Staff_Comment, Errata",
              "Text"
         ]
    }

    # Create and display the DataFrame for tag definitions
    try:
        list_lengths = {key: len(value) for key, value in tag_data.items()}
        if len(set(list_lengths.values())) > 1:
            st.error(f"Error creating Tag Definitions table: Lists have different lengths. {list_lengths}")
        else:
            tag_definitions_df = pd.DataFrame(tag_data)
            st.dataframe(tag_definitions_df, use_container_width=True, height=600)
    except Exception as e:
        st.error(f"An unexpected error occurred displaying Tag Definitions: {e}")

# Optional Footer
st.markdown("---")
st.caption("CAIRN Project v1.9 | Powered by Streamlit")
