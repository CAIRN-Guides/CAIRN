import streamlit as st

st.set_page_config(
    page_title="CAIRN",
    page_icon="📚",
    layout="wide"
)

st.title("📚 CAIRN: AI-Driven Doc Aggregation and Retrieval")

st.markdown(
    """
    Why CAIRN?

    CAIRN turns thousands of PDFs into a living knowledge graph you can search, tag, and interrogate in minutes instead of day to help utilities, advocates, and commissions must make faster climate‑risk decisions. 

    * **Collect** – scrape or upload filings from commissions, utilities, and intervenors.  
    * **Organise** – normalise metadata, enrich with tags, and store in a relational backbone.  
    * **Surface** – run keyword or semantic search, receive instant summaries, and (road‑mapped) chat with a RAG agent that cites its sources.
"""
)