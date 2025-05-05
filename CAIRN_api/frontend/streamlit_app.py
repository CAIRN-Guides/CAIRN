# frontend/app.py
# Full drop-in replacement code incorporating fixes

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

# ─── Load env & page setup ─────────────────────────────────────────────────────
load_dotenv()
# Ensure the API_URL points to your Render backend URL (or localhost for testing)
API_URL = os.getenv("API_URL", "http://localhost:8000") # Default to local FastAPI if not set
# Example Auth - replace with your actual auth mechanism if implemented
# Assume token might be stored in session state after login
AUTH_HEADERS = {}
if 'user_token' in st.session_state:
     AUTH_HEADERS = {"Authorization": f"Bearer {st.session_state['user_token']}"}

st.set_page_config(page_title="CAIRN Finder", layout="wide")

# ─── Header ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 6]) # Adjust ratio
with col1:
    # Consider adding error handling for image loading
    try:
        st.image("https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp", width=60)
    except Exception as img_e:
        st.caption("CAIRN Logo") # Fallback text
        # st.error(f"Could not load logo: {img_e}")
with col2:
    st.title("CAIRN Document Finder")

# ─── Sidebar filters (Keep existing sidebar code) ─────────────────────────────
st.sidebar.header("Filters")
params = {}
# --- Text inputs ---
text_cols = [
    "document_id", "document_title", "local_backup_name", "tagger",
    "file_format", "rate_impact", "quality_check", "regulatory_body",
    "state_region", "docket_number", "document_type", "org_utility_name",
    "parent_document", "replaces_document", "document_url", "cairn_url",
    "processing_notes"
]
for col in text_cols:
    # Use session state to preserve filter values across reruns
    if f"filter_{col}" not in st.session_state:
        st.session_state[f"filter_{col}"] = ""
    st.session_state[f"filter_{col}"] = st.sidebar.text_input(
        col.replace("_"," ").title(),
        value=st.session_state[f"filter_{col}"],
        key=f"input_{col}"
    )
    if st.session_state[f"filter_{col}"]:
        params[col] = st.session_state[f"filter_{col}"]

# --- Date inputs ---
date_fields = ["published_date", "date_tagged", "last_synced_at", "updated_at"]
for col in date_fields:
     if f"filter_{col}" not in st.session_state:
         st.session_state[f"filter_{col}"] = None
     # Convert stored string back to date object if needed, handle None
     current_val = None
     if st.session_state[f"filter_{col}"] is not None:
         try:
            # Assuming ISO format string was stored
            current_val = date.fromisoformat(st.session_state[f"filter_{col}"])
         except (TypeError, ValueError):
             current_val = None # Reset if conversion fails

     d = st.sidebar.date_input(col.replace("_"," ").title(), value=current_val, key=f"input_{col}")
     if d:
         params[col] = d.isoformat()
         st.session_state[f"filter_{col}"] = d.isoformat() # Store as string
     else:
          st.session_state[f"filter_{col}"] = None # Ensure None is stored if cleared


# --- List inputs (comma-separated) ---
list_cols = [
    "additional_keywords", "ders", "utility_reform",
    "customer_classes", "energy_resources",
    "related_documents", "relationship_types"
]
for col in list_cols:
    if f"filter_{col}" not in st.session_state:
        st.session_state[f"filter_{col}"] = ""
    st.session_state[f"filter_{col}"] = st.sidebar.text_input(
        col.replace("_"," ").title() + " (comma-sep)",
        value=st.session_state[f"filter_{col}"],
        key=f"input_{col}"
    )
    s = st.session_state[f"filter_{col}"]
    if s:
        params[col] = [x.strip() for x in s.split(",") if x.strip()]

# --- Boolean input ---
if f"filter_physical_climate_risk" not in st.session_state:
    st.session_state[f"filter_physical_climate_risk"] = False
st.session_state[f"filter_physical_climate_risk"] = st.sidebar.checkbox(
    "Physical Climate Risk",
    value=st.session_state[f"filter_physical_climate_risk"],
    key="input_physical_climate_risk"
)
if st.session_state[f"filter_physical_climate_risk"]:
    params["physical_climate_risk"] = True


# --- Pagination & Options ---
st.sidebar.header("Options")
if 'page' not in st.session_state: st.session_state.page = 1
if 'page_size' not in st.session_state: st.session_state.page_size = 20

st.session_state.page = st.sidebar.number_input("Page Number", min_value=1, value=st.session_state.page, key="input_page")
st.session_state.page_size = st.sidebar.number_input("Page Size", min_value=1, max_value=200, value=st.session_state.page_size, key="input_page_size")
params["page"] = st.session_state.page
params["page_size"] = st.session_state.page_size

# --- Load Button ---
load_button_pressed = st.sidebar.button("Load Documents", type="primary")

# ─── Main Area with Tabs ───────────────────────────────────────────────────────
about_tab, search_tab, tags_tab = st.tabs([
    "ℹ️ About CAIRN",
    "🔍 Search Documents",
    "🏷️ Tag Definitions"
])

with about_tab:
    # --- Keep existing About content ---
    # (Assuming your About content is here)
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
    3.  **Enables Targeted Search:** Allows you to filter and search the database (using the **🔍 Search Documents** tab!) to find precisely the documents you need. *(Roadmap includes semantic search and RAG)*.

    By streamlining access to this information, CAIRN aims to help environmental advocates, utility planners, regulatory analysts, researchers, and concerned citizens understand the landscape, track progress, compare approaches, and contribute more effectively to shaping our energy future.

    ### Getting Started: How to Query the CAIRN Database

    1.  Review the **🏷️ Tag Definitions** tab to understand the available search fields and common terms.
    2.  Click on the **🔍 Search Documents** tab.
    3.  Use the **filters in the sidebar** on the left to narrow down the vast collection of documents.
    4.  Once filters are set, click the **"Load Documents"** button in the sidebar.
    5.  The table will populate within the **🔍 Search Documents** tab. You can then sort, filter, search, download, and view details.
    """)

with search_tab:
    st.info("Use the filters in the sidebar and click 'Load Documents' to fetch and display data here.")

    # Initialize session state for search results if it doesn't exist
    if 'search_results_df' not in st.session_state:
        st.session_state.search_results_df = pd.DataFrame()
    if 'total_docs' not in st.session_state:
        st.session_state.total_docs = 0
    if 'total_pages' not in st.session_state:
        st.session_state.total_pages = 1
    if 'current_page_for_display' not in st.session_state:
         st.session_state.current_page_for_display = 1

    # Fetch data ONLY when the button is pressed
    if load_button_pressed:
        with st.spinner('Fetching documents from CAIRN API...'):
            try:
                # Use AUTH_HEADERS if authentication is implemented
                resp = requests.get(f"{API_URL}/documents", params=params, headers=AUTH_HEADERS, timeout=45)
                resp.raise_for_status() # Raises HTTPError for bad responses (4XX, 5XX)

                docs_data = resp.json()
                docs = docs_data.get("data", [])
                st.session_state.total_docs = docs_data.get("total_count", len(docs))
                st.session_state.current_page_for_display = params.get('page', 1)
                page_size = params.get('page_size', 20)
                st.session_state.total_pages = (st.session_state.total_docs + page_size - 1) // page_size if st.session_state.total_docs > 0 else 1

                if not docs:
                    st.warning("No documents found matching your criteria.")
                    st.session_state.search_results_df = pd.DataFrame() # Clear previous results
                else:
                    # --- Build DataFrame & process ---
                    df = pd.DataFrame(docs)
                    if 'id' not in df.columns:
                         st.error("Critical Error: 'id' column missing from API response. Downloads will fail.")
                         st.stop()

                    for lc in list_cols:
                        if lc in df.columns:
                            df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                    cols_order_original = [
                        "id", "document_id", "local_backup_name", "document_title", "published_date",
                        "org_utility_name", "docket_number", "document_type", "document_subtype",
                        "document_url", "cairn_url", "rate_impact", "utility_reform",
                        "energy_resources", "customer_classes", "ders",
                        "physical_climate_risk", "additional_keywords", "tagger",
                        "date_tagged", "quality_check", "processing_notes",
                        "state_region", "regulatory_body", "jurisdiction_type",
                        "parent_document", "related_documents", "replaces_document",
                        "relationship_types"
                    ]
                    cols_available = [col for col in cols_order_original if col in df.columns]
                    df_processed = df[cols_available]

                    rename_map = {
                         "id": "PK_ID", # Rename internal ID for display logic
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
                    df_renamed = df_processed.rename(columns={k: v for k, v in rename_map.items() if k in df_processed.columns})
                    st.session_state.search_results_df = df_renamed

            except requests.exceptions.RequestException as e:
                st.error(f"API Request Failed: {e}")
                st.session_state.search_results_df = pd.DataFrame()
            except Exception as e:
                st.error(f"An error occurred while processing data: {e}")
                import traceback
                st.error(traceback.format_exc())
                st.session_state.search_results_df = pd.DataFrame()

    # --- Display Results Area ---
    # This section now runs on every rerun if results exist in session state
    if not st.session_state.search_results_df.empty:
        st.write(f"Showing **{len(st.session_state.search_results_df)}** of **{st.session_state.total_docs}** total documents (Page {st.session_state.current_page_for_display} of {st.session_state.total_pages})")

        # --- Quick Search ---
        search_term = st.text_input("🔎 Quick Search current results", key="quick_search_input_main") # Unique key
        df_display = st.session_state.search_results_df
        if search_term:
            mask = df_display.apply(lambda row: row.astype(str).str.contains(search_term, case=False, na=False).any(), axis=1)
            df_display = df_display[mask]
            st.write(f"Showing {len(df_display)} rows matching quick search.") # Feedback on quick search

        # --- Configure AgGrid ---
        gb = GridOptionsBuilder.from_dataframe(df_display)
        gb.configure_default_column(
            sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150,
            filter=True, floatingFilter=True
        )
        if "PK_ID" in df_display.columns:
             gb.configure_column("PK_ID", hide=True) # Hide internal primary key
        if "Document URL" in df_display.columns:
            gb.configure_column("Document URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''')
        if "CAIRN URL" in df_display.columns:
            gb.configure_column("CAIRN URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''')

        gb.configure_side_bar(filters_panel=True, columns_panel=True)
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=st.session_state.page_size) # Client-side pagination for view
        gb.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True)
        gb.configure_grid_options(domLayout='normal')
        grid_opts = gb.build()

        # --- Display AgGrid ---
        grid_response = AgGrid(
            df_display,
            gridOptions=grid_opts,
            key='document_grid_main', # Unique key
            height=600,
            width='100%',
            columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT,
            allow_unsafe_jscode=True,
            enable_enterprise_modules=False,
            reload_data=True # Reload data if df_display changes (e.g. quick search)
                             # Set to False if causing issues, manage updates manually
        )

        # --- Actions Area Below Grid ---
        st.markdown("---") # Separator before actions

        # --- Download current view as CSV (Relocated) ---
        # This button is always available if df_display (grid data) is not empty
        if not df_display.empty:
            csv_data = df_display.to_csv(index=False).encode('utf-8')
            st.download_button(
                 label="📄 Download Current View as CSV",
                 data=csv_data,
                 file_name="cairn_documents_export.csv",
                 mime="text/csv",
                 key='csv_download_view_main' # Unique key
            )
            st.markdown("---") # Optional separator after CSV button

        # --- Selection-dependent Actions ---
        # Use .get() for safer access - returns None if key is missing or grid hasn't fully initialized
        selected_rows = grid_response.get("selected_rows")

        col_act_1, col_act_2 = st.columns([1, 3]) # Layout columns for selection actions/details

        with col_act_1:
            # --- Download Button Logic (SINGLE CORRECT BLOCK) ---
            # Check if selected_rows is a non-None sequence (list) before using len()
            if selected_rows and isinstance(selected_rows, list):
                num_selected = len(selected_rows)

                if num_selected == 1:
                    # --- Single Selection Download Button ---
                    selected_doc = selected_rows[0]
                    # Get the original primary key ('id'), checking for PK_ID rename first
                    doc_pk_id = selected_doc.get('PK_ID') or selected_doc.get('id')
                    doc_title = selected_doc.get('Document Title', f'File ID {selected_doc.get("File ID", doc_pk_id)}')

                    if doc_pk_id:
                        button_label = f"⬇️ Download Selected: {doc_title[:40]}..."
                        button_key = f"download_single_{doc_pk_id}" # Unique key

                        if st.button(button_label, key=button_key):
                            download_url_endpoint = f"{API_URL}/documents/{doc_pk_id}/download-url"
                            try:
                                with st.spinner(f"Generating secure link for '{doc_title[:30]}...'"):
                                    dl_resp = requests.get(download_url_endpoint, headers=AUTH_HEADERS, timeout=20)
                                    dl_resp.raise_for_status()
                                    download_info = dl_resp.json()
                                    url = download_info.get("url")
                                    if url:
                                        # Store link temporarily in session state to display after rerun
                                        st.session_state[f'download_link_{doc_pk_id}'] = url
                                    else:
                                        st.error("Backend did not return a valid download link.")
                                        # Clean up state if key exists
                                        st.session_state.pop(f'download_link_{doc_pk_id}', None)

                            except requests.exceptions.HTTPError as http_err:
                                 detail = f"Server error ({http_err.response.status_code})"
                                 try: detail = http_err.response.json().get('detail', detail)
                                 except: pass
                                 st.error(f"Download Failed: {detail}")
                                 st.session_state.pop(f'download_link_{doc_pk_id}', None)
                            except requests.exceptions.RequestException as req_err:
                                st.error(f"Network Error: Could not reach download API. {req_err}")
                                st.session_state.pop(f'download_link_{doc_pk_id}', None)
                            except Exception as e:
                                st.error(f"An unexpected error occurred: {e}")
                                st.session_state.pop(f'download_link_{doc_pk_id}', None)

                        # Display the download link IF it was generated in THIS specific button action's rerun cycle
                        # Check session state for the key associated with this specific button
                        link_key = f'download_link_{doc_pk_id}'
                        if st.session_state.get(link_key):
                            link = st.session_state.get(link_key)
                            st.markdown(f'✅ Link ready: <a href="{link}" target="_blank" download>Click here to download "{doc_title[:50]}..."</a>', unsafe_allow_html=True)
                            # Remove the link from state immediately after displaying it
                            del st.session_state[link_key]

                elif num_selected > 1:
                    # --- Multiple Selection Placeholder ---
                    st.button(f"⬇️ Download {num_selected} Selected as ZIP", key="download_selected_zip_main", disabled=True)
                    st.caption("(ZIP download not yet implemented)")
                # Implicit else: num_selected is 0, do nothing specific here for downloads

            # else: # If selected_rows is None or not a list
            #     st.caption("Select a single row to enable download.") # Optional feedback

        with col_act_2:
            # --- Detail pane for selected rows ---
             # Also check if selected_rows is valid here before proceeding
             if selected_rows and isinstance(selected_rows, list) and len(selected_rows) > 0:
                 st.markdown("#### Selected Document Details")
                 try:
                    sel_df = pd.DataFrame(selected_rows).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                    if len(sel_df) == 1:
                        st.dataframe(sel_df.iloc[0], use_container_width=True)
                    else:
                        st.dataframe(sel_df, use_container_width=True, height=200)
                 except Exception as detail_e:
                     st.error(f"Error displaying details: {detail_e}")
             # else: # If no valid rows selected
             #    st.caption("Select rows to see details here.") # Optional feedback


    elif load_button_pressed: # Handle case where button was pressed but API returned no results
         # This message is now implicitly covered by the main display logic:
         # If search_results_df becomes empty, the grid/actions won't show.
         # Adding an explicit message here might be redundant unless desired.
         # st.warning("No documents found for the current filters.")
         pass


with tags_tab:
    # --- Keep existing Tag Definitions content ---
    st.info("""
    This table explains the different fields (tags) used to categorize documents in CAIRN...
    """)
    tag_data = {
        'Tag Name (Filter)': [
            "File ID", "Document Title", "Published Date", "Org/Utility Name",
            "Docket Number", "Document Type", "Document Subtype", "Document URL", "CAIRN URL",
            "Rate Impact", "Utility Reform", "Energy Resources", "Customer Classes", "DERs",
            "Physical Climate Risk", "Additional Keywords", "Tagger", "Date Tagged", "Quality Check",
            "Processing Notes", "State/Region", "Regulatory Body", "Jurisdiction Type",
            "Parent Document", "Related Documents", "Replaces Document", "Relationship Types"
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
            "Direct URL link to the document file stored within the CAIRN system",
            "Does the document primarily discuss ratepayer bill or tariff impacts? (Y/N)",
            "Does the document primarily focus on utility governance or business model changes? (Y/N/Partial)",
            "Comma-separated list of energy resource types discussed (e.g., gas, solar, storage, EE)",
            "Comma-separated list of customer classes addressed (e.g., residential, C&I, low-income)",
            "Does the document primarily focus on Distributed Energy Resources (DERs)? (Y/N)",
            "Does the document primarily discuss physical climate risks like wildfire, heat, floods? (Y/N)",
            "Comma-separated list of additional relevant keywords for searching",
            "Identifier for the person or team who applied the tags",
            "The date the tags were applied or last updated",
            "Has the accuracy of the document's metadata been verified? (Y/N/Pending)",
            "Internal notes regarding document processing, OCR issues, or anomalies",
            "The primary geographic state or region the document pertains to",
            "The primary regulatory agency with jurisdiction (e.g., PUC, FERC)",
            "The level of regulatory authority (e.g., State-Level, National)",
            "The File ID of a parent document this document belongs to (e.g., for appendices)",
            "Comma-separated File IDs of other documents related to this one",
            "The File ID of a document that this document replaces or supersedes",
            "Describes the relationship to parent/related documents (e.g., Appendix, Comment)"
        ],
         'Common Examples / Format': [
             "CYY##### format", "Text", "YYYY-MM-DD", "PSE, Avista, PGE, CAISO, PNNL",
             "UE-#####, UG-#####, etc.", "IRP/ISP, Assessment, Comment, Report, Regulatory Rate Plan", "Electric IRP, Gas IRP, Comment, Clean_Energy_Party, Integrated Resource Plan", "URL", "URL",
             "Y, N", "Y, N, Partial", "All, Gas, Solar, Storage, EE, Clean_Energy", "All, Residential, C&I", "Y, N",
             "Y, N", "IRP, Resilience, Decarbonization, MYRP", "Text (e.g., Apples)", "YYYY-MM-DD", "Y, N, Pending",
             "Text", "WA, CA, OR, Multi-state, National", "WA_UTC, Oregon PUC, CAISO, FERC, CPUC", "State-Level, National",
             "CYY##### format", "CYY##### format (comma-sep)", "CYY##### format", "Appendix, IRP_Comment, Staff_Comment"
         ]
    }
    tag_definitions_df = pd.DataFrame(tag_data)
    st.dataframe(tag_definitions_df, use_container_width=True, height=600) # Use dataframe for scrollbars

# Optional Footer
# st.markdown("---")
# st.caption("CAIRN Project v1.2 | Powered by Streamlit")