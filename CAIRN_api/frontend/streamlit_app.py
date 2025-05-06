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

# ─── Header ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 5])
with col1:
    try: st.image("https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/main/CAIRN_api/frontend/CAIRN_BW_Photo_4.13.25.webp", width=40)
    except Exception as img_err: st.warning(f"Could not load logo: {img_err}")
with col2: st.title("CAIRN Document Finder")

# ─── Sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.header("Filters")
params = {}
text_cols = ["document_id", "document_title", "local_backup_name", "tagger", "file_format", "rate_impact", "quality_check", "regulatory_body", "state_region", "docket_number", "document_type", "org_utility_name", "parent_document", "replaces_document", "document_url", "cairn_url", "processing_notes"]
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
about_tab, search_tab, tags_tab = st.tabs(["ℹ️ About", "🔍 Search", "🏷️ Tags"])
with about_tab: st.markdown("{Placeholder}")
with tags_tab: st.markdown("{Placeholder}")

# ─── Search Tab Content ────────────────────────────────────────────────────────
with search_tab:
    st.info("Use filters and click 'Load Documents'.")

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
                st.write(f"Showing {len(docs)} of {total_docs} (Page {current_page}/{total_pages})")

                if not docs:
                    st.warning("No documents found."); st.session_state.docs_df = pd.DataFrame()
                else:
                    df = pd.DataFrame(docs)
                    list_cols_fmt = ["additional_keywords", "ders", "utility_reform", "customer_classes", "energy_resources", "related_documents", "relationship_types"]
                    for lc in list_cols_fmt:
                        if lc in df.columns and df[lc].apply(lambda x: isinstance(x, list)).any():
                            df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)
                    cols_order = ["id", "document_id", "document_title", "published_date", "org_utility_name", "docket_number", "document_type", "document_subtype", "state_region", "rate_impact", "utility_reform", "energy_resources", "customer_classes", "ders", "physical_climate_risk", "additional_keywords", "document_url", "cairn_url", "tagger", "date_tagged", "quality_check", "local_backup_name", "file_format", "processing_notes", "document_author", "regulatory_body", "jurisdiction_type", "parent_document", "related_documents", "replaces_document", "relationship_types", "b2_file_id", "created_at", "updated_at", "last_synced_at"]
                    cols_to_display = [col for col in cols_order if col in df.columns]
                    df_ordered = df[cols_to_display]
                    rename_map = {"id": "DB ID", "document_id": "File ID", "local_backup_name": "Local Backup Name", "document_title": "Document Title", "published_date": "Published Date", "document_author": "Document Author", "org_utility_name": "Org/Utility Name", "docket_number": "Docket Number", "document_type": "Document Type", "document_subtype": "Document Subtype", "document_url": "Document URL", "cairn_url": "CAIRN URL", "b2_file_id": "B2 File ID", "rate_impact": "Rate Impact", "utility_reform": "Utility Reform", "energy_resources": "Energy Resources", "customer_classes": "Customer Classes", "ders": "DERs", "physical_climate_risk": "Physical Climate Risk", "additional_keywords": "Additional Keywords", "tagger": "Tagger", "date_tagged": "Date Tagged", "quality_check": "Quality Check", "processing_notes": "Processing Notes", "state_region": "State/Region", "regulatory_body": "Regulatory Body", "jurisdiction_type": "Jurisdiction Type", "parent_document": "Parent Document", "related_documents": "Related Documents", "replaces_document": "Replaces Document", "relationship_types": "Relationship Types", "created_at": "Created At", "updated_at": "Updated At", "last_synced_at": "Last Synced At", "file_format": "File Format"}
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
        search = st.text_input("🔎 Quick Search", key="quick_search");
        if search: df_display_final = df_display_base[df_display_base.apply(lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1)]
        else: df_display_final = df_display_base

        # --- Configure AgGrid ---
        gb = GridOptionsBuilder.from_dataframe(df_display_final)
        # Use default column config (valueGetter removed)
        gb.configure_default_column(groupable=True, filter="agTextColumnFilter", filterParams={"debounceMs": 300}, sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150)
        link_cols = ["Document URL", "CAIRN URL"]
        for link_col in link_cols:
             if link_col in df_display_final.columns: gb.configure_column(link_col, cellRenderer='''function(params){return params.value?'<a href="'+params.value+'" target="_blank" rel="noopener noreferrer">'+params.value+'</a>':''}''', minWidth=250)
        gb.configure_side_bar(filters_panel=True, columns_panel=True)
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=params.get('page_size', 20))
        gb.configure_selection(selection_mode="multiple", use_checkbox=True, header_checkbox=True, rowMultiSelectWithClick=False)
        gb.configure_grid_options(domLayout='normal')
        grid_opts = gb.build()

        # --- Render AgGrid ---
        st.session_state.grid_response = AgGrid(
            df_display_final, gridOptions=grid_opts, key='document_grid_main',
            enable_enterprise_modules=False,
            update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT, # This mode returns DataFrame for selected_rows
            fit_columns_on_grid_load=False, height=600, width='100%',
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
                                        dl_url = f"{API_BASE_URL.rstrip('/')}{rel_url}"
                                        st.success("Link ready!")
                                        st.markdown(f'<a href="{dl_url}" target="_blank">{dl_fn}</a>', unsafe_allow_html=True)
                                        st.caption("Link may expire.")
                                    else: st.error("API No URL."); st.json(data)
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
            st.markdown("### 📄 Details")
            if len(sel_df_details) == 1: st.dataframe(sel_df_details.iloc[0])
            else: st.dataframe(sel_df_details, use_container_width=True)

        else:
            # --- Handle No Selection ---
            with col_actions2: st.button("📄 PDF Link", disabled=True, key='pdf_btn_no_sel')
            st.markdown("---"); st.caption("Select rows for details/download.")

    elif load_button_pressed and st.session_state.docs_df.empty: pass
    # Initial state handled implicitly