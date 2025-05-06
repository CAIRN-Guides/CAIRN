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
# <<< CHANGE 1: Updated default API_BASE_URL as requested >>>
API_BASE_URL = os.getenv("API_URL", "https://cairn-backend.onrender.com") # Updated default URL as per instructions
DOCUMENTS_API_URL = f"{API_BASE_URL.rstrip('/')}/documents"
st.set_page_config(page_title="CAIRN Finder", layout="wide")

# --- Initialize Session State ---
if 'docs_df' not in st.session_state: st.session_state.docs_df = pd.DataFrame()
if 'grid_response' not in st.session_state: st.session_state.grid_response = None

# ─── Header ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 5])
with col1:
    try: st.image("https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp", width=40)
    except Exception as img_err: st.warning(f"Could not load logo: {img_err}")
with col2: st.title("CAIRN Document Finder")

# ─── Sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.header("Filters")
params = {}
# <<< NOTE: Added 'description' and 'document_author' to the text filter list, although they might not be ideal for free-text search depending on content >>>
text_cols = ["document_id", "document_title", "description", "document_author", "local_backup_name", "tagger", "file_format", "rate_impact", "quality_check", "regulatory_body", "state_region", "docket_number", "document_type", "org_utility_name", "parent_document", "replaces_document", "document_url", "cairn_url", "processing_notes"]
for col in text_cols:
    v = st.sidebar.text_input(col.replace("_", " ").title());
    if v: params[col] = v
if d := st.sidebar.date_input("Published Date", value=None, key="pub_date"): params["published_date"] = d.isoformat()
if d := st.sidebar.date_input("Date Tagged", value=None, key="tag_date"): params["date_tagged"] = d.isoformat()
if d := st.sidebar.date_input("Last Synced", value=None, key="sync_date"): params["last_synced_at"] = d.isoformat()
if d := st.sidebar.date_input("Updated At", value=None, key="update_date"): params["updated_at"] = d.isoformat()
list_cols = ["additional_keywords", "ders", "utility_reform", "customer_classes", "energy_resources", "related_documents", "relationship_types"]
for col in list_cols:
    s = st.sidebar.text_input(col.replace("_", " ").title() + " (comma-separated)");
    if s: params[col] = s
if st.sidebar.checkbox("Physical Climate Risk"): params["physical_climate_risk"] = "true"
st.sidebar.header("Options")
params["page"] = st.sidebar.number_input("Page", min_value=1, value=1)
params["page_size"] = st.sidebar.number_input("Size", min_value=1, max_value=200, value=20)
load_button_pressed = st.sidebar.button("Load Documents", key="load_btn")

# ─── Main Area with Tabs ───────────────────────────────────────────────────────
# <<< Using tab names from broken code >>>
about_tab, search_tab, tags_tab = st.tabs([
    "ℹ️ About CAIRN",
    "🔍 Search Documents",
    "🏷️ Tag Definitions"
])

# <<< Content for About Tab from broken code >>>
with about_tab:
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

# <<< Content for Tags Tab from broken code >>>
with tags_tab:
    st.info("""
    This table explains the different fields (tags) used to categorize documents in CAIRN.
    You can use the filters in the sidebar (under the '🔍 Search Documents' tab) to search based on these fields and terms.
    Note: Field names here match the filter labels in the sidebar. The underlying database field names might differ slightly (e.g., underscores).
    """)

    # Define the tag data (based on sidebar filters and common fields)
    # Match these 'Tag Name (Filter)' values to the labels used in st.sidebar.text_input etc.
    # <<< Adjusted to include 'description' and 'document_author' as they are in the new code's sidebar >>>
    tag_data = {
        'Tag Name (Filter)': [
            "Document Id", "Document Title", "Description", "Published Date", "Document Author", "Org Utility Name",
            "Docket Number", "Document Type", "Document Subtype", "Document Url", "Cairn Url",
            "Rate Impact", "Utility Reform", "Energy Resources", "Customer Classes", "Ders",
            "Physical Climate Risk", "Additional Keywords", "Tagger", "Date Tagged", "Quality Check",
            "Processing Notes", "State Region", "Regulatory Body", "Jurisdiction Type",
            "Parent Document", "Related Documents", "Replaces Document", "Relationship Types",
            "File Format", "Local Backup Name",
            # Added Date/Time filters from new code sidebar
            "Last Synced", "Updated At",
            # "DB ID" and "Created At" are usually not filters but results
        ],
        'Description': [
            "Unique identifier for the document record (e.g., C250001)",
            "Full official title of the document",
            "Brief summary or description of the document content", # Added Description
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
            "Date the document record was last synchronized with its source (YYYY-MM-DD)", # Added Last Synced
            "Date the document record was last modified in the database (YYYY-MM-DD)", # Added Updated At
        ],
        'Filter Input Type / Format': [
            "Text", "Text", "Text", "Date Picker", "Text", "Text (e.g., Puget Sound Energy (PSE))",
            "Text (e.g., UE-#####)", "Text", "Text", "Text (URL)", "Text (URL)",
            "Text (e.g., Y, N)", "Text (e.g., Y, N)", "Text (comma-separated, e.g., solar, storage)", "Text (comma-separated, e.g., residential, C&I)", "Text (comma-separated)",
            "Checkbox (sends 'true' if checked)", "Text (comma-separated)", "Text", "Date Picker", "Text (e.g., Y, N)",
            "Text", "Text (e.g., WA, CA)", "Text (e.g., WA_UTC)", "Text",
            "Text (File ID)", "Text (comma-separated File IDs)", "Text (File ID)", "Text (comma-separated)",
            "Text (e.g., PDF)", "Text",
            "Date Picker", "Date Picker", # Added for Last Synced, Updated At
        ]
    }
    tag_definitions_df = pd.DataFrame(tag_data)

    # Display the DataFrame using st.dataframe for better scrolling and width handling
    st.dataframe(tag_definitions_df, use_container_width=True, height=600)


# ─── Search Tab Content ────────────────────────────────────────────────────────
with search_tab:
    # <<< Using Info text from broken code >>>
    st.info("Use the filters in the sidebar and click 'Load Documents' to fetch and display data here.")

    # --- Data Fetching ---
    if load_button_pressed:
        with st.spinner('Fetching documents...'):
            try:
                active_params = {k: v for k, v in params.items() if v is not None and v != ''}
                resp = requests.get(DOCUMENTS_API_URL, params=active_params, timeout=45)
                resp.raise_for_status()
                docs_data = resp.json()
                docs = docs_data.get("data", [])
                total_docs = docs_data.get("total_count", len(docs))
                current_page = active_params.get('page', 1); page_size = active_params.get('page_size', 20)
                total_pages = (total_docs + page_size - 1) // page_size if total_docs > 0 else 1
                # <<< Using write format from broken code >>>
                st.write(f"Showing **{len(docs)}** of **{total_docs}** documents (Page {current_page} of {total_pages})")

                if not docs:
                    st.warning("No documents found matching your criteria."); st.session_state.docs_df = pd.DataFrame()
                else:
                    df = pd.DataFrame(docs)
                    list_cols_fmt = ["additional_keywords", "ders", "utility_reform", "customer_classes", "energy_resources", "related_documents", "relationship_types"]
                    for lc in list_cols_fmt:
                        if lc in df.columns and df[lc].apply(lambda x: isinstance(x, list)).any():
                            df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                    # <<< CHANGE 2a: Added 'description' and 'document_author' to the desired column order >>>
                    cols_order = [
                        "id", "document_id", "document_title", "description", # Added description
                        "published_date", "document_author", # Added document_author
                        "org_utility_name", "docket_number", "document_type", "document_subtype",
                        "state_region", "rate_impact", "utility_reform", "energy_resources",
                        "customer_classes", "ders", "physical_climate_risk", "additional_keywords",
                        "document_url", "cairn_url", "tagger", "date_tagged", "quality_check",
                        "local_backup_name", "file_format", "processing_notes", "regulatory_body",
                        "jurisdiction_type", "parent_document", "related_documents", "replaces_document",
                        "relationship_types", "b2_file_id", "created_at", "updated_at", "last_synced_at"
                    ]
                    cols_to_display = [col for col in cols_order if col in df.columns]
                    df_ordered = df[cols_to_display]

                    # <<< CHANGE 2b: Added mappings for 'description' and 'document_author' >>>
                    rename_map = {
                        "id": "DB ID", "document_id": "File ID", "local_backup_name": "Local Backup Name",
                        "document_title": "Document Title", "description": "Description", # Added description
                        "published_date": "Published Date", "document_author": "Document Author", # Added document_author
                        "org_utility_name": "Org/Utility Name", "docket_number": "Docket Number",
                        "document_type": "Document Type", "document_subtype": "Document Subtype",
                        "document_url": "Document URL", "cairn_url": "CAIRN URL", "b2_file_id": "B2 File ID",
                        "rate_impact": "Rate Impact", "utility_reform": "Utility Reform",
                        "energy_resources": "Energy Resources", "customer_classes": "Customer Classes",
                        "ders": "DERs", "physical_climate_risk": "Physical Climate Risk",
                        "additional_keywords": "Additional Keywords", "tagger": "Tagger",
                        "date_tagged": "Date Tagged", "quality_check": "Quality Check",
                        "processing_notes": "Processing Notes", "state_region": "State/Region",
                        "regulatory_body": "Regulatory Body", "jurisdiction_type": "Jurisdiction Type",
                        "parent_document": "Parent Document", "related_documents": "Related Documents",
                        "replaces_document": "Replaces Document", "relationship_types": "Relationship Types",
                        "created_at": "Created At", "updated_at": "Updated At", "last_synced_at": "Last Synced At",
                        "file_format": "File Format"
                    }
                    df_renamed = df_ordered.rename(columns={k: v for k, v in rename_map.items() if k in df_ordered.columns})
                    st.session_state.docs_df = df_renamed

            except requests.exceptions.RequestException as e:
                st.error(f"API Request Failed: {e}")
                if hasattr(e, 'response') and e.response is not None: st.error(f"Status: {e.response.status_code}, Response: {e.response.text}")
                st.session_state.docs_df = pd.DataFrame()
            except Exception as e:
                st.error(f"Processing error: {e}"); st.error(traceback.format_exc())
                st.session_state.docs_df = pd.DataFrame()

    # --- Display AgGrid and Actions ---
    if not st.session_state.docs_df.empty:
        df_display_base = st.session_state.docs_df
        # <<< Quick search input from new code, using key from broken code if desired (using new key is fine too) >>>
        search = st.text_input("🔎 Quick Search current results", key="quick_search_input");
        if search: df_display_final = df_display_base[df_display_base.apply(lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1)]
        else: df_display_final = df_display_base

        # --- Configure AgGrid ---
        gb = GridOptionsBuilder.from_dataframe(df_display_final)
        # Use default column config (valueGetter removed)
        gb.configure_default_column(groupable=True, filter="agTextColumnFilter", filterParams={"debounceMs": 300}, sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150)
        link_cols = ["Document URL", "CAIRN URL"]
        for link_col in link_cols:
             if link_col in df_display_final.columns: gb.configure_column(link_col, cellRenderer='''function(params){return params.value?'<a href="'+params.value+'" target="_blank" rel="noopener noreferrer">'+params.value+'</a>':''}''', minWidth=250)
        # <<< NOTE: Configure specific columns like Description if needed (e.g., longer minWidth) >>>
        if "Description" in df_display_final.columns:
             gb.configure_column("Description", minWidth=300) # Example: Make Description column wider
        gb.configure_side_bar(filters_panel=True, columns_panel=True)
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=params.get('page_size', 20))
        # <<< Selection mode from new code >>>
        gb.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True, rowMultiSelectWithClick=False)
        gb.configure_grid_options(domLayout='normal')
        grid_opts = gb.build()

        # --- Render AgGrid ---
        st.session_state.grid_response = AgGrid(
            df_display_final, gridOptions=grid_opts, key='document_grid_main', # Using new code key
            enable_enterprise_modules=False,
            # <<< Update/Data modes from new code >>>
            update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT, # This mode returns DataFrame for selected_rows
            fit_columns_on_grid_load=False, height=600, width='100%',
            # <<< reload_data=False from new code, allow_unsafe_jscode=True >>>
            reload_data=False, allow_unsafe_jscode=True
        )

        # --- Actions Section ---
        st.markdown("---")
        col_actions1, col_actions2 = st.columns(2)

        # --- Download Table View (CSV) ---
        with col_actions1:
            out_df_view = pd.DataFrame(st.session_state.grid_response["data"]) # Data reflects grid view (sort/filter)
            if not out_df_view.empty:
                ts = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S'); csv_fn = f"cairn_{ts}.csv"
                csv_data = out_df_view.to_csv(index=False).encode('utf-8')
                # <<< Using download button label from new code >>>
                st.download_button(label="⬇️ CSV", data=csv_data, file_name=csv_fn, mime="text/csv", key='csv_btn')
            else: st.button("⬇️ CSV", disabled=True, key='csv_btn_dis')

        # --- Retrieve selected rows safely ---
        selected_rows_data = None
        grid_response_current = st.session_state.get('grid_response')
        if grid_response_current:
            selected_rows_data = grid_response_current.get("selected_rows") # This is a DataFrame

        # --- *** CORRECTED CHECK: Use DataFrame properties *** ---
        is_valid_selection = isinstance(selected_rows_data, pd.DataFrame) and not selected_rows_data.empty

        # Optional Debugging (can be removed later)
        # st.write("--- Debug Selection Info ---")
        # st.write(f"selected_rows type: {type(selected_rows_data)}")
        # if isinstance(selected_rows_data, pd.DataFrame): st.dataframe(selected_rows_data.head())
        # else: st.write(f"selected_rows value: {str(selected_rows_data)[:500]}")
        # st.write(f"Condition `isinstance(df) and not df.empty` is: {is_valid_selection}")
        # st.write("--- End Debug Selection Info ---")
        # --- *** END CORRECTED CHECK *** ---


        # --- Check the evaluated condition ---
        if is_valid_selection:
            # --- PDF Download Logic ---
            with col_actions2:
                # Use the DataFrame directly
                sel_df = selected_rows_data
                if "DB ID" not in sel_df.columns:
                    st.error("Error: 'DB ID' missing.")
                    st.button("📄 PDF Link", disabled=True, key='pdf_btn_no_id')
                else:
                    selected_pks = sel_df["DB ID"].tolist(); num_sel = len(selected_pks)
                    btn_label = f"📄 PDF Link ({num_sel} selected)"
                    if st.button(btn_label, key="pdf_trigger_btn"):
                        with st.spinner("Generating link..."):
                            api_url = None; payload = None; headers = {"Accept": "application/json"}
                            dl_url = None; dl_fn = "download"
                            try:
                                if num_sel == 1:
                                    api_url = f"{API_BASE_URL.rstrip('/')}/documents/{selected_pks[0]}/download-url"
                                    resp = requests.get(api_url, headers=headers, timeout=30)
                                elif num_sel > 1:
                                    api_url = f"{API_BASE_URL.rstrip('/')}/documents/batch-download-url"
                                    payload = {"document_ids": selected_pks}; headers["Content-Type"] = "application/json"
                                    resp = requests.post(api_url, json=payload, headers=headers, timeout=180)
                                else: resp = None

                                if resp:
                                    resp.raise_for_status(); data = resp.json()
                                    rel_url = data.get("url"); dl_fn = data.get("filename", "cairn_dl")
                                    if rel_url:
                                        # <<< Use the potentially updated API_BASE_URL >>>
                                        dl_url = f"{API_BASE_URL.rstrip('/')}{rel_url}"
                                        st.success("Link ready!")
                                        st.markdown(f'<a href="{dl_url}" target="_blank">{dl_fn}</a>', unsafe_allow_html=True)
                                        st.caption("Link may expire.")
                                    else: st.error("API did not return a URL."); st.json(data) # Corrected error message
                            except requests.exceptions.RequestException as e:
                                st.error(f"API Error: {e}")
                                if hasattr(e, 'response') and e.response is not None:
                                    st.error(f"API Status: {e.response.status_code}")
                                    try: st.error("API Detail:"); st.json(e.response.json())
                                    except ValueError: st.error(f"API Resp: {e.response.text[:500]}...")
                            except Exception as e: st.error(f"Error: {e}"); st.error(traceback.format_exc())

            # --- Detail pane ---
            st.markdown("---")
            # Use the DataFrame directly, drop AgGrid internal column if present
            sel_df_details = selected_rows_data.drop(columns=["_selectedRowNodeInfo"], errors="ignore")
            # <<< Using header from broken code >>>
            st.markdown("### 📄 Selected Document Details")
            # <<< Using display logic from broken code (transpose for single record) >>>
            if len(sel_df_details) == 1: st.dataframe(sel_df_details.iloc[0])
            else: st.dataframe(sel_df_details, use_container_width=True)

        else:
            # --- Handle No Selection ---
            with col_actions2: st.button("📄 PDF Link", disabled=True, key='pdf_btn_no_sel')
            st.markdown("---"); st.caption("Select rows for details/download.")

    elif load_button_pressed and st.session_state.docs_df.empty: pass # Handled by the warning message inside the 'if load_button_pressed' block
    # Initial state (before button press) handled implicitly - nothing shown in search tab except info text

# Optional Footer (Uncomment if desired)
# st.markdown("---")
# st.caption("CAIRN Project | Powered by Streamlit")