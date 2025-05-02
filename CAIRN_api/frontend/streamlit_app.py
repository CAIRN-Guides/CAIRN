# app.py (v1.2)

import os
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv
from PIL import Image # Needed for st.image with local files potentially
import streamlit as st # Make sure you have this import
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# ─── Load env & page setup ─────────────────────────────────────────────────────
load_dotenv()
API_URL = os.getenv("API_URL", "https://cairn-backend.onrender.com") # Use getenv for flexibility

st.set_page_config(page_title="CAIRN Finder", layout="wide")

# ─── Title and Logo Area ───────────────────────────────────────────────────────
col1, col2 = st.columns([4, 1]) # Ratio of width for title vs image

with col1:
    st.title("📚 CAIRN Document Finder")

with col2:
# --- Add your image here ---
# Use the specific RAW GitHub content URL obtained by clicking "Raw"
    image_url = "https://raw.githubusercontent.com/CAIRN-Guides/CAIRN/refs/heads/feature/api-ui-refresh/CAIRN_api/CAIRN_BW_Photo_4.13.25.webp"

# Display the image using Streamlit
    st.image(image_url,
            caption='CAIRN BW Photo', # Optional: Add a caption
            width=100) # Adjust width as needed

    # Option 2: Use a local file (uncomment the lines below)
    # Make sure 'cairn_logo.png' is in the same directory as app.py
    # or provide the correct path e.g., 'images/cairn_logo.png'
    # try:
    #     logo = Image.open('cairn_logo.png') # Replace with your image filename/path
    #     st.image(logo, width=100) # Adjust width as needed
    # except FileNotFoundError:
    #     st.warning("Logo image file not found.")


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
about_tab, search_tab, tags_tab = st.tabs([
    "ℹ️ About CAIRN",
    "🔍 Search Documents",
    "🏷️ Tag Definitions"
])

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
    # --- Content for the "Search Documents" tab ---
    st.info("Use the filters in the sidebar and click 'Load Documents' to fetch and display data here.")

    # The entire data fetching and display logic goes inside this tab
    # and only executes if the button in the sidebar was pressed.
    if load_button_pressed:
        with st.spinner('Fetching documents from CAIRN...'):
            try:
                resp = requests.get(API_URL, params=params, timeout=30)
                resp.raise_for_status()

                docs_data = resp.json()
                docs = docs_data.get("data", [])
                total_docs = docs_data.get("total_count", len(docs))
                current_page = params.get('page', 1)
                page_size = params.get('page_size', 20)
                total_pages = (total_docs + page_size - 1) // page_size if total_docs else 1

                st.write(f"Showing **{len(docs)}** of **{total_docs}** documents (Page {current_page} of {total_pages})")

                if not docs:
                    st.warning("No documents found matching your criteria.")
                    # st.stop() # Removed stop() to allow interaction even with no results initially

                else: # Only process and display if docs are found
                    # --- Build DataFrame & flatten list columns ---
                    df = pd.DataFrame(docs)
                    for lc in list_cols:
                        if lc in df.columns:
                            df[lc] = df[lc].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)

                    # --- Reorder & rename columns ---
                    cols_order_original = [
                        "document_id", "local_backup_name", #"tag_id", # Excluded based on previous analysis
                        "document_title", "published_date", "document_author", "org_utility_name",
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
                    search = st.text_input("🔎 Quick Search current results", key="quick_search_input")
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
                        filter="agTextColumnFilter", filterParams={"debounceMs": 300},
                        sortable=True, resizable=True, wrapText=True, autoHeight=True, minWidth=150
                    )
                    if "Document URL" in df_display.columns:
                         gb.configure_column("Document URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''')
                    if "CAIRN URL" in df_display.columns:
                         gb.configure_column("CAIRN URL", cellRenderer='''function(params) { return params.value ? '<a href="' + params.value + '" target="_blank" rel="noopener noreferrer">'+ params.value +'</a>' : ''; }''') # Added rel="noopener noreferrer"

                    gb.configure_side_bar(filters_panel=True, columns_panel=True)
                    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=params["page_size"])
                    gb.configure_selection(selection_mode="multiple", use_checkbox=True)
                    gb.configure_grid_options(domLayout='normal')
                    grid_opts = gb.build()

                    grid_response = AgGrid(
                        df_display,
                        gridOptions=grid_opts, key='document_grid',
                        enable_enterprise_modules=False,
                        update_mode=GridUpdateMode.MODEL_CHANGED | GridUpdateMode.SELECTION_CHANGED,
                        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                        fit_columns_on_grid_load=False, height=600, width='100%',
                        reload_data=True, allow_unsafe_jscode=True,
                    )

                    # --- Download current view as CSV ---
                    out_df = pd.DataFrame(grid_response["data"])
                    if not out_df.empty:
                         csv = out_df.to_csv(index=False).encode('utf-8')
                         st.download_button(
                             "⬇️ Download current view as CSV", data=csv,
                             file_name="cairn_documents_export.csv", mime="text/csv",
                             key='csv_download'
                         )

                    # --- Detail pane for selected rows ---
                    selected = grid_response["selected_rows"]
                    if selected:
                        sel_df = pd.DataFrame(selected).drop(columns=["_selectedRowNodeInfo"], errors="ignore")
                        st.markdown("### 📄 Selected Document Details")
                        if len(sel_df) == 1:
                            st.dataframe(sel_df.iloc[0])
                        else:
                            st.dataframe(sel_df, use_container_width=True)

            except requests.exceptions.RequestException as e:
                st.error(f"API Request Failed: {e}")
            except Exception as e:
                st.error(f"An error occurred while processing data in the Search tab: {e}")
                import traceback
                st.error(traceback.format_exc())


with tags_tab:
    # --- Content for the "Tag Definitions" tab ---
    st.info("""
    This table explains the different fields (tags) used to categorize documents in CAIRN.
    You can use the filters in the sidebar (under the '🔍 Search Documents' tab) to search based on these fields and terms.
    """)

    # Define the tag data (based on parsing your provided info and AgGrid columns)
    tag_data = {
        'Tag Name (Filter)': [
            "File ID", "Document Title", "Published Date", "Document Author", "Org/Utility Name",
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
            "The individual, firm, or entity that authored the document",
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
            "CYY##### format", "Text", "YYYY-MM-DD", "Text", "PSE, Avista, PGE, CAISO, PNNL",
            "UE-#####, UG-#####, etc.", "IRP/ISP, Assessment, Comment, Report, Regulatory Rate Plan", "Electric IRP, Gas IRP, Comment, Clean_Energy_Party, Integrated Resource Plan", "URL", "URL",
            "Y, N", "Y, N, Partial", "All, Gas, Solar, Storage, EE, Clean_Energy", "All, Residential, C&I", "Y, N",
            "Y, N", "IRP, Resilience, Decarbonization, MYRP", "Text (e.g., Apples)", "YYYY-MM-DD", "Y, N, Pending",
            "Text", "WA, CA, OR, Multi-state, National", "WA_UTC, Oregon PUC, CAISO, FERC, CPUC", "State-Level, National",
            "CYY##### format", "CYY##### format (comma-sep)", "CYY##### format", "Appendix, IRP_Comment, Staff_Comment"
        ]
    }
    tag_definitions_df = pd.DataFrame(tag_data)

    # Display the DataFrame
    st.dataframe(tag_definitions_df, use_container_width=True, height=600) # Use dataframe for scrollbars

# Optional Footer
# st.markdown("---")
# st.caption("CAIRN Project | Powered by Streamlit")