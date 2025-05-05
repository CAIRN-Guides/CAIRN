# frontend/app.py
import os
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv
from PIL import Image # Keep if used elsewhere
import time # Import time for spinner delays if needed

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
            from datetime import date
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

# Removed include_download_url checkbox
# params["include_download_url"] = st.sidebar.checkbox("Include Download URL", value=False)

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
    st.markdown("""
    ## What is CAIRN?
    ... [rest of your About content] ...
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
                resp = requests.get(f"{API_URL}/documents", params=params, headers=AUTH_HEADERS, timeout=45) # Increased timeout
                resp.raise_for_status() # Raises HTTPError for bad responses (4XX, 5XX)

                docs_data = resp.json()
                docs = docs_data.get("data", [])
                st.session_state.total_docs = docs_data.get("total_count", len(docs)) # Use total_count from response
                st.session_state.current_page_for_display = params.get('page', 1)
                page_size = params.get('page_size', 20)
                st.session_state.total_pages = (st.session_state.total_docs + page_size - 1) // page_size if st.session_state.total_docs > 0 else 1

                if not docs:
                    st.warning("No documents found matching your criteria.")
                    st.session_state.search_results_df = pd.DataFrame() # Clear previous results
                else:
                    # --- Build DataFrame & process ---
                    df = pd.DataFrame(docs)
                    # Ensure 'id' column exists
                    if 'id' not in df.columns:
                         st.error("Critical Error: 'id' column missing from API response. Downloads will fail.")
                         st.stop() # Stop execution if ID is missing

                    # Flatten list columns for display
                    for lc in list_cols:
                        if lc in df.columns:
                            df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                    # Define columns to display and their order
                    # Make sure 'id' is conceptually included, even if not displayed later
                    cols_order_original = [
                        "id", # Include ID for selection lookup, can hide later in AgGrid
                        "document_id", "local_backup_name",
                        "document_title", "published_date", #"document_author", # Add if available
                        "org_utility_name", "docket_number", "document_type", "document_subtype",
                        "document_url", "cairn_url", "rate_impact", "utility_reform",
                        "energy_resources", "customer_classes", "ders",
                        "physical_climate_risk", "additional_keywords", "tagger",
                        "date_tagged", "quality_check", "processing_notes",
                        "state_region", "regulatory_body", "jurisdiction_type",
                        "parent_document", "related_documents", "replaces_document",
                        "relationship_types"
                    ]
                    # Filter to only columns present in the DataFrame
                    cols_available = [col for col in cols_order_original if col in df.columns]
                    df_processed = df[cols_available]

                    # Rename columns for display
                    rename_map = {
                         "id": "PK_ID", # Rename internal ID if desired, or hide later
                         "document_id":        "File ID",
                         "local_backup_name":  "Local Backup Name",
                         # ... keep your existing rename map ...
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
                    # Apply renaming only for columns that exist
                    df_renamed = df_processed.rename(columns={k: v for k, v in rename_map.items() if k in df_processed.columns})

                    # Store processed DataFrame in session state
                    st.session_state.search_results_df = df_renamed

            except requests.exceptions.RequestException as e:
                st.error(f"API Request Failed: {e}")
                st.session_state.search_results_df = pd.DataFrame() # Clear results on error
            except Exception as e:
                st.error(f"An error occurred while processing data: {e}")
                import traceback
                st.error(traceback.format_exc())
                st.session_state.search_results_df = pd.DataFrame() # Clear results on error

    # --- Display Results Area ---
    if not st.session_state.search_results_df.empty:
        st.write(f"Showing **{len(st.session_state.search_results_df)}** of **{st.session_state.total_docs}** total documents (Page {st.session_state.current_page_for_display} of {st.session_state.total_pages})")

        # --- Quick Search ---
        search_term = st.text_input("🔎 Quick Search current results", key="quick_search_input")
        df_display = st.session_state.search_results_df
        if search_term:
            mask = df_display.apply(lambda row: row.astype(str).str.contains(search_term, case=False, na=False).any(), axis=1)
            df_display = df_display[mask]

        # --- Configure AgGrid ---
        gb = GridOptionsBuilder.from_dataframe(df_display)
        gb.configure_default_column(
            # filter="agTextColumnFilter", filterParams={"debounceMs": 300}, # Defer filter application
            sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150,
            filter=True, floatingFilter=True # Enable column filters
        )
        # Hide the internal primary key column if renamed or not needed for direct view
        if "PK_ID" in df_display.columns:
             gb.configure_column("PK_ID", hide=True)
        # Make URLs clickable
        if "Document URL" in df_display.columns:
            gb.configure_column("Document URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''')
        if "CAIRN URL" in df_display.columns:
            gb.configure_column("CAIRN URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''')

        gb.configure_side_bar(filters_panel=True, columns_panel=True)
        # Use client-side pagination within AgGrid for the current page's data
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=st.session_state.page_size)
        gb.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True) # Enable checkboxes
        gb.configure_grid_options(domLayout='normal') # normal layout is often better than autoHeight
        grid_opts = gb.build()

        # Display AgGrid
        grid_response = AgGrid(
            df_display,
            gridOptions=grid_opts,
            key='document_grid', # Consistent key
            height=600,
            width='100%',
            columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS, # Adjust column size
            # update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED, # Listen for changes
            update_mode=GridUpdateMode.SELECTION_CHANGED, # Primarily interested in selection
            data_return_mode=DataReturnMode.AS_INPUT, # Important: return data as it was passed in
            allow_unsafe_jscode=True, # Needed for cellRenderers
            enable_enterprise_modules=False, # Unless you have a license
            reload_data=False # Avoid unnecessary reloads, manage data via session state
        )

        # --- Actions Area Below Grid (Download, Details) ---
        st.markdown("---")
        selected_rows = grid_response["selected_rows"]

        col_act_1, col_act_2 = st.columns([1, 3]) # Layout columns for buttons/details

        with col_act_1:
            # --- Download Button for Single Selection ---
            if len(selected_rows) == 1:
                selected_doc = selected_rows[0]
                # Get the original primary key ('id') using the renamed 'PK_ID' or original 'id'
                doc_pk_id = selected_doc.get('PK_ID') or selected_doc.get('id') # Adjust based on renaming
                doc_title = selected_doc.get('Document Title', f'File ID {selected_doc.get("File ID", doc_pk_id)}')

                if doc_pk_id:
                    if st.button(f"⬇️ Download: {doc_title[:50]}...", key=f"download_{doc_pk_id}"): # Use PK in key
                        download_url_endpoint = f"{API_URL}/documents/{doc_pk_id}/download-url"
                        try:
                            with st.spinner(f"Generating secure link for '{doc_title[:30]}...'"):
                                # Add headers=AUTH_HEADERS if auth is implemented
                                dl_resp = requests.get(download_url_endpoint, headers=AUTH_HEADERS, timeout=20)
                                dl_resp.raise_for_status() # Check for HTTP errors

                                download_info = dl_resp.json()
                                url = download_info.get("url")

                                if url:
                                    # Provide a robust link; use a temporary session state flag to show it only once
                                    st.session_state[f'download_link_{doc_pk_id}'] = url
                                else:
                                    st.error("Backend did not return a valid download link.")
                                    if f'download_link_{doc_pk_id}' in st.session_state: del st.session_state[f'download_link_{doc_pk_id}']


                        except requests.exceptions.HTTPError as http_err:
                             # Try to get detail from response
                             detail = "Unknown error"
                             try: detail = http_err.response.json().get('detail', detail)
                             except: pass
                             st.error(f"Download Failed ({http_err.response.status_code}): {detail}")
                             if f'download_link_{doc_pk_id}' in st.session_state: del st.session_state[f'download_link_{doc_pk_id}']
                        except requests.exceptions.RequestException as req_err:
                            st.error(f"Network Error: Could not reach download API. {req_err}")
                            if f'download_link_{doc_pk_id}' in st.session_state: del st.session_state[f'download_link_{doc_pk_id}']
                        except Exception as e:
                            st.error(f"An unexpected error occurred: {e}")
                            if f'download_link_{doc_pk_id}' in st.session_state: del st.session_state[f'download_link_{doc_pk_id}']

                    # Display the download link if it was successfully generated in this run
                    if st.session_state.get(f'download_link_{doc_pk_id}'):
                         link = st.session_state[f'download_link_{doc_pk_id}']
                         # Use markdown for a clear link. The 'download' attribute helps browsers.
                         st.markdown(f'✅ Link ready: <a href="{link}" target="_blank" download>Click here to download "{doc_title[:50]}..."</a>', unsafe_allow_html=True)
                         # Optionally clear the link after showing it once or add a timeout
                         # del st.session_state[f'download_link_{doc_pk_id}']

            elif len(selected_rows) > 1:
                st.button(f"⬇️ Download {len(selected_rows)} Selected as ZIP", key="download_selected_zip", disabled=True) # Placeholder for future ZIP feature
                st.caption("(ZIP download not yet implemented)")


            # --- Download current view as CSV ---
            # Get filtered data directly from AgGrid response if needed, otherwise use df_display
            # grid_df_view = pd.DataFrame(grid_response['data']) # This has the grid's current view
            if not df_display.empty:
                # Prepare CSV data from the currently displayed DataFrame (df_display)
                csv_data = df_display.to_csv(index=False).encode('utf-8')
                st.download_button(
                     label="📄 Download Current View as CSV",
                     data=csv_data,
                     file_name="cairn_documents_export.csv",
                     mime="text/csv",
                     key='csv_download'
                )

        with col_act_2:
            # --- Detail pane for selected rows ---
             if selected_rows:
                 st.markdown("#### Selected Document Details")
                 # Prepare DataFrame for display, remove AgGrid internal column if present
                 sel_df = pd.DataFrame(selected_rows).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                 if len(sel_df) == 1:
                     # Transpose for better single-record view
                     st.dataframe(sel_df.iloc[0], use_container_width=True)
                 else:
                     st.dataframe(sel_df, use_container_width=True, height=200) # Show multiple selected rows


    elif load_button_pressed: # Handle case where button was pressed but no results came back
         st.warning("No documents found for the current filters.")


with tags_tab:
    # --- Keep existing Tag Definitions content ---
    st.info("""
    This table explains the different fields (tags) used to categorize documents in CAIRN...
    """)
    # ... [rest of your Tag Definitions DataFrame creation and display] ...
    tag_data = {
        'Tag Name (Filter)': [
            "File ID", "Document Title", "Published Date", #"Document Author",
             "Org/Utility Name",
            "Docket Number", "Document Type", "Document Subtype", "Document URL", "CAIRN URL",
            "Rate Impact", "Utility Reform", "Energy Resources", "Customer Classes", "DERs",
            "Physical Climate Risk", "Additional Keywords", "Tagger", "Date Tagged", "Quality Check",
            "Processing Notes", "State/Region", "Regulatory Body", "Jurisdiction Type",
            "Parent Document", "Related Documents", "Replaces Document", "Relationship Types"
            # "Local Backup Name" is excluded as likely internal use only
        ],
        'Description': [
            "Unique identifier for the document record (e.g., C250001)",
            "Full official title of the document",
            "The date the document was published or filed",
            #"The individual, firm, or entity that authored the document",
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
             "CYY##### format", "Text", "YYYY-MM-DD", #"Text",
             "PSE, Avista, PGE, CAISO, PNNL",
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
# st.caption("CAIRN Project v1.1 | Powered by Streamlit")