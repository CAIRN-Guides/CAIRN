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
API_BASE_URL = os.getenv("API_URL", "https://cairn-backend.onrender.com") # Default URL
DOCUMENTS_API_URL = f"{API_BASE_URL.rstrip('/')}/documents"
st.set_page_config(page_title="CAIRN Finder", layout="wide")

# --- Initialize Session State (as per user's reference code) ---
if 'docs_df' not in st.session_state: st.session_state.docs_df = pd.DataFrame()
if 'grid_response' not in st.session_state: st.session_state.grid_response = None

# ─── Header ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 5])
with col1:
    try: st.image("https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp", width=40)
    except Exception as img_err: st.warning(f"Could not load logo: {img_err}")
with col2: st.title("CAIRN Document Finder")

# ─── Sidebar filters (New Layout, Old Param Handling) ───────────────────────────
st.sidebar.header("Filters")
params = {} # Local params dictionary, populated on each run

# Group 1 Filters
val = st.sidebar.text_input("Org or Utility Name")
if val: params["org_utility_name"] = val

val = st.sidebar.text_input("Document Author")
if val: params["document_author"] = val

val = st.sidebar.text_input("Document Type")
if val: params["document_type"] = val

val = st.sidebar.text_input("Document Subtype")
if val: params["document_subtype"] = val

st.sidebar.markdown("---") # Break in the sidebar

# Group 2 Filters
val = st.sidebar.text_input("State or Region")
if val: params["state_region"] = val

val = st.sidebar.text_input("Jurisdiction") # Using the new, more user-friendly label
if val: params["jurisdiction_type"] = val # Maps to the backend parameter name

val = st.sidebar.text_input("Regulatory Body")
if val: params["regulatory_body"] = val

# "Load Documents" button comes right after "Regulatory Body"
load_button_pressed = st.sidebar.button("Load Documents", key="load_btn")

# Options section after the "Load Documents" button
st.sidebar.header("Options")
params["page"] = st.sidebar.number_input("Page", min_value=1, value=1)
params["page_size"] = st.sidebar.number_input("Size", min_value=1, max_value=200, value=20)

# ─── Main Area with Tabs (Reverted to User's Reference Logic) ───────────────────
about_tab, search_tab, tags_tab = st.tabs([
    "ℹ️ About CAIRN",
    "🔍 Search Documents",
    "🏷️ Tag Definitions"
])

# --- Content for About Tab (from user's reference) ---
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

    1.  Review the **🏷️ Tag Definitions** tab to understand the available search fields and common terms. Currently search only matches EXACTLY.
    2.  Click on the **🔍 Search Documents** tab.
    3.  Use the **filters in the sidebar** on the left to narrow down the vast collection of documents.
    4.  Once filters are set, click the **"Load Documents"** button in the sidebar.
    5.  The table will populate within the **🔍 Search Documents** tab. You can then sort, filter, search, download, and view details.
    """)

# --- Content for Tags Tab (MODIFIED SECTION) ---
with tags_tab:
    st.info("""
    This table displays the primary filter categories available in the sidebar for searching documents.
    For each category, the top terms (and their occurrence counts in the dataset) are listed to provide insight into common values.
    Use these filter categories in the sidebar on the '🔍 Search Documents' tab to refine your search.
    """)

    # Data for the new Tag Definitions Tab based on the "Top 3 Table"
    # Note: <br> from your input has been replaced with \n for better display in st.dataframe
    top_3_data = {
        'Filter Name (Category)': [
            "Org or Utility Name",
            "Document Author",
            "Document Type",
            "Document Subtype",
            "State or Region",
            "Jurisdiction",
            "Regulatory Body"
        ],
        'Top 3 Examples - Search Using Exact Matches': [
            "1. Seattle City Light (SCL) \n | Puget Sound Energy (PSE) | Avista WA | SnoPUD   ", 
            "1. Seattle City Light (SCL) | \n PNUCC ",
            "1. IRP/ISP \n | Rate Schedule ",
            "1. Rate Summary | \n IRP | Utility Association ", # Combined 2nd/3rd if counts are same
            "1. WA \n | PNW Region ",
            "1. State Level \n Regional Level ",
            "1. WA UTC |\n BPA / PNW "
        ]
    }
    tags_display_df = pd.DataFrame(top_3_data)

    # Display the DataFrame
    # st.dataframe will typically wrap text containing newline characters (\n)
    st.dataframe(tags_display_df, use_container_width=True, hide_index=True)

    st.markdown("""
    ---
    **Understanding the Table:**
    * **Filter Name (Category):** These are the labels for the filters you can use in the sidebar to narrow down your document search.
    * **Top 3 Examples (with count):** These are the most frequently occurring terms found in the dataset for that specific filter category. The number in parentheses (e.g., "(9)") indicates how many documents are associated with that term. This helps you understand common values and data distribution.
    """)
# ─── Search Tab Content (Reverted to User's Reference Logic) ───────────────────
with search_tab:
    st.info("Use the filters in the sidebar and click 'Load Documents' to fetch and display data here.")

    if load_button_pressed:
        with st.spinner('Fetching documents...'):
            try:
                # active_params uses the local 'params' dictionary populated by the sidebar
                active_params = {k: v for k, v in params.items() if v is not None and str(v).strip() != ''}
                resp = requests.get(DOCUMENTS_API_URL, params=active_params, timeout=45)
                resp.raise_for_status()
                docs_data = resp.json()
                docs = docs_data.get("data", [])
                total_docs = docs_data.get("total_count", len(docs))
                current_page_val = active_params.get('page', 1)
                page_size_val = active_params.get('page_size', 20)
                total_pages = (total_docs + page_size_val - 1) // page_size_val if total_docs > 0 else 1
                st.write(f"Showing **{len(docs)}** of **{total_docs}** documents (Page {current_page_val} of {total_pages})")

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

    # --- Display AgGrid and Actions (this part is outside the `if load_button_pressed` block in user's reference) ---
    # It relies on st.session_state.docs_df being populated.
    if not st.session_state.docs_df.empty:
        df_display_base = st.session_state.docs_df
        search_val = st.text_input("🔎 Quick Search current results", key="quick_search_input"); # Renamed variable
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
        # params.get('page_size', 20) is from the local params dict defined in the sidebar for the current run
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=params.get('page_size', 20))
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
            # Ensure grid_response["data"] is valid before processing
            current_grid_data = st.session_state.grid_response.get("data") if st.session_state.grid_response else None
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
                    st.error("Error: 'DB ID' missing.") # Error from user's reference
                    st.button("📄 PDF Link", disabled=True, key='pdf_btn_no_id')
                else:
                    selected_pks = sel_df["DB ID"].dropna().tolist() # Added dropna for robustness
                    num_sel = len(selected_pks)
                    btn_label = f"📄 PDF Link ({num_sel} selected)"

                    if not selected_pks: # Handle case where selection might result in no valid DB IDs
                        st.button(btn_label, disabled=True, key="pdf_trigger_btn_no_valid_pks")
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
                                    resp = None

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
        # This case is when the button was pressed, API call was made (or attempted),
        # but no docs were found or an error occurred.
        # Warnings/errors are shown inside the data fetching block.
        pass
    # else: # Initial state: load_button_pressed is False and docs_df is empty.
        # The st.info message at the top of the 'with search_tab:' block is displayed.

# Optional Footer
# st.markdown("---")
# st.caption("CAIRN Project | Powered by Streamlit")
