


# Project CAIRN: Climate & Energy Document Navigator

## 1. Why CAIRN?

Navigating the thousands of PDF documents in energy utility regulation—filings, dockets, IRPs, and testimonies—is a monumental task. CAIRN transforms this landscape into an accessible knowledge base, empowering utilities, advocates, and commissions to make faster, more informed climate-risk decisions.

* **Collect:** Ingest PDF documents from local storage or other sources.
* **Organize:** Metadata is managed via Google Sheets, synchronized to a Supabase/PostgreSQL database, and linked to original PDF files stored securely in Backblaze B2.
* **Surface & Access:** Users interact with a Streamlit web application to:
    * Query and filter documents based on rich metadata.
    * View detailed document information.
    * Select and download individual or batches of PDF documents directly through a secure backend proxy.
* **Future Roadmap:** Includes semantic search capabilities and a RAG (Retrieval Augmented Generation) agent for conversational Q&A with source citations.

---

## 2 System Architecture

```
┌──────────────┐   files   ┌──────────────┐   sync   ┌──────────────┐
│  Backblaze   │─────────▶ │  Supabase    │◀────────▶│ Google‑Sheets│
│     B2       │           │ PostgreSQL   │          │  Metadata    │
└──────────────┘           └────┬─────────┘          └──────────────┘
                                │
                                ▼
                        ┌────────────────────────┐
                        │ Front End: Streamlight │
                        │  Backend: Render       │     
                        └────────────────────────┘



* **Local PDF Storage:** The initial source for PDF documents.
* **Google Sheets:** Serves as a user-friendly interface for inputting and managing document metadata.
* **Python Sync Script (Jupyter Notebook):**
    * Reads metadata from Google Sheets.
    * Upserts this metadata into the Supabase PostgreSQL database.
    * Identifies corresponding PDF files in the local storage.
    * Uploads these PDFs to Backblaze B2 if not already present.
    * Updates Supabase with the B2 file identifier (`b2_file_id`).
* **Supabase (PostgreSQL Database):** The central relational backbone for structured metadata, including the crucial `b2_file_id` linking to files in B2.
* **Backblaze B2:** Secure and cost-effective cloud storage for the original PDF documents.
* **FastAPI Backend API:**
    * Provides an endpoint (`/documents`) for the frontend to query and filter document metadata from Supabase.
    * Offers endpoints (`/documents/.../download-url`) to generate secure, short-lived proxy URLs for downloading files.
    * Includes a proxy endpoint (`/api/b2-proxy/...`) that securely streams files from Backblaze B2 to the user, keeping B2 credentials private.
* **Streamlit Frontend Application:** Allows users to:
    * Dynamically filter and search for documents based on the metadata in Supabase.
    * View search results in an interactive table.
    * Select one or more documents.
    * Initiate downloads, which are served via the FastAPI backend proxy from B2.

---

## 3. Core Components & Key Capabilities (Implemented)

### 3.1. Document Storage – Backblaze B2
* **Reliable Object Storage:** Stores original PDF documents.
* **Accessed via Backend Proxy:** PDFs are delivered to users through a secure FastAPI proxy, not direct B2 links, protecting credentials and managing access.

### 3.2. Relational Backbone – Supabase (PostgreSQL)
* **Structured Metadata:** Hosts the `files` table and other relational data. Key fields include `document_id`, `source_file_id`, `document_title`, `published_date`, various tags (as text or arrays), and the critical `b2_file_id`.
* **Data Source for API:** The FastAPI backend queries this database to serve the frontend.
* **Unique Identifiers:** Uses `document_id` (from Google Sheets "Tag ID") for upserting metadata.

### 3.3. Metadata Management – Google Sheets & Python Sync Script
* **User-Friendly Input:** Google Sheets provides a familiar interface for inputting and editing document metadata.
* **Automated Synchronization:** A Python script (runnable in a Jupyter Notebook):
    * Pulls metadata from a designated Google Sheet.
    * Cleans and transforms data.
    * Upserts metadata records to the Supabase `files` table.
    * Locates corresponding PDF files from a local directory based on a "File ID" from the sheet.
    * Uploads these PDFs to Backblaze B2.
    * Updates Supabase records with the `b2_file_id` from B2.

### 3.4. Backend API – FastAPI
* **Serves Metadata:** Exposes an endpoint for the Streamlit frontend to query document metadata.
* **Secure Downloads:** Provides endpoints to generate relative proxy URLs and a dedicated proxy endpoint to stream files from B2 to the user, abstracting B2 access. This is key for allowing users to download selected PDFs.

### 3.5. User Interface – Streamlit
* **Interactive Search & Filter:** Users can filter documents based on multiple metadata fields.
* **Document Display:** Shows query results in an interactive table using `st-aggrid`.
* **PDF Download Functionality:** Users can select documents via checkboxes in the table and trigger a download. The frontend communicates with the FastAPI backend to obtain a proxied download link for single or multiple (zipped) files.

---

## 4. Getting Started

1.  **Set up Environment:**
    * Clone the repository.
    * Configure `.env` files for the Python sync script (Supabase, Google Sheets, B2 credentials, local PDF path) and the Streamlit frontend/FastAPI backend (API URL).
2.  **Prepare Data:**
    * Populate your Google Sheet with document metadata. Ensure the "File ID" column matches the base names of your local PDF files.
    * Place corresponding PDF files in the local directory specified in the sync script's `.env` file.
3.  **Run Sync Script:** Execute the Jupyter Notebook cells for the sync script to:
    * Load metadata from Google Sheets into Supabase.
    * Upload local PDFs to Backblaze B2 and link them in Supabase.
4.  **Deploy/Run Backend & Frontend:**
    * Run the FastAPI backend application.
    * Run the Streamlit frontend application.
5.  **Access CAIRN:** Open the Streamlit application in your browser to search and download documents.

---

## 5. Contributing

PRs and issues are welcome! Please open a discussion for major features.

---

## 6. License

MIT.

---
