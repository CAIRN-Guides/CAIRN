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
params["jurisdiction_type"] = st.sidebar.text_input("Jurisdiction", value=params.get("jurisdiction_type", "")) # Renamed label
params["regulatory_body"] = st.sidebar.text_input("Regulatory Body", value=params.get("regulatory_body", ""))

st.sidebar.markdown("---") # Optional: another separator before other less critical filters

# Define all original text columns and list columns
all_text_cols = [
    "document_id", "document_title", "description", "local_backup_name",
    "tagger", "file_format", "rate_impact", "quality_check",
    "docket_number", "parent_document", "replaces_document",
    "document_url", "cairn_url", "processing_notes"
]
# Remove already displayed columns from all_text_cols
priority_text_cols = ["org_utility_name", "document_author", "document_type", "document_subtype",
                      "state_region", "jurisdiction_type", "regulatory_body"]
remaining_text_cols = [col for col in all_text_cols if col not in priority_text_cols]

for col in remaining_text_cols:
    params[col] = st.sidebar.text_input(col.replace("_", " ").title(), value=params.get(col, ""))

# Date Filters
if d := st.sidebar.date_input("Published Date", value=pd.to_datetime(params.get("published_date")) if params.get("published_date") else None, key="pub_date"):
    params["published_date"] = d.isoformat()
else:
    if "pub_date" in st.session_state and st.session_state.pub_date is None : params.pop("published_date", None) # Clear if explicitly cleared

if d := st.sidebar.date_input("Date Tagged", value=pd.to_datetime(params.get("date_tagged")) if params.get("date_tagged") else None, key="tag_date"):
    params["date_tagged"] = d.isoformat()
else:
    if "tag_date" in st.session_state and st.session_state.tag_date is None : params.pop("date_tagged", None)


if d := st.sidebar.date_input("Last Synced", value=pd.to_datetime(params.get("last_synced_at")) if params.get("last_synced_at") else None, key="sync_date"):
    params["last_synced_at"] = d.isoformat()
else:
    if "sync_date" in st.session_state and st.session_state.sync_date is None : params.pop("last_synced_at", None)

if d := st.sidebar.date_input("Updated At", value=pd.to_datetime(params.get("updated_at")) if params.get("updated_at") else None, key="update_date"):
    params["updated_at"] = d.isoformat()
else:
    if "update_date" in st.session_state and st.session_state.update_date is None : params.pop("updated_at", None)


# List Filters
list_cols = ["additional_keywords", "ders", "utility_reform", "customer_classes", "energy_resources", "related_documents", "relationship_types"]
for col in list_cols:
    params[col] = st.sidebar.text_input(col.replace("_", " ").title() + " (comma-separated)", value=params.get(col, ""))

# Checkbox Filter
physical_climate_risk_checked = st.sidebar.checkbox("Physical Climate Risk", value=params.get("physical_climate_risk") == "true")
if physical_climate_risk_checked:
    params["physical_climate_risk"] = "true"
else:
    params.pop("physical_climate_risk", None) # Remove if unchecked

# Options
st.sidebar.header("Options")
params["page"] = st.sidebar.number_input("Page", min_value=1, value=params.get("page", 1))
params["page_size"] = st.sidebar.number_input("Size", min_value=1, max_value=200, value=params.get("page_size", 20))

load_button_pressed = st.sidebar.button("Load Documents", key="load_btn")

if load_button_pressed:
    st.session_state.active_tab = "search_documents" # Switch to search tab on button press
    st.session_state.params = params # Store current params in session state

# ─── Main Area with Tabs ───────────────────────────────────────────────────────
# Define tab keys for referencing
tab_keys = ["about_cairn", "search_documents", "tag_definitions"]
tab_titles = ["ℹ️ About CAIRN", "🔍 Search Documents", "🏷️ Tag Definitions"]

# Determine which tab should be active
try:
    selected_tab_key = st.session_state.active_tab
except AttributeError: # Should not happen with initialization above, but good practice
    selected_tab_key = tab_keys[0]


about_tab_content, search_tab_content, tags_tab_content = st.tabs(tab_titles)


# --- Content for About Tab ---
if about_tab_content: # This is how Streamlit handles tab selection now
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

    tag_data = {
        'Tag Name (Filter)': [
            "Org or Utility Name", "Document Author", "Document Type", "Document Subtype", # New Order - Group 1
            "State or Region", "Jurisdiction", "Regulatory Body", # New Order - Group 2
            "Document Id", "Document Title", "Description", "Published Date",
            "Docket Number", "Document Url", "Cairn Url",
            "Rate Impact", "Utility Reform", "Energy Resources", "Customer Classes", "Ders",
            "Physical Climate Risk", "Additional Keywords", "Tagger", "Date Tagged", "Quality Check",
            "Processing Notes",
            "Parent Document", "Related Documents", "Replaces Document", "Relationship Types",
            "File Format", "Local Backup Name",
            "Last Synced", "Updated At",
        ],
        'Description': [
            "The primary utility, organization, or agency associated with the document", # org_utility_name
            "The individual, firm, or entity that authored the document", # document_author
            "The main category or classification of the document", # document_type
            "A more specific sub-category of the document", # document_subtype
            "The primary geographic state or region the document pertains to", # state_region
            "The level of regulatory authority (e.g., State-Level, National)", # jurisdiction_type
            "The primary regulatory agency with jurisdiction (e.g., PUC, FERC)", # regulatory_body
            "Unique identifier for the document record (e.g., C250001)",
            "Full official title of the document",
            "Brief summary or description of the document content",
            "The date the document was published or filed (YYYY-MM-DD)",
            "The official proceeding number (e.g., UE-230810)",
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
            "The File ID of a parent document this document belongs to (e.g., for appendices)",
            "Comma-separated File IDs of other documents related to this one",
            "The File ID of a document that this document replaces or supersedes",
            "Describes the relationship to parent/related documents (e.g., Appendix, Comment)",
            "The format of the file (e.g., PDF, DOCX)",
            "Internal filename used for local backup storage",
            "Date the document record was last synchronized with its source (YYYY-MM-DD)",
            "Date the document record was last modified in the database (YYYY-MM-DD)",
        ],
        'Filter Input Type / Format': [
            "Text (e.g., Puget Sound Energy (PSE))", "Text", "Text", "Text", # Group 1
            "Text (e.g., WA, CA)", "Text", "Text (e.g., WA_UTC)", # Group 2
            "Text", "Text", "Text", "Date Picker",
            "Text (e.g., UE-#####)", "Text (URL)", "Text (URL)",
            "Text (e.g., Y, N)", "Text (e.g., Y, N)", "Text (comma-separated, e.g., solar, storage)", "Text (comma-separated, e.g., residential, C&I)", "Text (comma-separated)",
            "Checkbox (sends 'true' if checked)", "Text (comma-separated)", "Text", "Date Picker", "Text (e.g., Y, N)",
            "Text",
            "Text (File ID)", "Text (comma-separated File IDs)", "Text (File ID)", "Text (comma-separated)",
            "Text (e.g., PDF)", "Text",
            "Date Picker", "Date Picker",
        ]
    }
    tag_definitions_df = pd.DataFrame(tag_data)
    st.dataframe(tag_definitions_df, use_container_width=True, height=600)


# ─── Search Tab Content ────────────────────────────────────────────────────────
if search_tab_content:
    st.info("Use the filters in the sidebar and click 'Load Documents' to fetch and display data here.")

    if load_button_pressed or 'docs_df' in st.session_state and not st.session_state.docs_df.empty : # If button was just pressed OR if data already exists
        # --- Data Fetching (only if button pressed, subsequent views use existing data) ---
        if load_button_pressed: # Only fetch if the button initiated this
            with st.spinner('Fetching documents...'):
                try:
                    active_params = {k: v for k, v in st.session_state.params.items() if v is not None and str(v).strip() != ''}
                    resp = requests.get(DOCUMENTS_API_URL, params=active_params, timeout=45)
                    resp.raise_for_status()
                    docs_data = resp.json()
                    docs = docs_data.get("data", [])
                    total_docs = docs_data.get("total_count", len(docs))
                    current_page = active_params.get('page', 1); page_size = active_params.get('page_size', 20)
                    total_pages = (total_docs + page_size - 1) // page_size if total_docs > 0 else 1
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
            search = st.text_input("🔎 Quick Search current results", key="quick_search_input");
            if search: df_display_final = df_display_base[df_display_base.apply(lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1)]
            else: df_display_final = df_display_base

            gb = GridOptionsBuilder.from_dataframe(df_display_final)
            gb.configure_default_column(groupable=True, filter="agTextColumnFilter", filterParams={"debounceMs": 300}, sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150)
            link_cols = ["Document URL", "CAIRN URL"]
            for link_col in link_cols:
                 if link_col in df_display_final.columns: gb.configure_column(link_col, cellRenderer='''function(params){return params.value?'<a href="'+params.value+'" target="_blank" rel="noopener noreferrer">'+params.value+'</a>':''}''', minWidth=250)
            if "Description" in df_display_final.columns:
                 gb.configure_column("Description", minWidth=300)
            gb.configure_side_bar(filters_panel=True, columns_panel=True)
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
                out_df_view = pd.DataFrame(st.session_state.grid_response["data"])
                if not out_df_view.empty:
                    ts = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S'); csv_fn = f"cairn_{ts}.csv"
                    csv_data = out_df_view.to_csv(index=False).encode('utf-8')
                    st.download_button(label="⬇️ CSV", data=csv_data, file_name=csv_fn, mime="text/csv", key='csv_btn')
                else: st.button("⬇️ CSV", disabled=True, key='csv_btn_dis')

            selected_rows_data = None
            grid_response_current = st.session_state.get('grid_response')
            if grid_response_current:
                selected_rows_data = grid_response_current.get("selected_rows")

            is_valid_selection = isinstance(selected_rows_data, pd.DataFrame) and not selected_rows_data.empty

            if is_valid_selection:
                with col_actions2:
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

            else:
                with col_actions2: st.button("📄 PDF Link", disabled=True, key='pdf_btn_no_sel')
                st.markdown("---"); st.caption("Select rows for details/download.")

        elif load_button_pressed and st.session_state.docs_df.empty:
            pass # Warning already shown inside data fetching block

    elif not load_button_pressed and st.session_state.docs_df.empty :
         # This state is when the tab is selected but no button has been pressed yet
         # and no data is loaded. The initial info message is sufficient.
         pass


# Make sure the correct tab is shown based on st.session_state.active_tab
# This needs to be handled carefully with how st.tabs now works.
# The new st.tabs directly gives you a boolean for which tab is active.
# The logic for switching tabs is handled when the "Load Documents" button is pressed by updating st.session_state.active_tab
# For the initial render, or if the user clicks a tab, Streamlit handles the active tab.
# The `selected_tab_key` logic was more for older Streamlit versions or more complex tab management.
# The current structure where each tab content is conditionally rendered `if about_tab_content:` etc., is the standard way.

# Ensure the correct tab is visually selected if changed programmatically.
# Streamlit's new tab behavior might make explicit selection tricky without a full rerun.
# The button click causes a rerun, and `st.session_state.active_tab` being set before `st.tabs` *should* influence it,
# but `st.tabs` itself doesn't have a direct `default_selected_index` or similar after the initial call.
# The approach taken (setting session state and having st.tabs re-evaluate) is the most Streamlit-idiomatic way.

# Small adjustment for how st.tabs() works:
# The active tab is determined by which variable (about_tab_content, search_tab_content, etc.) is True.
# To "select" a tab programmatically, you typically manage this state and ensure only one is true,
# or rely on Streamlit's default behavior on rerun.
# The `st.session_state.active_tab` is now primarily used to remember the tab across reruns if needed,
# and to trigger the switch when the button is pressed.
# The actual rendering of tabs and their content is correctly handled by the `if search_tab_content:` blocks.

# Switch active tab if "Load Documents" was pressed
# This will be handled on the next re-run.
if load_button_pressed:
    # The change to st.session_state.active_tab will persist.
    # To force the tab switch visually *immediately* without direct control in st.tabs,
    # this is a common pattern. The next time st.tabs is called, it should reflect this.
    # However, Streamlit's st.tabs doesn't have an explicit "select_tab" method.
    # The best we can do is set the state and let Streamlit's rerun reflect it.
    # In recent Streamlit versions, simply ensuring the content of the desired tab
    # is rendered (which our if load_button_pressed and subsequent logic does)
    # effectively "switches" to it because that tab's content block becomes active.
    pass


# Optional Footer (Uncomment if desired)
# st.markdown("---")
# st.caption("CAIRN Project | Powered by Streamlit")