# frontend/app.py
# Full drop-in replacement code - Selection Fix + Basic/Advanced Tabs

import os
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv
from PIL import Image # Keep if used elsewhere
import time # Import time for spinner delays if needed
from datetime import date # Added for date conversion check

# Make sure AgGrid is installed: pip install streamlit-aggrid
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, ColumnsAutoSizeMode

# --- Constants ---
BASIC_COLUMNS_TO_SHOW = ["File ID", "Document Title", "Org/Utility Name", "Document Type", "Published Date"]
# PK_ID is needed internally but will be hidden

# ─── Load env & page setup ─────────────────────────────────────────────────────
load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000")
AUTH_HEADERS = {}
if 'user_token' in st.session_state:
     AUTH_HEADERS = {"Authorization": f"Bearer {st.session_state['user_token']}"}

st.set_page_config(page_title="CAIRN Finder", layout="wide")

# ─── Header ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 6])
with col1:
    try: st.image("https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp", width=60)
    except: st.caption("CAIRN Logo")
with col2: st.title("CAIRN Document Finder")

# ─── Sidebar filters (Keep existing sidebar code) ─────────────────────────────
# (This section remains the same as your last version - Ensure it's correctly placed here)
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

# ─── Main Area with Tabs (UPDATED) ───────────────────────────────────────────
about_tab, search_basic_tab, search_advanced_tab, tags_tab = st.tabs([
    "ℹ️ About CAIRN",
    "🔍 Search Documents (Basic)",
    "🔬 Search Documents (Advanced)", # New Tab
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
                st.session_state.search_results_df = pd.DataFrame() # Clear previous results
                st.session_state.api_error = None # Clear previous errors
                st.session_state.data_message = "No documents found matching your criteria."
            else:
                df = pd.DataFrame(docs)
                if 'id' not in df.columns:
                     # Store error message instead of stopping execution
                     st.session_state.search_results_df = pd.DataFrame()
                     st.session_state.api_error = "Critical Error: 'id' column missing from API response. Downloads will fail."
                     st.session_state.data_message = None
                else:
                    for lc in list_cols: # Flatten lists
                        if lc in df.columns: df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                    # Define mapping from DB columns to display names
                    rename_map = {
                         "id": "PK_ID", # Internal Primary Key - will be hidden
                         "document_id":        "File ID",
                         "local_backup_name":  "Local Backup Name",
                         "document_title":     "Document Title",
                         "published_date":     "Published Date",
                         "document_author":    "Document Author",
                         "org_utility_name":   "Org/Utility Name",
                         "docket_number":      "Docket Number",
                         "document_type":      "Document Type",
                         "document_subtype":   "Document Subtype",
                         "document_url":       "Document URL",
                         "cairn_url":          "CAIRN URL",
                         "rate_impact":        "Rate Impact",
                         "utility_reform":     "Utility Reform",
                         "energy_resources":   "Energy Resources",
                         "customer_classes":   "Customer Classes",
                         "ders":               "DERs",
                         "physical_climate_risk": "Physical Climate Risk",
                         "additional_keywords": "Additional Keywords",
                         "tagger":             "Tagger",
                         "date_tagged":        "Date Tagged",
                         "quality_check":      "Quality Check",
                         "processing_notes":   "Processing Notes",
                         "state_region":       "State/Region",
                         "regulatory_body":    "Regulatory Body",
                         "jurisdiction_type":  "Jurisdiction Type",
                         "parent_document":    "Parent Document",
                         "related_documents":  "Related Documents",
                         "replaces_document":  "Replaces Document",
                         "relationship_types": "Relationship Types",
                    }
                    # Select ALL potentially available columns first
                    all_possible_cols = list(rename_map.keys())
                    cols_in_df = [col for col in all_possible_cols if col in df.columns]
                    df_processed = df[cols_in_df]
                    # Apply renaming
                    df_renamed = df_processed.rename(columns=rename_map)
                    # Store processed DataFrame in session state
                    st.session_state.search_results_df = df_renamed
                    st.session_state.api_error = None # Clear previous errors
                    st.session_state.data_message = None # Clear no data message


        except requests.exceptions.RequestException as e:
            st.session_state.search_results_df = pd.DataFrame()
            st.session_state.api_error = f"API Request Failed: {e}"
            st.session_state.data_message = None
        except Exception as e:
            st.session_state.search_results_df = pd.DataFrame()
            st.session_state.api_error = f"An error occurred while processing data: {e}"
            st.session_state.data_message = None
            # Optionally log full traceback to console or file, not usually shown to user
            # import traceback
            # print(traceback.format_exc())


# --- Tab Implementations ---

with about_tab:
    # (Keep existing About content)
    st.markdown("...") # Truncated for brevity

# --- Function to Display Grid and Actions (to reduce duplication) ---
# Note: Refactoring into functions is ideal, but for a quick drop-in,
# we will duplicate the logic with unique keys first.
# Consider refactoring later for maintainability.

# --- Basic Search Tab ---
with search_basic_tab:
    st.info("Basic search view. Use sidebar filters and click 'Load Documents'.")

    # Display error messages if any occurred during fetch
    if st.session_state.get('api_error'):
        st.error(st.session_state.api_error)
    if st.session_state.get('data_message'):
        st.warning(st.session_state.data_message)

    # Display results if available in session state
    if 'search_results_df' in st.session_state and not st.session_state.search_results_df.empty:
        st.write(f"Showing **{len(st.session_state.search_results_df)}** of **{st.session_state.total_docs}** total documents (Page {st.session_state.current_page_for_display} of {st.session_state.total_pages})")

        # Filter displayed columns for Basic view
        # Ensure PK_ID is present for actions, even if hidden
        cols_to_display_basic = ["PK_ID"] + BASIC_COLUMNS_TO_SHOW
        # Filter the dataframe to only include available basic columns
        df_basic_view = st.session_state.search_results_df[[col for col in cols_to_display_basic if col in st.session_state.search_results_df.columns]]

        # Quick Search specific to this tab
        search_term_basic = st.text_input("🔎 Quick Search basic results", key="quick_search_input_basic")
        df_display_basic = df_basic_view
        if search_term_basic:
            mask = df_display_basic.apply(lambda row: row.astype(str).str.contains(search_term_basic, case=False, na=False).any(), axis=1)
            df_display_basic = df_display_basic[mask]
            st.write(f"Showing {len(df_display_basic)} rows matching quick search.")

        if not df_display_basic.empty:
            # Configure AgGrid for Basic view
            gb_basic = GridOptionsBuilder.from_dataframe(df_display_basic)
            gb_basic.configure_default_column(sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150, filter=True, floatingFilter=True)
            gb_basic.configure_column("PK_ID", hide=True) # Hide primary key
            # Add clickable links if these columns are present (unlikely in basic view, but safe to include)
            if "Document URL" in df_display_basic.columns: gb_basic.configure_column("Document URL", cellRenderer='''...''') # Same renderer JS
            if "CAIRN URL" in df_display_basic.columns: gb_basic.configure_column("CAIRN URL", cellRenderer='''...''') # Same renderer JS

            gb_basic.configure_side_bar(filters_panel=False, columns_panel=True) # Maybe disable filter panel here?
            gb_basic.configure_pagination(paginationAutoPageSize=False, paginationPageSize=st.session_state.page_size)
            gb_basic.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True)
            # *** FIX for Selection: Add getRowId ***
            gb_basic.configure_grid_options(domLayout='normal', getRowId = 'params.data.PK_ID') # Tell AgGrid how to identify rows
            grid_opts_basic = gb_basic.build()

            # Display AgGrid for Basic view
            grid_response_basic = AgGrid(
                df_display_basic,
                gridOptions=grid_opts_basic,
                key='document_grid_basic', # *** UNIQUE KEY ***
                height=600, width='100%',
                columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                allow_unsafe_jscode=True, enable_enterprise_modules=False,
                reload_data=False # *** FIX for Selection: Set to False ***
            )

            # --- Actions Area Below Basic Grid ---
            st.markdown("---")
            if not df_display_basic.empty: # Check if grid data exists before CSV button
                csv_data_basic = df_display_basic.to_csv(index=False).encode('utf-8')
                st.download_button(label="📄 Download Basic View as CSV", data=csv_data_basic, file_name="cairn_basic_export.csv", mime="text/csv", key='csv_download_basic') # *** UNIQUE KEY ***
                st.markdown("---")

            selected_rows_basic = grid_response_basic.get("selected_rows")
            col_act_basic_1, col_act_basic_2 = st.columns([1, 3])

            with col_act_basic_1:
                if selected_rows_basic and isinstance(selected_rows_basic, list):
                    num_selected = len(selected_rows_basic)
                    if num_selected == 1:
                        selected_doc = selected_rows_basic[0]
                        doc_pk_id = selected_doc.get('PK_ID') # PK_ID should exist
                        doc_title = selected_doc.get('Document Title', f'File ID {selected_doc.get("File ID", doc_pk_id)}')
                        if doc_pk_id:
                            button_label = f"⬇️ Download Selected: {doc_title[:40]}..."
                            button_key = f"download_single_basic_{doc_pk_id}" # *** UNIQUE KEY ***
                            if st.button(button_label, key=button_key):
                                # (Identical API call and error handling logic as before)
                                download_url_endpoint = f"{API_URL}/documents/{doc_pk_id}/download-url"
                                try:
                                    with st.spinner(f"Generating link..."):
                                        dl_resp = requests.get(download_url_endpoint, headers=AUTH_HEADERS, timeout=20)
                                        dl_resp.raise_for_status()
                                        url = dl_resp.json().get("url")
                                        if url: st.session_state[f'download_link_basic_{doc_pk_id}'] = url
                                        else: st.error("Invalid link returned."); st.session_state.pop(f'download_link_basic_{doc_pk_id}', None)
                                except requests.exceptions.HTTPError as http_err:
                                     detail = f"Server error ({http_err.response.status_code})"
                                     try: detail = http_err.response.json().get('detail', detail)
                                     except: pass
                                     st.error(f"Download Failed: {detail}"); st.session_state.pop(f'download_link_basic_{doc_pk_id}', None)
                                except Exception as e: st.error(f"Error: {e}"); st.session_state.pop(f'download_link_basic_{doc_pk_id}', None)

                            link_key = f'download_link_basic_{doc_pk_id}' # *** UNIQUE KEY ***
                            if st.session_state.get(link_key):
                                link = st.session_state.get(link_key)
                                st.markdown(f'✅ Link ready: <a href="{link}" target="_blank" download>Click here to download "{doc_title[:50]}..."</a>', unsafe_allow_html=True)
                                del st.session_state[link_key] # Clear after display

                    elif num_selected > 1:
                        st.button(f"⬇️ Download {num_selected} Selected as ZIP", key="download_selected_zip_basic", disabled=True) # *** UNIQUE KEY ***
                        st.caption("(ZIP download not yet implemented)")

            with col_act_basic_2:
                 if selected_rows_basic and isinstance(selected_rows_basic, list) and len(selected_rows_basic) > 0:
                     st.markdown("#### Selected Document Details")
                     try:
                        sel_df = pd.DataFrame(selected_rows_basic).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                        if len(sel_df) == 1: st.dataframe(sel_df.iloc[0], use_container_width=True)
                        else: st.dataframe(sel_df, use_container_width=True, height=200)
                     except Exception as detail_e: st.error(f"Error displaying details: {detail_e}")
        else:
             if search_term_basic: # Only show if quick search yielded no results
                 st.caption("No results match the quick search term in this view.")


# --- Advanced Search Tab ---
with search_advanced_tab:
    st.info("Advanced search view with all columns. Use sidebar filters and click 'Load Documents'.")

    # Display error messages if any occurred during fetch
    if st.session_state.get('api_error'):
        st.error(st.session_state.api_error)
    if st.session_state.get('data_message'):
        st.warning(st.session_state.data_message)

    # Display results if available in session state
    if 'search_results_df' in st.session_state and not st.session_state.search_results_df.empty:
        st.write(f"Showing **{len(st.session_state.search_results_df)}** of **{st.session_state.total_docs}** total documents (Page {st.session_state.current_page_for_display} of {st.session_state.total_pages})")

        # Use the full renamed dataframe from session state
        df_advanced_view = st.session_state.search_results_df

        # Quick Search specific to this tab
        search_term_advanced = st.text_input("🔎 Quick Search advanced results", key="quick_search_input_advanced") # *** UNIQUE KEY ***
        df_display_advanced = df_advanced_view
        if search_term_advanced:
            mask = df_display_advanced.apply(lambda row: row.astype(str).str.contains(search_term_advanced, case=False, na=False).any(), axis=1)
            df_display_advanced = df_display_advanced[mask]
            st.write(f"Showing {len(df_display_advanced)} rows matching quick search.")

        if not df_display_advanced.empty:
            # Configure AgGrid for Advanced view
            gb_advanced = GridOptionsBuilder.from_dataframe(df_display_advanced)
            gb_advanced.configure_default_column(sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150, filter=True, floatingFilter=True)
            gb_advanced.configure_column("PK_ID", hide=True) # Hide primary key
            # Add clickable links
            if "Document URL" in df_display_advanced.columns: gb_advanced.configure_column("Document URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''')
            if "CAIRN URL" in df_display_advanced.columns: gb_advanced.configure_column("CAIRN URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''')

            gb_advanced.configure_side_bar(filters_panel=True, columns_panel=True)
            gb_advanced.configure_pagination(paginationAutoPageSize=False, paginationPageSize=st.session_state.page_size)
            gb_advanced.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True)
            # *** FIX for Selection: Add getRowId ***
            gb_advanced.configure_grid_options(domLayout='normal', getRowId = 'params.data.PK_ID') # Tell AgGrid how to identify rows
            grid_opts_advanced = gb_advanced.build()

            # Display AgGrid for Advanced view
            grid_response_advanced = AgGrid(
                df_display_advanced,
                gridOptions=grid_opts_advanced,
                key='document_grid_advanced', # *** UNIQUE KEY ***
                height=600, width='100%',
                columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                allow_unsafe_jscode=True, enable_enterprise_modules=False,
                reload_data=False # *** FIX for Selection: Set to False ***
            )

            # --- Actions Area Below Advanced Grid ---
            st.markdown("---")
            if not df_display_advanced.empty: # Check if grid data exists before CSV button
                csv_data_advanced = df_display_advanced.to_csv(index=False).encode('utf-8')
                st.download_button(label="📄 Download Advanced View as CSV", data=csv_data_advanced, file_name="cairn_advanced_export.csv", mime="text/csv", key='csv_download_advanced') # *** UNIQUE KEY ***
                st.markdown("---")

            selected_rows_advanced = grid_response_advanced.get("selected_rows")
            col_act_adv_1, col_act_adv_2 = st.columns([1, 3])

            with col_act_adv_1:
                if selected_rows_advanced and isinstance(selected_rows_advanced, list):
                    num_selected = len(selected_rows_advanced)
                    if num_selected == 1:
                        selected_doc = selected_rows_advanced[0]
                        doc_pk_id = selected_doc.get('PK_ID')
                        doc_title = selected_doc.get('Document Title', f'File ID {selected_doc.get("File ID", doc_pk_id)}')
                        if doc_pk_id:
                            button_label = f"⬇️ Download Selected: {doc_title[:40]}..."
                            button_key = f"download_single_advanced_{doc_pk_id}" # *** UNIQUE KEY ***
                            if st.button(button_label, key=button_key):
                                # (Identical API call and error handling logic as before)
                                download_url_endpoint = f"{API_URL}/documents/{doc_pk_id}/download-url"
                                try:
                                    with st.spinner(f"Generating link..."):
                                        dl_resp = requests.get(download_url_endpoint, headers=AUTH_HEADERS, timeout=20)
                                        dl_resp.raise_for_status()
                                        url = dl_resp.json().get("url")
                                        if url: st.session_state[f'download_link_advanced_{doc_pk_id}'] = url
                                        else: st.error("Invalid link returned."); st.session_state.pop(f'download_link_advanced_{doc_pk_id}', None)
                                except requests.exceptions.HTTPError as http_err:
                                     detail = f"Server error ({http_err.response.status_code})"
                                     try: detail = http_err.response.json().get('detail', detail)
                                     except: pass
                                     st.error(f"Download Failed: {detail}"); st.session_state.pop(f'download_link_advanced_{doc_pk_id}', None)
                                except Exception as e: st.error(f"Error: {e}"); st.session_state.pop(f'download_link_advanced_{doc_pk_id}', None)

                            link_key = f'download_link_advanced_{doc_pk_id}' # *** UNIQUE KEY ***
                            if st.session_state.get(link_key):
                                link = st.session_state.get(link_key)
                                st.markdown(f'✅ Link ready: <a href="{link}" target="_blank" download>Click here to download "{doc_title[:50]}..."</a>', unsafe_allow_html=True)
                                del st.session_state[link_key] # Clear after display

                    elif num_selected > 1:
                        st.button(f"⬇️ Download {num_selected} Selected as ZIP", key="download_selected_zip_advanced", disabled=True) # *** UNIQUE KEY ***
                        st.caption("(ZIP download not yet implemented)")

            with col_act_adv_2:
                 if selected_rows_advanced and isinstance(selected_rows_advanced, list) and len(selected_rows_advanced) > 0:
                     st.markdown("#### Selected Document Details")
                     try:
                        sel_df = pd.DataFrame(selected_rows_advanced).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                        if len(sel_df) == 1: st.dataframe(sel_df.iloc[0], use_container_width=True)
                        else: st.dataframe(sel_df, use_container_width=True, height=200)
                     except Exception as detail_e: st.error(f"Error displaying details: {detail_e}")
        else:
             if search_term_advanced: # Only show if quick search yielded no results
                 st.caption("No results match the quick search term in this view.")


# --- Tags Tab ---
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
            # Note: Added Document Author back based on some earlier definitions, remove if not applicable
            # ,"Document Author"
            # Note: Excluded 'Local Backup Name' and 'PK_ID' as they are likely internal use
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
            "Direct URL link to the document file stored within the CAIRN system (if available)", # Added clarification
            "Does the document primarily discuss ratepayer bill or tariff impacts? (Yes/No/Partial)", # Updated example
            "Does the document primarily focus on utility governance or business model changes? (Yes/No/Partial)",
            "Comma-separated list of energy resource types discussed (e.g., gas, solar, storage, EE)",
            "Comma-separated list of customer classes addressed (e.g., residential, C&I, low-income)",
            "Does the document primarily focus on Distributed Energy Resources (DERs)? (Yes/No)", # Updated example
            "Does the document primarily discuss physical climate risks like wildfire, heat, floods? (Yes/No)", # Updated example
            "Comma-separated list of additional relevant keywords for searching",
            "Identifier for the person or team who applied the tags",
            "The date the tags were applied or last updated",
            "Has the accuracy of the document's metadata been verified? (Complete/Pending/Needs Review)", # Updated example
            "Internal notes regarding document processing, OCR issues, or anomalies",
            "The primary geographic state or region the document pertains to",
            "The primary regulatory agency with jurisdiction (e.g., PUC, FERC)",
            "The level of regulatory authority (e.g., State-Level, National)",
            "The File ID of a parent document this document belongs to (e.g., for appendices)",
            "Comma-separated File IDs of other documents related to this one",
            "The File ID of a document that this document replaces or supersedes",
            "Describes the relationship to parent/related documents (e.g., Appendix, Comment)"
            # ,"The individual, firm, or entity that authored the document" # Description for Document Author
        ],
         'Common Examples / Format': [
             "CYY##### format (e.g., C250001)", # Added example
             "Text",
             "YYYY-MM-DD",
             "PSE, Avista, PGE, CAISO, PNNL",
             "UE-#####, UG-#####, etc.",
             "IRP/ISP, Assessment, Comment, Report, Regulatory Rate Plan Order", # Expanded example
             "Electric IRP, Gas IRP, Comment, Clean_Energy_Party, Integrated Resource Plan",
             "URL",
             "URL (May require login/access)", # Added clarification
             "Yes, No, Partial", # Simpler examples
             "Yes, No, Partial", # Simpler examples
             "All, Gas, Solar, Storage, EE, Clean_Energy, Efficiency", # Added one
             "All, Residential, C&I, Low-Income", # Added one
             "Yes, No", # Simpler examples
             "Yes, No", # Simpler examples
             "IRP, Resilience, Decarbonization, MYRP, Wildfire", # Added one
             "Text (e.g., Apples)",
             "YYYY-MM-DD",
             "Complete, Pending, Needs Review", # Match description
             "Text (e.g., OCR issues found)", # Added example
             "WA, CA, OR, Multi-state, National",
             "WA_UTC, Oregon PUC, CAISO, FERC, CPUC",
             "State-Level, National, Regional", # Added one
             "CYY##### format (e.g., C250002)", # Added example
             "CYY##### format (comma-sep)",
             "CYY##### format",
             "Appendix, IRP_Comment, Staff_Comment, Errata" # Added one
             # ,"Text" # Format for Document Author
         ]
    }

    # Create the DataFrame
    try:
        tag_definitions_df = pd.DataFrame(tag_data)
        # Display the DataFrame
        st.dataframe(tag_definitions_df, use_container_width=True, height=600)
    except ValueError as ve:
        st.error(f"Error creating Tag Definitions table: {ve}")
        st.caption("This usually means the lists in the 'tag_data' dictionary in the code have different lengths.")
    except Exception as e:
         st.error(f"An unexpected error occurred displaying Tag Definitions: {e}")

# Optional Footer
# st.markdown("---")
# st.caption("CAIRN Project v1.3 | Powered by Streamlit")