# app.py

import os
import streamlit as st
import requests
import pandas as pd
from dotenv import load_dotenv

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# ─── Load env & page setup ─────────────────────────────────────────────────────
load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000/documents")

st.set_page_config(page_title="CAIRN Tagger", layout="wide")
st.title("📚 CAIRN Document Tagger")

# ─── Ad-hoc (patch out!) ───────────────────────────────────────────────────────
DOC_NAME = 'PSE_IRP_ElectricChapters_3.31.2025.pdf'

# ─── Sidebar filters ───────────────────────────────────────────────────────────

# ─── Fetch & display ───────────────────────────────────────────────────────────
if st.sidebar.button("Load Documents"):
    pass