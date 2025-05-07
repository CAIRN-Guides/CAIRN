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
API_BASE_URL = os.getenv("API_URL", "https://cairn-backend.onrender.com")
DOCUMENTS_API_URL = f"{API_BASE_URL.rstrip('/')}/documents"
st.set_page_config(page_title="CAIRN Finder", layout="wide")

# --- Initialize Session State ---
if 'docs_df' not in st.session_state: st.session_state.docs_df = pd.DataFrame()
if 'grid_response' not in st.session_state: st.session_state.grid_response = None
if 'active_tab' not in st.session_state: st.session_state.active_tab = "about_cairn" # Default tab
if 'params' not in st.session_state: st.session_state.params = {}


# ─── Header ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 5])
with col1:
    try: st.image("https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp", width=40)
    except Exception as img_err: st.warning(f"Could not load logo: {img_err}")
with col2: st.title("CAIRN Document Finder")

# ─── Sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.header("Filters")
params = st.session_state.params # Use session state for params

# Group 1 Filters
params["org_utility_name"] = st.sidebar.text_input("Org or Utility Name", value=params.get("org_utility_name", ""))
params["document_author"] = st.sidebar.text_input("Document Author", value=params.get("document_author", ""))
params["document_type"] = st.sidebar.text_input("Document Type", value=params.get("document_type", ""))
params["document_subtype"] = st.sidebar.text_input("Document Subtype", value=params.get("document_subtype", ""))

st.sidebar.markdown("---") # Break in the sidebar

# Group 2 Filters
params["state_region"] = st.sidebar.text_input("State or Region", value=params.get("state_region", ""))
params["jurisdiction_type"] = st.sidebar.text_input("Jurisdiction", value=params.get("jurisdiction_type", ""))
params["regulatory_body"] = st.sidebar.text_input("Regulatory Body", value=params.get("regulatory_body", ""))

# "Load Documents" button comes right after "Regulatory Body"
load_button_pressed = st.sidebar.button("Load Documents", key="load_btn")

# Options section after the "Load Documents" button
st.sidebar.header("Options")
params["page"] = st.sidebar.number_input("Page", min_value=1, value=params.get("page", 1))
params["page_size"] = st.sidebar.number_input("Size", min_value=1, max_value=200, value=params.get("page_size", 20))

if load_button_pressed:
    st.session_state.active_tab = "search_documents" # Switch to search tab on button press
    st.session_state.params = params # Store current params in session state

# ─── Main Area with Tabs ───────────────────────────────────────────────────────
tab_titles = ["ℹ️ About CAIRN", "🔍 Search Documents", "🏷️ Tag Definitions"]
about_tab_content, search_tab_content, tags_tab_content = st.tabs(tab_titles)


# --- Content for About Tab ---
if about_tab_content:
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

# --- Content for Tags Tab ---
if tags_tab_content:
    st.info("""
    This table explains the different fields (tags) used to categorize documents in CAIRN.
    You can use the filters in the sidebar (under the '🔍 Search Documents' tab) to search based on these fields and terms.
    Note: Field names here match the filter labels in the sidebar. The underlying database field names might differ slightly (e.g., underscores).
    """)

    # Defines filterable fields for the "Tag Definitions" tab
    tag_data_filterable = {
        'Tag Name (Filter)': [
            "Org or Utility Name", "Document Author", "Document Type", "Document Subtype",
            "State or Region", "Jurisdiction", "Regulatory Body",
        ],
        'Description': [
            "The primary utility, organization, or agency associated with the document (Filterable)",
            "The individual, firm, or entity that authored the document (Filterable)",
            "The main category or classification of the document (Filterable)",
            "A more specific sub-category of the document (Filterable)",
            "The primary geographic state or region the document pertains to (Filterable)",
            "The level of regulatory authority (e.g., State-Level, National) (Filterable)",
            "The primary regulatory agency with jurisdiction (e.g., PUC, FERC) (Filterable)",
        ],
        'Filter Input Type / Format': [
            "Text (e.g., Puget Sound Energy (PSE))", "Text", "Text", "Text",
            "Text (e.g., WA, CA)", "Text", "Text (e.g., WA_UTC)",
        ]
    }
    tag_definitions_df_filterable = pd.DataFrame(tag_data_filterable)
    tag_definitions_df_filterable.rename(columns={'Tag Name (Filter)': 'Field Name', 'Filter Input Type / Format': 'Example Input / Notes'}, inplace=True)

    # Defines other common fields that appear in the table but are not filterable via sidebar
    # CORRECTED: Ensured all lists have the same length (29 items)
    common_table_fields_tags = {
        'Tag Name (Displayed in Table)': [
            "DB ID", "File ID", "Document Title", "Description", "Published Date",
            "Docket Number", "Rate Impact", "Utility Reform", "Energy Resources",
            "Customer Classes", "DERs", "Physical Climate Risk", "Additional Keywords",
            "Document URL", "CAIRN URL", "Tagger", "Date Tagged", "Quality Check",
            "Local Backup Name", "File Format", "Processing Notes", "Parent Document",
            "Related Documents", "Replaces Document", "Relationship Types", "B2 File ID",
            "Created At", "Updated At", "Last Synced At"
        ], # 29 items
        'Description': [
            "Unique database identifier for the document record",
            "Unique CAIRN identifier for the document file (e.g., C250001)",
            "Full official title of the document",
            "Brief summary or description of the document content",
            "The date the document was published or filed (YYYY-MM-DD)",
            "The official proceeding number (e.g., UE-230810)",
            "Discusses ratepayer bill or tariff impacts? (e.g., Y/N/Partial/Text)",
            "Focuses on utility governance or business model changes? (e.g., Y/N/Partial/Text)",
            "Energy resource types discussed (e.g., gas, solar, storage, EE) (comma-separated)",
            "Customer classes addressed (e.g., residential, C&I, low-income) (comma-separated)",
            "Related to Distributed Energy Resources (DERs) (e.g., DER, interconnection) (comma-separated)",
            "Discusses physical climate risks like wildfire, heat, floods?",
            "Additional relevant keywords for searching (comma-separated)",
            "Direct URL link to the original source document webpage (if available)",
            "Direct URL link to the document file stored within the CAIRN system (if generated/available)",
            "Identifier for the person or team who applied the tags",
            "The date the tags were applied or last updated (YYYY-MM-DD)",
            "Has the accuracy of the document's metadata been verified? (e.g., Y/N/Pending)",
            "Internal filename used for local backup storage",
            "The format of the file (e.g., PDF, DOCX)",
            "Internal notes regarding document processing, OCR issues, or anomalies",
            "File ID of a parent document this document belongs to",
            "File IDs of other documents related to this one (comma-separated)",
            "File ID of a document that this document replaces or supersedes",
            "Describes the relationship to parent/related documents (comma-separated)",
            "Internal Backblaze B2 file identifier",
            "Date the record was created in the database",
            "Date the record was last modified in the database",
            "Date the document record was last synchronized with its source"
        ], # 29 items
        'Filterable in Sidebar?': ["No"] * 29 # 29 items
    }
    tag_definitions_df_other = pd.DataFrame(common_table_fields_tags)
    tag_definitions_df_other.rename(columns={'Tag Name (Displayed in Table)': 'Field Name'}, inplace=True)


    st.subheader("Filterable Fields (via Sidebar)")
    st.dataframe(tag_definitions_df_filterable[['Field Name', 'Description', 'Example Input / Notes']], use_container_width=True)

    st.subheader("Other Common Fields (Displayed in Document Table)")
    st.markdown("The following fields may also appear in the document table in the 'Search Documents' tab but are not directly filterable through the simplified sidebar filters.")
    # Displaying relevant columns from the corrected DataFrame
    st.dataframe(tag_definitions_df_other[['Field Name', 'Description']], use_container_width=True, height=300)


# ─── Search Tab Content ────────────────────────────────────────────────────────
if search_tab_content:
    st.info("Use the filters in the sidebar and click 'Load Documents' to fetch and display data here.")

    if load_button_pressed or ('docs_df' in st.session_state and not st.session_state.docs_df.empty) :
        if load_button_pressed: # Only fetch if the button initiated this
            with st.spinner('Fetching documents...'):
                try:
                    active_params = {}
                    for k, v in st.session_state.params.items():
                        if isinstance(v, str):
                            if v.strip() != '': # Send only non-empty strings
                                active_params[k] = v
                        elif v is not None : # For non-string types like numbers (page, page_size)
                             active_params[k] = v
                    
                    # Remove keys with None or empty string values from params before API call
                    # This is implicitly handled by the loop above, but good to be aware
                    # active_params = {k: v for k, v in active_params.items() if v is not None and (not isinstance(v, str) or v.strip() != '')}


                    resp = requests.get(DOCUMENTS_API_URL, params=active_params, timeout=45)
                    resp.raise_for_status()
                    docs_data = resp.json()
                    docs = docs_data.get("data", [])
                    total_docs = docs_data.get("total_count", len(docs))
                    # Use .get for page and page_size from active_params to handle cases where they might not be set
                    current_page = active_params.get('page', 1)
                    page_size_from_params = active_params.get('page_size', 20)
                    total_pages = (total_docs + page_size_from_params - 1) // page_size_from_params if total_docs > 0 else 1
                    st.write(f"Showing **{len(docs)}** of **{total_docs}** documents (Page {current_page} of {total_pages})")

                    if not docs:
                        st.warning("No documents found matching your criteria."); st.session_state.docs_df = pd.DataFrame()
                    else:
                        df = pd.DataFrame(docs)
                        list_cols_fmt = ["additional_keywords", "ders", "utility_reform", "customer_classes", "energy_resources", "related_documents", "relationship_types"]
                        for lc in list_cols_fmt:
                            if lc in df.columns and df[lc].apply(lambda x: isinstance(x, list)).any():
                                df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                        cols_order = [
                            "id", "document_id", "document_title", "description",
                            "published_date", "document_author",
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

                        rename_map = {
                            "id": "DB ID", "document_id": "File ID", "local_backup_name": "Local Backup Name",
                            "document_title": "Document Title", "description": "Description",
                            "published_date": "Published Date", "document_author": "Document Author",
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

        # --- Display AgGrid and Actions (always if docs_df is not empty) ---
        if not st.session_state.docs_df.empty:
            df_display_base = st.session_state.docs_df
            search_val = st.text_input("🔎 Quick Search current results", key="quick_search_input");
            if search_val: df_display_final = df_display_base[df_display_base.apply(lambda r: r.astype(str).str.contains(search_val, case=False, na=False).any(), axis=1)]
            else: df_display_final = df_display_base

            gb = GridOptionsBuilder.from_dataframe(df_display_final)
            gb.configure_default_column(groupable=True, filter="agTextColumnFilter", filterParams={"debounceMs": 300}, sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150)
            link_cols = ["Document URL", "CAIRN URL"]
            for link_col in link_cols:
                 if link_col in df_display_final.columns: gb.configure_column(link_col, cellRenderer='''function(params){return params.value?'<a href="'+params.value+'" target="_blank" rel="noopener noreferrer">'+params.value+'</a>':''}''', minWidth=250)
            if "Description" in df_display_final.columns:
                 gb.configure_column("Description", minWidth=300)
            gb.configure_side_bar(filters_panel=True, columns_panel=True)
            # Use page_size from session_state.params for pagination, which should be up-to-date
            gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=st.session_state.params.get('page_size', 20))
            gb.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True, rowMultiSelectWithClick=False)
            gb.configure_grid_options(domLayout='normal')
            grid_opts = gb.build()

            st.session_state.grid_response = AgGrid(
                df_display_final, gridOptions=grid_opts, key='document_grid_main',
                enable_enterprise_modules=False,
                update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=False, height=600, width='100%',
                reload_data=False, allow_unsafe_jscode=True
            )

            st.markdown("---")
            col_actions1, col_actions2 = st.columns(2)

            with col_actions1:
                current_grid_data = st.session_state.grid_response.get("data")
                if isinstance(current_grid_data, pd.DataFrame) and not current_grid_data.empty:
                    out_df_view = current_grid_data
                    ts = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S'); csv_fn = f"cairn_{ts}.csv"
                    csv_data = out_df_view.to_csv(index=False).encode('utf-8')
                    st.download_button(label="⬇️ CSV", data=csv_data, file_name=csv_fn, mime="text/csv", key='csv_btn')
                else:
                    st.button("⬇️ CSV", disabled=True, key='csv_btn_dis')


            selected_rows_data = None
            grid_response_current = st.session_state.get('grid_response')
            if grid_response_current:
                selected_rows_data = grid_response_current.get("selected_rows")

            is_valid_selection = isinstance(selected_rows_data, pd.DataFrame) and not selected_rows_data.empty

            if is_valid_selection:
                with col_actions2:
                    sel_df = selected_rows_data
                    if "DB ID" not in sel_df.columns:
                        st.error("Error: 'DB ID' missing from selected rows. Cannot generate PDF link.")
                        st.button("📄 PDF Link", disabled=True, key='pdf_btn_no_id')
                    else:
                        selected_pks = sel_df["DB ID"].dropna().tolist()
                        num_sel = len(selected_pks)
                        btn_label = f"📄 PDF Link ({num_sel} selected)"

                        if not selected_pks:
                             st.warning("No valid DB IDs in selection for PDF link.")
                             st.button(btn_label, disabled=True, key="pdf_trigger_btn_no_valid_ids")
                        elif st.button(btn_label, key="pdf_trigger_btn"):
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
                                    else:
                                        resp = None # Should not be reached if selected_pks is not empty

                                    if resp:
                                        resp.raise_for_status(); data = resp.json()
                                        rel_url = data.get("url"); dl_fn = data.get("filename", "cairn_dl")
                                        if rel_url:
                                            dl_url = f"{API_BASE_URL.rstrip('/')}{rel_url}"
                                            st.success("Link ready!")
                                            st.markdown(f'<a href="{dl_url}" target="_blank">{dl_fn}</a>', unsafe_allow_html=True)
                                            st.caption("Link may expire.")
                                        else: st.error("API did not return a URL."); st.json(data)
                                except requests.exceptions.RequestException as e:
                                    st.error(f"API Error: {e}")
                                    if hasattr(e, 'response') and e.response is not None:
                                        st.error(f"API Status: {e.response.status_code}")
                                        try: st.error("API Detail:"); st.json(e.response.json())
                                        except ValueError: st.error(f"API Resp: {e.response.text[:500]}...")
                                except Exception as e: st.error(f"Error: {e}"); st.error(traceback.format_exc())

                st.markdown("---")
                sel_df_details = selected_rows_data.drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                st.markdown("### 📄 Selected Document Details")
                if len(sel_df_details) == 1: st.dataframe(sel_df_details.iloc[0])
                else: st.dataframe(sel_df_details, use_container_width=True)

            else: # if not is_valid_selection
                with col_actions2: st.button("📄 PDF Link", disabled=True, key='pdf_btn_no_sel')
                st.markdown("---"); st.caption("Select rows for details/download.")

        elif load_button_pressed and st.session_state.docs_df.empty:
            # This case is when the button was pressed, API call was made, but no docs were found.
            # The warning "No documents found matching your criteria." is already shown inside the data fetching block.
            pass

    elif not load_button_pressed and st.session_state.docs_df.empty :
         # This state is when the tab is selected but no button has been pressed yet
         # and no data is loaded. The initial info message "Use the filters..." is sufficient.
         pass

# Optional Footer
# st.markdown("---")
# st.caption("CAIRN Project | Powered by Streamlit")
