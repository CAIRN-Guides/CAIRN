# app.py

import os
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# ─── Load env & page setup ─────────────────────────────────────────────────────
load_dotenv()
API_URL = os.getenv("API_URL", "https://cairn-backend.onrender.com") # Use getenv for flexibility

st.set_page_config(page_title="CAIRN Finder", layout="wide")
st.title("📚 CAIRN Document Finder")

# ─── Sidebar filters (Remains unchanged) ─────────────────────────────────────
st.sidebar.header("Filters")
params = {}

# text inputs
text_cols = [
    "document_id", "document_title", "local_backup_name", "tagger",
    "file_format", "rate_impact", "quality_check", "regulatory_body",
    "state_region", "docket_number", "document_type", "org_utility_name",
    "parent_document", "replaces_document", "document_url", "cairn_url",
    "processing_notes"
]
for col in text_cols:
    v = st.sidebar.text_input(col.replace("_"," ").title())
    if v:
        params[col] = v

# date inputs
if d := st.sidebar.date_input("Published Date", value=None):
    params["published_date"] = d.isoformat()
if d := st.sidebar.date_input("Date Tagged", value=None):
    params["date_tagged"] = d.isoformat()
if d := st.sidebar.date_input("Last Synced At", value=None):
    params["last_synced_at"] = d.isoformat()
if d := st.sidebar.date_input("Updated At", value=None):
    params["updated_at"] = d.isoformat()

# list inputs
list_cols = [
    "additional_keywords", "ders", "utility_reform",
    "customer_classes", "energy_resources",
    "related_documents", "relationship_types"
]
for col in list_cols:
    s = st.sidebar.text_input(col.replace("_"," ").title() + " (comma-separated)")
    if s:
        params[col] = [x.strip() for x in s.split(",") if x.strip()]

# boolean
if st.sidebar.checkbox("Physical Climate Risk"):
    params["physical_climate_risk"] = True

# pagination & options
st.sidebar.header("Options")
params["page"]      = st.sidebar.number_input("Page Number", min_value=1, value=1)
params["page_size"] = st.sidebar.number_input("Page Size",   min_value=1, max_value=200, value=20)
params["include_download_url"] = st.sidebar.checkbox("Include Download URL", value=False)

# The "Load Documents" button stays in the sidebar
load_button_pressed = st.sidebar.button("Load Documents")

# ─── Main Area with Tabs ───────────────────────────────────────────────────────
about_tab, search_tab = st.tabs(["ℹ️ About CAIRN", "🔍 Search Documents"])

with about_tab:
    # --- Content for the "About CAIRN" tab ---
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
    2.  **Organizes & Tags:** Uses humans and AI (via Supabase/PostgreSQL and Google Sheets integration) to categorize documents by utility, topic, date, document type, and other key factors.
    3.  **Enables Targeted Search:** Allows you to filter and search the database (using the 'Search Documents' tab!) to find precisely the documents you need. *(Roadmap includes semantic search and RAG)*.

    By streamlining access to this information, CAIRN aims to help environmental advocates, utility planners, regulatory analysts, researchers, and concerned citizens understand the landscape, track progress, compare approaches, and contribute more effectively to shaping our energy future.

    ### Getting Started: How to Query the CAIRN Database

    1.  Click on the **'🔍 Search Documents'** tab above.
    2.  Use the **filters in the sidebar** on the left to narrow down the vast collection of documents. Specify criteria like document type, utility name, date range, or keywords.
    3.  Once you've set your filters, click the **"Load Documents"** button in the sidebar to fetch the results.
    4.  The table will populate within the 'Search Documents' tab. You can then sort, filter, search, download, and view details as needed.

    """)

with search_tab:
    # --- Content for the "Search Documents" tab ---
    st.info("Use the filters in the sidebar and click 'Load Documents' to fetch and display data here.")

    # The entire data fetching and display logic goes inside this tab
    # and only executes if the button in the sidebar was pressed.
    if load_button_pressed:
        with st.spinner('Fetching documents from CAIRN...'):
            try:
                resp = requests.get(API_URL, params=params, timeout=30) # Add a timeout
                resp.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

                docs_data = resp.json()
                docs = docs_data.get("data", [])
                total_docs = docs_data.get("total_count", len(docs)) # Try to get total count if API provides it
                current_page = params.get('page', 1)
                page_size = params.get('page_size', 20)
                total_pages = (total_docs + page_size - 1) // page_size if total_docs else 1

                st.write(f"Showing **{len(docs)}** of **{total_docs}** documents (Page {current_page} of {total_pages})")

                if not docs:
                    st.warning("No documents found matching your criteria.") # Changed to warning as info is used above
                    st.stop()

                # --- Build DataFrame & flatten list columns ---
                df = pd.DataFrame(docs)
                for lc in list_cols:
                    if lc in df.columns:
                        # Ensure we handle None or non-list values gracefully
                        df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                # --- Reorder & rename columns ---
                cols_order_original = [
                    "document_id", "local_backup_name", "tag_id", "document_title",
                    "published_date", "document_author", "org_utility_name",
                    "docket_number", "document_type", "document_subtype",
                    "document_url", "cairn_url", "rate_impact", "utility_reform",
                    "energy_resources", "customer_classes", "ders",
                    "physical_climate_risk", "additional_keywords", "tagger",
                    "date_tagged", "quality_check", "processing_notes",
                    "state_region", "regulatory_body", "jurisdiction_type",
                    "parent_document", "related_documents", "replaces_document",
                    "relationship_types"
                ]
                cols_to_display = [col for col in cols_order_original if col in df.columns]
                df = df[cols_to_display]


                rename_map = {
                    "document_id":         "File ID",
                    "local_backup_name":   "Local Backup Name",
                    "tag_id":              "Tag ID",
                    "document_title":      "Document Title",
                    "published_date":      "Published Date",
                    "document_author":     "Document Author",
                    "org_utility_name":    "Org/Utility Name",
                    "docket_number":       "Docket Number",
                    "document_type":       "Document Type",
                    "document_subtype":    "Document Subtype",
                    "document_url":        "Document URL",
                    "cairn_url":           "CAIRN URL",
                    "rate_impact":         "Rate Impact",
                    "utility_reform":      "Utility Reform",
                    "energy_resources":    "Energy Resources",
                    "customer_classes":    "Customer Classes",
                    "ders":                "DERs",
                    "physical_climate_risk": "Physical Climate Risk",
                    "additional_keywords": "Additional Keywords",
                    "tagger":              "Tagger",
                    "date_tagged":         "Date Tagged",
                    "quality_check":       "Quality Check",
                    "processing_notes":    "Processing Notes",
                    "state_region":        "State/Region",
                    "regulatory_body":     "Regulatory Body",
                    "jurisdiction_type":   "Jurisdiction Type",
                    "parent_document":     "Parent Document",
                    "related_documents":   "Related Documents",
                    "replaces_document":   "Replaces Document",
                    "relationship_types":  "Relationship Types",
                }
                df_renamed = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

                # --- Quick-search across all fields ---
                search = st.text_input("🔎 Quick Search current results", key="quick_search_input") # Add key
                if search:
                    mask = df_renamed.apply(lambda row: row.astype(str)
                                              .str.contains(search, case=False, na=False)
                                              .any(), axis=1)
                    df_display = df_renamed[mask]
                else:
                    df_display = df_renamed

                # --- Configure AgGrid ---
                gb = GridOptionsBuilder.from_dataframe(df_display)
                gb.configure_default_column(
                    filter="agTextColumnFilter",
                    filterParams={"debounceMs": 300},
                    sortable=True,
                    resizable=True,
                    wrapText=True,
                    autoHeight=True,
                    minWidth=150
                )
                if "Document URL" in df_display.columns:
                     gb.configure_column("Document URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank">'+ params.value +'</a>' : ''; }''')
                if "CAIRN URL" in df_display.columns:
                     gb.configure_column("CAIRN URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank">'+ params.value +'</a>' : ''; }''')

                gb.configure_side_bar(filters_panel=True, columns_panel=True)
                gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=params["page_size"])
                gb.configure_selection(selection_mode="multiple", use_checkbox=True)
                gb.configure_grid_options(domLayout='normal')
                grid_opts = gb.build()

                grid_response = AgGrid(
                    df_display,
                    gridOptions=grid_opts,
                    key='document_grid', # Add a key to the grid
                    enable_enterprise_modules=False,
                    update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
                    data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                    fit_columns_on_grid_load=False,
                    height=600,
                    width='100%',
                    reload_data=True,
                    allow_unsafe_jscode=True, # Needed for cellRenderer link formatting
                )

                # --- Download current view as CSV ---
                out_df = pd.DataFrame(grid_response["data"])
                if not out_df.empty:
                     csv = out_df.to_csv(index=False).encode('utf-8')
                     st.download_button(
                         "⬇️ Download current view as CSV",
                         data=csv,
                         file_name="cairn_documents_export.csv",
                         mime="text/csv",
                         key='csv_download'
                     )

                # --- Detail pane for selected rows ---
                selected = grid_response["selected_rows"]
                if selected:
                    sel_df = pd.DataFrame(selected).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                    st.markdown("### 📄 Selected Document Details")
                    if len(sel_df) == 1:
                        # Display transposed view for single selection
                        st.dataframe(sel_df.iloc[0])
                    else:
                        # Display standard table for multiple selections
                        st.dataframe(sel_df, use_container_width=True)

            except requests.exceptions.RequestException as e:
                st.error(f"API Request Failed: {e}")
            except Exception as e:
                st.error(f"An error occurred while processing data in the Search tab: {e}")
                import traceback
                st.error(traceback.format_exc()) # Show full traceback for debugging


# If you have any code that should always be at the bottom, outside the tabs,
# it can go here. For example, a footer:
# st.markdown("---")
# st.caption("CAIRN Project | Powered by Streamlit")