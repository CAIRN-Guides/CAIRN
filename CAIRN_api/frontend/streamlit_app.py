# frontend/streamlit_app.py
# Full drop-in replacement code - v1.4
# Fixes JS error with getRowId, includes Basic/Advanced tabs, full About/Tags content.

import os
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv
from PIL import Image # Keep if used elsewhere
import time # Import time for spinner delays if needed
from datetime import date # Added for date conversion check

# Make sure AgGrid is installed: pip install streamlit-aggrid streamlit-aggrid-ext
# Updated import for JsCode location can vary, check st_aggrid docs if needed
try:
    from st_aggrid.shared import JsCode
except ImportError:
    # Try alternative location if the first one fails (might depend on version)
    try:
        from st_aggrid.grid_options_builder import JsCode
    except ImportError:
        st.error("Could not import JsCode from streamlit-aggrid. Please ensure streamlit-aggrid is installed correctly.")
        st.stop() # Stop execution if JsCode cannot be imported

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, ColumnsAutoSizeMode

# --- Constants ---
BASIC_COLUMNS_TO_SHOW = ["File ID", "Document Title", "Org/Utility Name", "Document Type", "Published Date"]
# PK_ID is needed internally but will be hidden

# ─── Load env & page setup ─────────────────────────────────────────────────────
load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000") # Default to local FastAPI if not set
AUTH_HEADERS = {}
if 'user_token' in st.session_state:
     AUTH_HEADERS = {"Authorization": f"Bearer {st.session_state['user_token']}"}

st.set_page_config(page_title="CAIRN Finder", layout="wide")

# ─── Header ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 6]) # Adjust ratio
with col1:
    try: st.image("https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp", width=60)
    except: st.caption("CAIRN Logo") # Fallback text
with col2: st.title("CAIRN Document Finder")

# ─── Sidebar filters ──────────────────────────────────────────────────────────
st.sidebar.header("Filters")
params = {}
# Text inputs
text_cols = ["document_id", "document_title", "local_backup_name", "tagger", "file_format", "rate_impact", "quality_check", "regulatory_body", "state_region", "docket_number", "document_type", "org_utility_name", "parent_document", "replaces_document", "document_url", "cairn_url", "processing_notes"]
for col in text_cols:
    if f"filter_{col}" not in st.session_state: st.session_state[f"filter_{col}"] = ""
    st.session_state[f"filter_{col}"] = st.sidebar.text_input(col.replace("_"," ").title(), value=st.session_state[f"filter_{col}"], key=f"input_{col}")
    if st.session_state[f"filter_{col}"]: params[col] = st.session_state[f"filter_{col}"]
# Date inputs
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
# List inputs
list_cols = ["additional_keywords", "ders", "utility_reform", "customer_classes", "energy_resources", "related_documents", "relationship_types"]
for col in list_cols:
    if f"filter_{col}" not in st.session_state: st.session_state[f"filter_{col}"] = ""
    st.session_state[f"filter_{col}"] = st.sidebar.text_input(col.replace("_"," ").title() + " (comma-sep)", value=st.session_state[f"filter_{col}"], key=f"input_{col}")
    s = st.session_state[f"filter_{col}"]
    if s: params[col] = [x.strip() for x in s.split(",") if x.strip()]
# Boolean input
if f"filter_physical_climate_risk" not in st.session_state: st.session_state[f"filter_physical_climate_risk"] = False
st.session_state[f"filter_physical_climate_risk"] = st.sidebar.checkbox("Physical Climate Risk", value=st.session_state[f"filter_physical_climate_risk"], key="input_physical_climate_risk")
if st.session_state[f"filter_physical_climate_risk"]: params["physical_climate_risk"] = True
# Pagination & Options
st.sidebar.header("Options")
if 'page' not in st.session_state: st.session_state.page = 1
if 'page_size' not in st.session_state: st.session_state.page_size = 20
st.session_state.page = st.sidebar.number_input("Page Number", min_value=1, value=st.session_state.page, key="input_page")
st.session_state.page_size = st.sidebar.number_input("Page Size", min_value=1, max_value=200, value=st.session_state.page_size, key="input_page_size")
params["page"], params["page_size"] = st.session_state.page, st.session_state.page_size
# Load Button
load_button_pressed = st.sidebar.button("Load Documents", type="primary")

# ─── Main Area with Tabs ───────────────────────────────────────────────────────
about_tab, search_basic_tab, search_advanced_tab, tags_tab = st.tabs([
    "ℹ️ About CAIRN",
    "🔍 Search (Basic)", # Updated Tab Name
    "🔬 Search (Advanced)", # Updated Tab Name
    "🏷️ Tag Definitions"
])

# --- Common Data Loading Logic ---
# This runs only when the button is pressed, updating session state
if load_button_pressed:
    with st.spinner('Fetching documents from CAIRN API...'):
        try:
            resp = requests.get(f"{API_URL}/documents", params=params, headers=AUTH_HEADERS, timeout=45)
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
                else:
                    for lc in list_cols:
                        if lc in df.columns: df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                    rename_map = {
                         "id": "PK_ID", "document_id": "File ID", "local_backup_name": "Local Backup Name",
                         "document_title": "Document Title", "published_date": "Published Date",
                         "document_author": "Document Author", "org_utility_name": "Org/Utility Name",
                         "docket_number": "Docket Number", "document_type": "Document Type",
                         "document_subtype": "Document Subtype", "document_url": "Document URL",
                         "cairn_url": "CAIRN URL", "rate_impact": "Rate Impact",
                         "utility_reform": "Utility Reform", "energy_resources": "Energy Resources",
                         "customer_classes": "Customer Classes", "ders": "DERs",
                         "physical_climate_risk": "Physical Climate Risk",
                         "additional_keywords": "Additional Keywords", "tagger": "Tagger",
                         "date_tagged": "Date Tagged", "quality_check": "Quality Check",
                         "processing_notes": "Processing Notes", "state_region": "State/Region",
                         "regulatory_body": "Regulatory Body", "jurisdiction_type": "Jurisdiction Type",
                         "parent_document": "Parent Document", "related_documents": "Related Documents",
                         "replaces_document": "Replaces Document", "relationship_types": "Relationship Types",
                    }
                    all_possible_cols = list(rename_map.keys())
                    cols_in_df = [col for col in all_possible_cols if col in df.columns]
                    df_processed = df[cols_in_df]
                    df_renamed = df_processed.rename(columns=rename_map)
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


# --- Tab Implementations ---

with about_tab:
    # --- Full About Content ---
    st.markdown("""
    ## What is CAIRN?

    Inspired by the stone cairns that guide hikers through uncertain terrain, **Project CAIRN** is designed to help you navigate the complex landscape of energy utility regulation. Built by 9zero members and partners, CAIRN uses artificial intelligence (AI) to collect, categorize, and unlock insights from the vast collection of documents produced by utilities, regulators, and other stakeholders. Our goal is to foster collaboration and innovation by making this crucial information more accessible and understandable.

    ### Why Do Utility Documents Matter?

    Every day, decisions impacting our energy future are documented in regulatory filings, dockets, integrated resource plans (IRPs), rate cases, and policy directives. These documents determine:

    * **Your Energy Bills:** How rates are set and what infrastructure costs you pay for.
    * **Grid Reliability:** Plans for maintaining and upgrading power lines and generation to keep the lights on, especially during extreme weather.
    * **Climate Action:** How utilities plan to reduce emissions, integrate renewable energy (like solar and wind), and adapt to climate change risks (like wildfires and heatwaves).
    * **New Technologies:** The adoption process for things like electric vehicles (EVs), battery storage, and smart grid technologies.

    However, these documents are often incredibly dense, technical, numerous, and scattered across different agencies and websites. Tracking developments or finding specific information can be a major challenge, slowing down progress and innovation.

    ### How CAIRN Helps

    CAIRN tackles this complexity head-on. We are building a system that:

    1.  **Stores Documents:** Collects and storing documents in a single shared database (using Backblaze B2).
    2.  **Organizes & Tags:** Uses humans and AI (via Supabase/PostgreSQL and Google Sheets integration) to categorize documents by utility, topic, date, document type, and other key factors. See the **🏷️ Tag Definitions** tab for details on searchable fields.
    3.  **Enables Targeted Search:** Allows you to filter and search the database (using the **🔍 Search Documents** tabs!) to find precisely the documents you need. *(Roadmap includes semantic search and RAG)*.

    By streamlining access to this information, CAIRN aims to help environmental advocates, utility planners, regulatory analysts, researchers, and concerned citizens understand the landscape, track progress, compare approaches, and contribute more effectively to shaping our energy future.

    ### Getting Started: How to Query the CAIRN Database

    1.  Review the **🏷️ Tag Definitions** tab to understand the available search fields and common terms.
    2.  Click on the **🔍 Search (Basic)** or **🔬 Search (Advanced)** tab.
    3.  Use the **filters in the sidebar** on the left to narrow down the vast collection of documents.
    4.  Once filters are set, click the **"Load Documents"** button in the sidebar.
    5.  The table will populate within the chosen search tab. You can then sort, filter, search, download (single files), and view details.
    """)

# --- Basic Search Tab ---
with search_basic_tab:
    st.info("Basic search view. Use sidebar filters and click 'Load Documents'. Select a single row to enable download.")

    # Display error messages if any occurred during fetch
    if st.session_state.get('api_error'): st.error(st.session_state.api_error)
    if st.session_state.get('data_message'): st.warning(st.session_state.data_message)

    # Display results if available in session state
    if 'search_results_df' in st.session_state and not st.session_state.search_results_df.empty:
        st.write(f"Showing **{len(st.session_state.search_results_df)}** of **{st.session_state.total_docs}** total documents (Page {st.session_state.current_page_for_display} of {st.session_state.total_pages})")

        cols_to_display_basic = ["PK_ID"] + BASIC_COLUMNS_TO_SHOW # PK_ID needed for actions
        df_basic_view = st.session_state.search_results_df[[col for col in cols_to_display_basic if col in st.session_state.search_results_df.columns]]

        search_term_basic = st.text_input("🔎 Quick Search basic results", key="quick_search_input_basic")
        df_display_basic = df_basic_view
        if search_term_basic:
            mask = df_display_basic.apply(lambda row: row.astype(str).str.contains(search_term_basic, case=False, na=False).any(), axis=1)
            df_display_basic = df_display_basic[mask]
            if not df_display_basic.empty: st.write(f"Showing {len(df_display_basic)} rows matching quick search.")

        if not df_display_basic.empty:
            gb_basic = GridOptionsBuilder.from_dataframe(df_display_basic)
            gb_basic.configure_default_column(sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150, filter=True, floatingFilter=True)
            gb_basic.configure_column("PK_ID", hide=True)
            gb_basic.configure_side_bar(filters_panel=False, columns_panel=True)
            gb_basic.configure_pagination(paginationAutoPageSize=False, paginationPageSize=st.session_state.page_size)
            gb_basic.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True)
            gb_basic.configure_grid_options(domLayout='normal') # Removed getRowId here, adding below
            grid_opts_basic = gb_basic.build()

            # *** FIX for Selection: Add getRowId using JsCode ***
            get_row_id_basic = JsCode("""function(params) { return params.data.PK_ID; }""")
            grid_opts_basic['getRowId'] = get_row_id_basic

            grid_response_basic = AgGrid(
                df_display_basic, gridOptions=grid_opts_basic, key='document_grid_basic',
                height=600, width='100%', columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
                update_mode=GridUpdateMode.SELECTION_CHANGED, data_return_mode=DataReturnMode.AS_INPUT,
                allow_unsafe_jscode=True, enable_enterprise_modules=False, reload_data=False
            )

            # --- Actions Area Below Basic Grid ---
            st.markdown("---")
            csv_data_basic = df_display_basic.to_csv(index=False).encode('utf-8')
            st.download_button(label="📄 Download Basic View as CSV", data=csv_data_basic, file_name="cairn_basic_export.csv", mime="text/csv", key='csv_download_basic')
            st.markdown("---")

            selected_rows_basic = grid_response_basic.get("selected_rows")
            col_act_basic_1, col_act_basic_2 = st.columns([1, 3])

            with col_act_basic_1:
                if selected_rows_basic and isinstance(selected_rows_basic, list):
                    num_selected = len(selected_rows_basic)
                    if num_selected == 1:
                        selected_doc = selected_rows_basic[0]; doc_pk_id = selected_doc.get('PK_ID')
                        doc_title = selected_doc.get('Document Title', f'File ID {selected_doc.get("File ID", doc_pk_id)}')
                        if doc_pk_id:
                            button_label = f"⬇️ Download Selected: {doc_title[:40]}..."
                            button_key = f"download_single_basic_{doc_pk_id}"
                            if st.button(button_label, key=button_key):
                                download_url_endpoint = f"{API_URL}/documents/{doc_pk_id}/download-url"
                                try:
                                    with st.spinner(f"Generating link..."):
                                        dl_resp = requests.get(download_url_endpoint, headers=AUTH_HEADERS, timeout=20); dl_resp.raise_for_status()
                                        url = dl_resp.json().get("url")
                                        if url: st.session_state[f'download_link_basic_{doc_pk_id}'] = url
                                        else: st.error("Invalid link returned."); st.session_state.pop(f'download_link_basic_{doc_pk_id}', None)
                                except requests.exceptions.HTTPError as http_err:
                                     detail = f"Server error ({http_err.response.status_code})"; try: detail = http_err.response.json().get('detail', detail); except: pass
                                     st.error(f"Download Failed: {detail}"); st.session_state.pop(f'download_link_basic_{doc_pk_id}', None)
                                except Exception as e: st.error(f"Error: {e}"); st.session_state.pop(f'download_link_basic_{doc_pk_id}', None)

                            link_key = f'download_link_basic_{doc_pk_id}'
                            if st.session_state.get(link_key):
                                link = st.session_state.get(link_key)
                                st.markdown(f'✅ Link ready: <a href="{link}" target="_blank" download>Click here to download "{doc_title[:50]}..."</a>', unsafe_allow_html=True)
                                del st.session_state[link_key]
                    elif num_selected > 1:
                        st.button(f"⬇️ Download {num_selected} Selected as ZIP", key="download_selected_zip_basic", disabled=True); st.caption("(ZIP download not implemented)")

            with col_act_basic_2:
                 if selected_rows_basic and isinstance(selected_rows_basic, list) and len(selected_rows_basic) > 0:
                     st.markdown("#### Selected Document Details")
                     try:
                        sel_df = pd.DataFrame(selected_rows_basic).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                        if len(sel_df) == 1: st.dataframe(sel_df.iloc[0], use_container_width=True)
                        else: st.dataframe(sel_df, use_container_width=True, height=200)
                     except Exception as detail_e: st.error(f"Error displaying details: {detail_e}")
        else:
             if search_term_basic: st.caption("No results match the quick search term in this view.")


# --- Advanced Search Tab ---
with search_advanced_tab:
    st.info("Advanced search view with all columns. Use sidebar filters and click 'Load Documents'. Select a single row to enable download.")

    # Display error messages if any occurred during fetch
    if st.session_state.get('api_error'): st.error(st.session_state.api_error)
    if st.session_state.get('data_message'): st.warning(st.session_state.data_message)

    # Display results if available in session state
    if 'search_results_df' in st.session_state and not st.session_state.search_results_df.empty:
        st.write(f"Showing **{len(st.session_state.search_results_df)}** of **{st.session_state.total_docs}** total documents (Page {st.session_state.current_page_for_display} of {st.session_state.total_pages})")

        df_advanced_view = st.session_state.search_results_df # Use full DataFrame

        search_term_advanced = st.text_input("🔎 Quick Search advanced results", key="quick_search_input_advanced")
        df_display_advanced = df_advanced_view
        if search_term_advanced:
            mask = df_display_advanced.apply(lambda row: row.astype(str).str.contains(search_term_advanced, case=False, na=False).any(), axis=1)
            df_display_advanced = df_display_advanced[mask]
            if not df_display_advanced.empty: st.write(f"Showing {len(df_display_advanced)} rows matching quick search.")

        if not df_display_advanced.empty:
            gb_advanced = GridOptionsBuilder.from_dataframe(df_display_advanced)
            gb_advanced.configure_default_column(sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150, filter=True, floatingFilter=True)
            gb_advanced.configure_column("PK_ID", hide=True)
            if "Document URL" in df_display_advanced.columns: gb_advanced.configure_column("Document URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''')
            if "CAIRN URL" in df_display_advanced.columns: gb_advanced.configure_column("CAIRN URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''')
            gb_advanced.configure_side_bar(filters_panel=True, columns_panel=True)
            gb_advanced.configure_pagination(paginationAutoPageSize=False, paginationPageSize=st.session_state.page_size)
            gb_advanced.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True)
            gb_advanced.configure_grid_options(domLayout='normal') # Removed getRowId here, adding below
            grid_opts_advanced = gb_advanced.build()

            # *** FIX for Selection: Add getRowId using JsCode ***
            get_row_id_advanced = JsCode("""function(params) { return params.data.PK_ID; }""")
            grid_opts_advanced['getRowId'] = get_row_id_advanced

            grid_response_advanced = AgGrid(
                df_display_advanced, gridOptions=grid_opts_advanced, key='document_grid_advanced',
                height=600, width='100%', columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
                update_mode=GridUpdateMode.SELECTION_CHANGED, data_return_mode=DataReturnMode.AS_INPUT,
                allow_unsafe_jscode=True, enable_enterprise_modules=False, reload_data=False
            )

            # --- Actions Area Below Advanced Grid ---
            st.markdown("---")
            csv_data_advanced = df_display_advanced.to_csv(index=False).encode('utf-8')
            st.download_button(label="📄 Download Advanced View as CSV", data=csv_data_advanced, file_name="cairn_advanced_export.csv", mime="text/csv", key='csv_download_advanced')
            st.markdown("---")

            selected_rows_advanced = grid_response_advanced.get("selected_rows")
            col_act_adv_1, col_act_adv_2 = st.columns([1, 3])

            with col_act_adv_1:
                if selected_rows_advanced and isinstance(selected_rows_advanced, list):
                    num_selected = len(selected_rows_advanced)
                    if num_selected == 1:
                        selected_doc = selected_rows_advanced[0]; doc_pk_id = selected_doc.get('PK_ID')
                        doc_title = selected_doc.get('Document Title', f'File ID {selected_doc.get("File ID", doc_pk_id)}')
                        if doc_pk_id:
                            button_label = f"⬇️ Download Selected: {doc_title[:40]}..."
                            button_key = f"download_single_advanced_{doc_pk_id}"
                            if st.button(button_label, key=button_key):
                                # (Identical API call and error handling logic)
                                download_url_endpoint = f"{API_URL}/documents/{doc_pk_id}/download-url"
                                try:
                                    with st.spinner(f"Generating link..."):
                                        dl_resp = requests.get(download_url_endpoint, headers=AUTH_HEADERS, timeout=20); dl_resp.raise_for_status()
                                        url = dl_resp.json().get("url")
                                        if url: st.session_state[f'download_link_advanced_{doc_pk_id}'] = url
                                        else: st.error("Invalid link returned."); st.session_state.pop(f'download_link_advanced_{doc_pk_id}', None)
                                except requests.exceptions.HTTPError as http_err:
                                     detail = f"Server error ({http_err.response.status_code})"; try: detail = http_err.response.json().get('detail', detail); except: pass
                                     st.error(f"Download Failed: {detail}"); st.session_state.pop(f'download_link_advanced_{doc_pk_id}', None)
                                except Exception as e: st.error(f"Error: {e}"); st.session_state.pop(f'download_link_advanced_{doc_pk_id}', None)

                            link_key = f'download_link_advanced_{doc_pk_id}'
                            if st.session_state.get(link_key):
                                link = st.session_state.get(link_key)
                                st.markdown(f'✅ Link ready: <a href="{link}" target="_blank" download>Click here to download "{doc_title[:50]}..."</a>', unsafe_allow_html=True)
                                del st.session_state[link_key]
                    elif num_selected > 1:
                        st.button(f"⬇️ Download {num_selected} Selected as ZIP", key="download_selected_zip_advanced", disabled=True); st.caption("(ZIP download not implemented)")

            with col_act_adv_2:
                 if selected_rows_advanced and isinstance(selected_rows_advanced, list) and len(selected_rows_advanced) > 0:
                     st.markdown("#### Selected Document Details")
                     try:
                        sel_df = pd.DataFrame(selected_rows_advanced).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                        if len(sel_df) == 1: st.dataframe(sel_df.iloc[0], use_container_width=True)
                        else: st.dataframe(sel_df, use_container_width=True, height=200)
                     except Exception as detail_e: st.error(f"Error displaying details: {detail_e}")
        else:
             if search_term_advanced: st.caption("No results match the quick search term in this view.")


# --- Tags Tab ---
with tags_tab:
    st.info("""
    This table explains the different fields (tags) used to categorize documents in CAIRN.
    You can use the filters in the sidebar (under the search tabs) to search based on these fields and terms.
    """)

    # Define the COMPLETE tag data without using '...' ellipsis placeholders
    tag_data = {
        'Tag Name (Filter)': [
            "File ID", "Document Title", "Published Date", "Org/Utility Name",
            "Docket Number", "Document Type", "Document Subtype", "Document URL", "CAIRN URL",
            "Rate Impact", "Utility Reform", "Energy Resources", "Customer Classes", "DERs",
            "Physical Climate Risk", "Additional Keywords", "Tagger", "Date Tagged", "Quality Check",
            "Processing Notes", "State/Region", "Regulatory Body", "Jurisdiction Type",
            "Parent Document", "Related Documents", "Replaces Document", "Relationship Types"
            # ,"Document Author" # Uncomment if needed
        ],
        'Description': [
            "Unique identifier for the document record (e.g., C250001)",
            "Full official title of the document",
            "The date the document was published or filed",
            "The primary utility, organization, or agency associated with the document",
            "The official proceeding number (e.g., UE-230810)",
            "The main category or classification of the document",
            "A more specific sub-category of the document",
            "Direct URL link to the original source document webpage (if available)",
            "Direct URL link to the document file stored within the CAIRN system (if available)",
            "Does the document primarily discuss ratepayer bill or tariff impacts? (Yes/No/Partial)",
            "Does the document primarily focus on utility governance or business model changes? (Yes/No/Partial)",
            "Comma-separated list of energy resource types discussed (e.g., gas, solar, storage, EE)",
            "Comma-separated list of customer classes addressed (e.g., residential, C&I, low-income)",
            "Does the document primarily focus on Distributed Energy Resources (DERs)? (Yes/No)",
            "Does the document primarily discuss physical climate risks like wildfire, heat, floods? (Yes/No)",
            "Comma-separated list of additional relevant keywords for searching",
            "Identifier for the person or team who applied the tags",
            "The date the tags were applied or last updated",
            "Has the accuracy of the document's metadata been verified? (Complete/Pending/Needs Review)",
            "Internal notes regarding document processing, OCR issues, or anomalies",
            "The primary geographic state or region the document pertains to",
            "The primary regulatory agency with jurisdiction (e.g., PUC, FERC)",
            "The level of regulatory authority (e.g., State-Level, National)",
            "The File ID of a parent document this document belongs to (e.g., for appendices)",
            "Comma-separated File IDs of other documents related to this one",
            "The File ID of a document that this document replaces or supersedes",
            "Describes the relationship to parent/related documents (e.g., Appendix, Comment)"
            # ,"The individual, firm, or entity that authored the document"
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
             "Appendix, IRP_Comment, Staff_Comment, Errata"
             # ,"Text"
         ]
    }

    # Create and display the DataFrame
    try:
        tag_definitions_df = pd.DataFrame(tag_data)
        st.dataframe(tag_definitions_df, use_container_width=True, height=600)
    except ValueError as ve:
        st.error(f"Error creating Tag Definitions table: {ve}. Check lists in tag_data dictionary.")
    except Exception as e:
         st.error(f"An unexpected error occurred displaying Tag Definitions: {e}")

# Optional Footer
# st.markdown("---")
# st.caption("CAIRN Project v1.4 | Powered by Streamlit")