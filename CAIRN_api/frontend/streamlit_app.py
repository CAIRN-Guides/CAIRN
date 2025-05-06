import os
import streamlit as st
import requests # For making API calls
import pandas as pd
from dotenv import load_dotenv
from PIL import Image # If used elsewhere, keep
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
# This prevents errors if these keys are accessed before being set
if 'docs_df' not in st.session_state:
    st.session_state.docs_df = pd.DataFrame() # Stores the main DataFrame
if 'grid_response' not in st.session_state:
    st.session_state.grid_response = None # Stores the output from AgGrid

# ─── Header ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 5])
with col1:
    # Consider adding error handling for image loading if needed
    try:
        st.image("https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp", width=40) # adjust width as needed
    except Exception as img_err:
        st.warning(f"Could not load logo image: {img_err}")
with col2:
    st.title("CAIRN Document Finder")

# ─── Sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.header("Filters")
# Store parameters for the API request in a dictionary
# Reset params dict at the start of each run to reflect current sidebar state
params = {}

# --- Text Input Filters ---
text_cols = [
    "document_id", "document_title", "local_backup_name", "tagger",
    "file_format", "rate_impact", "quality_check", "regulatory_body",
    "state_region", "docket_number", "document_type", "org_utility_name",
    "parent_document", "replaces_document", "document_url", "cairn_url",
    "processing_notes"
]
for col in text_cols:
    # Use snake_case for keys, Title Case for labels
    v = st.sidebar.text_input(col.replace("_", " ").title())
    if v: # Only add non-empty values to params
        params[col] = v

# --- Date Input Filters ---
if d := st.sidebar.date_input("Published Date", value=None, key="published_date_filter"):
    params["published_date"] = d.isoformat()
if d := st.sidebar.date_input("Date Tagged", value=None, key="date_tagged_filter"):
    params["date_tagged"] = d.isoformat()
if d := st.sidebar.date_input("Last Synced At", value=None, key="last_synced_filter"):
    params["last_synced_at"] = d.isoformat()
if d := st.sidebar.date_input("Updated At", value=None, key="updated_at_filter"):
    params["updated_at"] = d.isoformat()

# --- List Input Filters (Comma-Separated Text) ---
list_cols = [
    "additional_keywords", "ders", "utility_reform",
    "customer_classes", "energy_resources",
    "related_documents", "relationship_types"
]
for col in list_cols:
    s = st.sidebar.text_input(col.replace("_", " ").title() + " (comma-separated)")
    if s:
        # Backend expects comma-separated string for list filters based on its logic
        params[col] = s

# --- Boolean Input Filter ---
# Assuming backend expects 'true' string for boolean filters via .eq()
if st.sidebar.checkbox("Physical Climate Risk"):
    params["physical_climate_risk"] = "true"

# --- Pagination & Options ---
st.sidebar.header("Options")
# Get pagination params directly for the API call
params["page"] = st.sidebar.number_input("Page Number", min_value=1, value=1)
params["page_size"] = st.sidebar.number_input("Page Size", min_value=1, max_value=200, value=20)

# This param doesn't seem to be used by the backend /documents endpoint currently
# params["include_download_url"] = st.sidebar.checkbox("Include Download URL", value=False)

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
    # Content is static, kept as provided
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
    5.  The table will populate within the **🔍 Search Documents** tab. You can then sort, filter, search, select rows using checkboxes, download selected PDFs, and view details.
    """) # Added mention of selection/download

# ─── Search Tab Content ────────────────────────────────────────────────────────
with search_tab:
    st.info("Use the filters in the sidebar and click 'Load Documents' to fetch and display data here.")

    # --- Data Fetching Logic ---
    # Triggered only when the Load button is pressed
    if load_button_pressed:
        with st.spinner('Fetching documents from CAIRN...'):
            try:
                # Filter out empty parameters before sending
                active_params = {k: v for k, v in params.items() if v is not None and v != ''}

                st.write("Sending Request to:", DOCUMENTS_API_URL) # Debug
                st.write("With Params:", active_params) # Debug

                resp = requests.get(DOCUMENTS_API_URL, params=active_params, timeout=45) # Slightly increased timeout
                resp.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

                docs_data = resp.json()
                docs = docs_data.get("data", [])
                total_docs = docs_data.get("total_count", len(docs))
                current_page = active_params.get('page', 1)
                page_size = active_params.get('page_size', 20)
                total_pages = (total_docs + page_size - 1) // page_size if total_docs > 0 else 1

                st.write(f"Showing **{len(docs)}** of **{total_docs}** documents (Page {current_page} of {total_pages})")

                if not docs:
                    st.warning("No documents found matching your criteria.")
                    st.session_state.docs_df = pd.DataFrame() # Clear stored DataFrame
                else:
                    # --- Build DataFrame ---
                    df = pd.DataFrame(docs)

                    # --- Flatten list columns for display ---
                    # (Backend handles list filtering with 'cs' operator if column is text[])
                    list_cols_from_sidebar = [
                        "additional_keywords", "ders", "utility_reform",
                        "customer_classes", "energy_resources",
                        "related_documents", "relationship_types"
                    ]
                    for lc in list_cols_from_sidebar:
                        if lc in df.columns:
                            # Check if the column actually contains lists before trying to join
                            if df[lc].apply(lambda x: isinstance(x, list)).any():
                                df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                    # --- Reorder & rename columns for display ---
                    cols_order_original = [
                        "id", # DB Primary Key - Needed for downloads!
                        "document_id", "document_title", "published_date", "org_utility_name",
                        "docket_number", "document_type", "document_subtype", "state_region",
                        "rate_impact", "utility_reform", "energy_resources", "customer_classes", "ders",
                        "physical_climate_risk", "additional_keywords",
                        "document_url", "cairn_url", # Keep if useful/populated
                        "tagger", "date_tagged", "quality_check",
                        # Less frequently needed display columns:
                        "local_backup_name", "file_format", "processing_notes",
                        "document_author", "regulatory_body", "jurisdiction_type",
                        "parent_document", "related_documents", "replaces_document", "relationship_types",
                        "b2_file_id", # Include for debug if helpful
                        "created_at", "updated_at", "last_synced_at",
                    ]
                    # Filter list to only include columns actually present in the DataFrame from API
                    cols_to_display = [col for col in cols_order_original if col in df.columns]
                    df_ordered = df[cols_to_display] # Reorder DF based on available columns

                    # Map backend field names to user-friendly names
                    rename_map = {
                        "id":                   "DB ID",
                        "document_id":          "File ID",
                        "local_backup_name":    "Local Backup Name",
                        "document_title":       "Document Title",
                        "published_date":       "Published Date",
                        "document_author":      "Document Author",
                        "org_utility_name":     "Org/Utility Name",
                        "docket_number":        "Docket Number",
                        "document_type":        "Document Type",
                        "document_subtype":     "Document Subtype",
                        "document_url":         "Document URL",
                        "cairn_url":            "CAIRN URL",
                        "b2_file_id":           "B2 File ID",
                        "rate_impact":          "Rate Impact",
                        "utility_reform":       "Utility Reform",
                        "energy_resources":     "Energy Resources",
                        "customer_classes":     "Customer Classes",
                        "ders":                 "DERs",
                        "physical_climate_risk":"Physical Climate Risk",
                        "additional_keywords":  "Additional Keywords",
                        "tagger":               "Tagger",
                        "date_tagged":          "Date Tagged",
                        "quality_check":        "Quality Check",
                        "processing_notes":     "Processing Notes",
                        "state_region":         "State/Region",
                        "regulatory_body":      "Regulatory Body",
                        "jurisdiction_type":    "Jurisdiction Type",
                        "parent_document":      "Parent Document",
                        "related_documents":    "Related Documents",
                        "replaces_document":    "Replaces Document",
                        "relationship_types":   "Relationship Types",
                        "created_at":           "Created At",
                        "updated_at":           "Updated At",
                        "last_synced_at":       "Last Synced At",
                        "file_format":          "File Format",
                    }
                    # Apply renaming only for columns present in the DataFrame
                    df_renamed = df_ordered.rename(columns={k: v for k, v in rename_map.items() if k in df_ordered.columns})

                    # --- Store the fetched and processed DataFrame in session state ---
                    # This replaces the old data upon successful load
                    st.session_state.docs_df = df_renamed

            except requests.exceptions.RequestException as e:
                st.error(f"API Request Failed: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    st.error(f"Status Code: {e.response.status_code}")
                    st.error(f"Response Text: {e.response.text}")
                st.session_state.docs_df = pd.DataFrame() # Clear stored DataFrame on error
            except Exception as e:
                st.error(f"An error occurred while processing data in the Search tab: {e}")
                st.error(traceback.format_exc())
                st.session_state.docs_df = pd.DataFrame() # Clear stored DataFrame on error

    # --- Display AgGrid and Download/Detail sections ---
    # This part runs based on the *current* content of session state,
    # making it more resilient to reruns caused by grid interactions.
    if not st.session_state.docs_df.empty:
        df_display_base = st.session_state.docs_df

        # --- Quick-search filter for the current view ---
        search = st.text_input("🔎 Quick Search current results", key="quick_search_input")
        if search:
            # Apply search mask case-insensitively across all string representations of columns
            mask = df_display_base.apply(
                lambda row: row.astype(str).str.contains(search, case=False, na=False).any(),
                axis=1
            )
            df_display_final = df_display_base[mask]
        else:
            df_display_final = df_display_base

        # --- Configure AgGrid ---
        gb = GridOptionsBuilder.from_dataframe(df_display_final)
        gb.configure_default_column(
            groupable=True, valueGetter="(data.field == null ? '' : data.field)", # Handle nulls better
            # enableValue=True, # Consider if needed
            # enableRowGroup=True, # Consider if needed
            # enablePivot=True, # Consider if needed
            filter="agTextColumnFilter", filterParams={"debounceMs": 300},
            sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150
        )
        # Make specific columns clickable links
        link_cols = ["Document URL", "CAIRN URL"] # Add others if needed
        for link_col in link_cols:
             if link_col in df_display_final.columns:
                 gb.configure_column(link_col, cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''', minWidth=250)

        gb.configure_side_bar(filters_panel=True, columns_panel=True)
        # Pagination within AgGrid (client-side for the loaded data)
        gb.configure_pagination(
            paginationAutoPageSize=False,
            paginationPageSize=params.get('page_size', 20) # Use the fetched page size as default
        )
        # IMPORTANT: Enable multi-row selection with checkboxes
        gb.configure_selection(
            selection_mode="multiple",
            use_checkbox=True,
            header_checkbox=True, # Allows select/deselect all on current page
            rowMultiSelectWithClick=False # Require checkbox click for selection
        )
        gb.configure_grid_options(domLayout='normal') # Use 'normal' for better performance with large datasets
        grid_opts = gb.build()

        # --- Render AgGrid ---
        # Use a consistent key, manage data via session state, store response in session state
        st.session_state.grid_response = AgGrid(
            df_display_final,
            gridOptions=grid_opts,
            key='document_grid_main', # Consistent key for the grid widget
            enable_enterprise_modules=False, # Set to True if using enterprise features
            # Trigger updates on selection change
            update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
            # Return filtered/sorted data if needed, though selection uses original data
            data_return_mode=DataReturnMode.AS_INPUT, # Get selected rows based on input data
            fit_columns_on_grid_load=False, # Adjust as needed
            height=600, width='100%',
            reload_data=False, # IMPORTANT: Data managed by session state externally
            allow_unsafe_jscode=True, # Needed for cellRenderer links
        )

        # --- Actions Section (Download Table CSV, Download Selected PDFs, View Details) ---
        st.markdown("---") # Visual separator

        col_actions1, col_actions2 = st.columns(2) # Create columns for actions

        # --- Download current table view as CSV ---
        with col_actions1:
            # Operate on the potentially filtered/sorted data shown in the grid
            # Note: grid_response['data'] reflects client-side filtering/sorting in AgGrid
            out_df_view = pd.DataFrame(st.session_state.grid_response["data"])
            if not out_df_view.empty:
                # Use ISO format for timestamp in filename
                timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
                csv_filename = f"cairn_export_{timestamp}.csv"
                csv_data = out_df_view.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Download Table View (CSV)",
                    data=csv_data,
                    file_name=csv_filename,
                    mime="text/csv",
                    key='csv_download_button'
                )
            else:
                st.button("⬇️ Download Table View (CSV)", disabled=True, key='csv_download_button_disabled')


        # --- PDF Download Logic (using selected rows) ---
        with col_actions2:
            # Retrieve selected rows from the grid response stored in session state
            selected_rows_data = st.session_state.grid_response["selected_rows"]

            if selected_rows_data:
                sel_df = pd.DataFrame(selected_rows_data)
                # CRITICAL: Ensure 'DB ID' column exists from your renaming step
                if "DB ID" not in sel_df.columns:
                    st.error("Error: 'DB ID' column missing in selection. Cannot prepare download.")
                    # Add debug info if needed: st.write(sel_df.columns)
                    st.button("📄 Prepare PDF Download Link", disabled=True, key='pdf_download_button_disabled_no_id')
                else:
                    selected_doc_pks = sel_df["DB ID"].tolist()
                    num_selected = len(selected_doc_pks)
                    download_button_label = f"📄 Prepare PDF Download Link ({num_selected} selected)"

                    if st.button(download_button_label, key="pdf_download_trigger_button"):
                        with st.spinner("Generating download link... This may take a moment for multiple files..."):
                            download_api_url = None
                            payload = None
                            headers = {"Accept": "application/json"}
                            full_proxy_url = None
                            download_filename = "download" # Default base name

                            try:
                                if num_selected == 1:
                                    doc_pk = selected_doc_pks[0]
                                    download_api_url = f"{API_BASE_URL.rstrip('/')}/documents/{doc_pk}/download-url"
                                    # Optional Debug: st.write(f"Calling single: {download_api_url}")
                                    download_resp = requests.get(download_api_url, headers=headers, timeout=30)
                                elif num_selected > 1:
                                    download_api_url = f"{API_BASE_URL.rstrip('/')}/documents/batch-download-url"
                                    payload = {"document_ids": selected_doc_pks}
                                    headers["Content-Type"] = "application/json"
                                    # Optional Debug: st.write(f"Calling batch: {download_api_url} with {num_selected} IDs")
                                    # Longer timeout for batch zipping/upload by backend
                                    download_resp = requests.post(download_api_url, json=payload, headers=headers, timeout=180)
                                else:
                                    # Should be unreachable due to outer 'if selected_rows_data:'
                                    st.warning("No documents selected.")
                                    download_resp = None

                                if download_resp:
                                    download_resp.raise_for_status() # Check HTTP status
                                    download_data = download_resp.json()

                                    relative_proxy_url = download_data.get("url")
                                    download_filename = download_data.get("filename", "cairn_download") # Use suggested filename

                                    if relative_proxy_url:
                                        # Construct the FULL URL for the browser link
                                        full_proxy_url = f"{API_BASE_URL.rstrip('/')}{relative_proxy_url}"

                                        st.success("Download link ready!")
                                        # Provide the link using markdown
                                        st.markdown(f"""
                                        Click the link below to download **{download_filename}**:
                                        <a href="{full_proxy_url}" target="_blank">{download_filename}</a>
                                        """, unsafe_allow_html=True)
                                        st.caption("Note: Link may expire after some time.")
                                    else:
                                        st.error("API did not return a valid download URL path.")
                                        st.json(download_data) # Show response for debugging

                            except requests.exceptions.RequestException as req_err:
                                st.error(f"Failed to get download link from API: {req_err}")
                                if hasattr(req_err, 'response') and req_err.response is not None:
                                    st.error(f"API Status Code: {req_err.response.status_code}")
                                    try:
                                        # Try to parse and display JSON error detail from backend
                                        error_detail = req_err.response.json()
                                        st.error("API Error Detail:")
                                        st.json(error_detail)
                                    except ValueError: # If response is not JSON
                                        st.error(f"API Response Text: {req_err.response.text[:500]}...") # Show raw text snippet
                            except Exception as gen_err:
                                st.error(f"An unexpected error occurred: {gen_err}")
                                st.error(traceback.format_exc())

            else:
                # Show disabled button if no rows are selected
                 st.button("📄 Prepare PDF Download Link", disabled=True, key='pdf_download_button_disabled_no_selection')

        # --- Detail pane for selected rows ---
        if selected_rows_data:
            st.markdown("---") # Separator before details
            sel_df_details = pd.DataFrame(selected_rows_data).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
            st.markdown("### 📄 Selected Document Details")
            if len(sel_df_details) == 1:
                # Transpose single selection for better readability
                st.dataframe(sel_df_details.iloc[0])
            else:
                # Display multiple selections as a table
                st.dataframe(sel_df_details, use_container_width=True)

    # --- Handle case where Load was pressed but no results found ---
    elif load_button_pressed and st.session_state.docs_df.empty:
        # The warning "No documents found..." was already shown during the fetch attempt.
        # No grid or actions needed here.
        pass

    # --- Initial state (before Load is pressed) ---
    # No grid or actions needed here either. The info message at the top covers this.


# ─── Tag Definitions Tab Content ───────────────────────────────────────────────
with tags_tab:
    st.info("""
    This table explains the different fields (tags) used to categorize documents in CAIRN.
    You can use the filters in the sidebar (under the '🔍 Search Documents' tab) to search based on these fields and terms.
    Note: Field names here match the filter labels in the sidebar. The underlying database field names might differ slightly (e.g., underscores).
    """)

    # Define the tag data (based on sidebar filters and common fields)
    # Match these 'Tag Name (Filter)' values to the labels used in st.sidebar.text_input etc.
    tag_data = {
        'Tag Name (Filter)': [
            "Document Id", "Document Title", "Published Date", "Document Author", "Org Utility Name",
            "Docket Number", "Document Type", "Document Subtype", "Document Url", "Cairn Url",
            "Rate Impact", "Utility Reform", "Energy Resources", "Customer Classes", "Ders",
            "Physical Climate Risk", "Additional Keywords", "Tagger", "Date Tagged", "Quality Check",
            "Processing Notes", "State Region", "Regulatory Body", "Jurisdiction Type",
            "Parent Document", "Related Documents", "Replaces Document", "Relationship Types",
            "File Format", "Local Backup Name", # Added from sidebar filters
            # "DB ID" and "Created At" are usually not filters but results
        ],
        'Description': [
            "Unique identifier for the document record (e.g., C250001)",
            "Full official title of the document",
            "The date the document was published or filed (YYYY-MM-DD)",
            "The individual, firm, or entity that authored the document",
            "The primary utility, organization, or agency associated with the document",
            "The official proceeding number (e.g., UE-230810)",
            "The main category or classification of the document",
            "A more specific sub-category of the document",
            "Direct URL link to the original source document webpage (if available)",
            "Direct URL link to the document file stored within the CAIRN system (if generated/available)",
            "Does the document primarily discuss ratepayer bill or tariff impacts? (e.g., Y/N/Partial/Text)",
            "Does the document primarily focus on utility governance or business model changes? (e.g., Y/N/Partial/Text)",
            "Comma-separated list of energy resource types discussed (e.g., gas, solar, storage, EE)",
            "Comma-separated list of customer classes addressed (e.g., residential, C&I, low-income)",
            "Comma-separated list related to Distributed Energy Resources (DERs) (e.g., DER, interconnection)",
            "Does the document primarily discuss physical climate risks like wildfire, heat, floods? (boolean 'true' or filter text)",
            "Comma-separated list of additional relevant keywords for searching",
            "Identifier for the person or team who applied the tags",
            "The date the tags were applied or last updated (YYYY-MM-DD)",
            "Has the accuracy of the document's metadata been verified? (e.g., Y/N/Pending)",
            "Internal notes regarding document processing, OCR issues, or anomalies",
            "The primary geographic state or region the document pertains to",
            "The primary regulatory agency with jurisdiction (e.g., PUC, FERC)",
            "The level of regulatory authority (e.g., State-Level, National)",
            "The File ID of a parent document this document belongs to (e.g., for appendices)",
            "Comma-separated File IDs of other documents related to this one",
            "The File ID of a document that this document replaces or supersedes",
            "Describes the relationship to parent/related documents (e.g., Appendix, Comment)",
            "The format of the file (e.g., PDF, DOCX)",
            "Internal filename used for local backup storage",
        ],
        'Filter Input Type / Format': [
            "Text", "Text", "Date Picker", "Text", "Text (e.g., Puget Sound Energy (PSE))",
            "Text (e.g., UE-#####)", "Text", "Text", "Text (URL)", "Text (URL)",
            "Text (e.g., Y, N)", "Text (e.g., Y, N)", "Text (comma-separated, e.g., solar, storage)", "Text (comma-separated, e.g., residential, C&I)", "Text (comma-separated)",
            "Checkbox (sends 'true' if checked)", "Text (comma-separated)", "Text", "Date Picker", "Text (e.g., Y, N)",
            "Text", "Text (e.g., WA, CA)", "Text (e.g., WA_UTC)", "Text",
            "Text (File ID)", "Text (comma-separated File IDs)", "Text (File ID)", "Text (comma-separated)",
            "Text (e.g., PDF)", "Text",
        ]
    }
    tag_definitions_df = pd.DataFrame(tag_data)

    # Display the DataFrame using st.dataframe for better scrolling and width handling
    st.dataframe(tag_definitions_df, use_container_width=True, height=600)

# ─── Optional Footer ───────────────────────────────────────────────────────────
# st.markdown("---")
# st.caption("CAIRN Project | Powered by Streamlit")