# CAIRN
See Notion for full Project Description: https://applesclimatespace.notion.site/Project-CAIRN-190f05ec7e58807f84a6fbd535c17188?pvs=4

# Project CAIRN

## Collection, Analysis, and Interpretation of Regulatory Networks

Project CAIRN is a set of tools designed to unlock innovation in energy regulation by collecting, categorizing, and using utility and intervenor documentation. It aims to create a collaborative container for projects exploring the intersection of AI advancements, utility regulation, and the policy impacts of climate risk.

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Core Components](#core-components)
  - [Document Storage (Backblaze B2)](#document-storage-backblaze-b2)
  - [Database (Supabase/PostgreSQL)](#database-supabasepostgresql)
  - [Metadata Management (Google Sheets)](#metadata-management-google-sheets)
  - [Document Processing Pipeline](#document-processing-pipeline)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
- [Usage](#usage)
  - [Uploading Documents](#uploading-documents)
  - [Managing Metadata](#managing-metadata)
  - [Searching Documents](#searching-documents)
  - [Collaborative Tagging](#collaborative-tagging)
- [Development Roadmap](#development-roadmap)
- [Contributing](#contributing)
- [License](#license)

## Overview

The energy sector faces complex challenges in regulatory transitions, climate risk management, and affordability constraints, all amidst slow feedback loops and rapidly evolving technologies. Project CAIRN addresses these challenges through:

1. **AI-Driven Document Aggregation & Retrieval** - Automated ingestion of regulatory materials with contextual summaries using Large Language Models (LLMs)
2. **Scenario-Building & Agentic Feedback Loops** - Modeling hypothetical policy changes with iterative analysis
3. **Open, Modular Architecture** - Supporting community contributions and plug-and-play tools

This system empowers environmental advocates, utility planners, and regulatory analysts to quickly access, understand, and act on regulatory information that would otherwise require days of manual review.

## System Architecture

CAIRN follows a modular architecture with several integrated components:

```
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│                   │     │                   │     │                   │
│   Document        │     │   Supabase        │     │   Metadata        │
│   Storage         │────▶│   PostgreSQL      │◀───▶│   Management      │
│   (Backblaze B2)  │     │   Database        │     │   (Google Sheets) │
│                   │     │                   │     │                   │
└───────────────────┘     └─────────┬─────────┘     └───────────────────┘
                                    │
                                    ▼
                          ┌───────────────────┐
                          │                   │
                          │   Document        │
                          │   Processing      │
                          │   Pipeline        │
                          │                   │
                          └─────────┬─────────┘
                                    │
                                    ▼
                          ┌───────────────────┐
                          │                   │
                          │   RAG-Enhanced    │
                          │   LLM Analysis    │
                          │   & Interactions  │
                          │                   │
                          └───────────────────┘
```

## Core Components

### Document Storage (Backblaze B2)

CAIRN uses Backblaze B2 Cloud Storage for storing the original PDF documents. This provides:

- Cost-effective object storage
- Durability and reliability
- Secure access to documents
- Scalability for growing document collections

The `B2Uploader` class handles the interaction with Backblaze B2, providing methods to:
- Upload individual files or entire directories
- Check if files already exist to avoid duplication
- Manage metadata for uploaded files

### Database (Supabase/PostgreSQL)

CAIRN leverages Supabase, a powerful open-source Firebase alternative built on PostgreSQL, to provide:

- Fully managed PostgreSQL database
- Real-time data synchronization
- Authentication and authorization
- REST and GraphQL APIs for easy integration
- Row-level security for fine-grained access control
- Collaborative features across multiple users

The database schema includes:

- `utilities` - Information about utility companies
- `regulatory_bodies` - Regulatory agencies and commissions
- `dockets` - Regulatory proceedings and cases
- `document_types` - Categories of documents (e.g., IRPs, Rate Cases)
- `documents` - Core document metadata with links to B2 storage
- `tags` - Flexible categorization system
- `document_tags` - Many-to-many relationship between documents and tags
- `document_content` - Extracted text content with full-text search capabilities
- `document_summaries` - LLM-generated summaries
- `external_metadata_syncs` - Tracking for external metadata synchronization

Supabase's real-time capabilities enable collaborative tagging and metadata management, allowing multiple users to work simultaneously on document classification and organization. Changes made by one user are instantly visible to others, creating a seamless collaborative experience.

### Metadata Management (Google Sheets)

To make metadata management accessible to non-technical users, CAIRN integrates with Google Sheets. This provides:

- A familiar interface for viewing and editing document metadata
- Collaborative tagging and categorization
- Bi-directional synchronization with the Supabase PostgreSQL database

The system uses four sheets:
1. **Documents** - Main sheet for document metadata and tagging
2. **Utilities** - Reference data for utility companies
3. **Document Types** - Categories of regulatory documents
4. **Tags** - Available tags for document classification

The `SheetsMetadataManager` class handles:
- Initializing sheets with proper headers
- Syncing reference data from the database
- Transferring document metadata to sheets
- Updating the database with changes made in sheets

### Document Processing Pipeline

The document processing pipeline handles:
- PDF upload to Backblaze B2
- Metadata extraction and storage in Supabase
- Text extraction from PDFs
- Full-text indexing for search

Future enhancements will include:
- Automatic document classification
- Entity recognition for key stakeholders, dates, and monetary values
- LLM-based summarization and analysis

## Getting Started

### Prerequisites

- Python 3.8+
- Supabase account
- Google Cloud account (for Sheets API)
- Backblaze B2 account

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/cairn.git
   cd cairn
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up Supabase:
   - Create a new Supabase project
   - Use the SQL scripts in the `schema/` directory to create the required tables
   - Configure authentication as needed for your users

4. Configure API credentials (see Configuration section)

### Configuration

Create a `config.ini` file with the following structure:

```ini
[supabase]
url = https://your-project-ref.supabase.co
key = your_supabase_api_key
service_role_key = your_service_role_key

[backblaze]
key_id = your_b2_key_id
application_key = your_b2_application_key
bucket_name = your_bucket_name

[googlesheets]
credentials_path = path/to/credentials.json
spreadsheet_id = your_spreadsheet_id
```

## Usage

### Uploading Documents

```python
from cairn.storage import B2Uploader
from cairn.database import SupabaseClient
from cairn.utils import upload_to_b2_and_database

# Initialize components
db = SupabaseClient(
    supabase_url='https://your-project-ref.supabase.co',
    supabase_key='your_supabase_api_key'
)

uploader = B2Uploader(
    key_id='your_key_id',
    application_key='your_application_key',
    bucket_name='your_bucket_name'
)

# Upload a single file
document_id = upload_to_b2_and_database(
    file_path='path/to/document.pdf',
    db=db,
    uploader=uploader,
    title='Sample Utility IRP',
    description='Integrated Resource Plan for Sample Utility',
    utility_id=1,
    document_type_id=3,
    filing_date='2024-03-15'
)

print(f"Document uploaded with ID: {document_id}")
```

### Managing Metadata

```python
from cairn.metadata import SheetsMetadataManager

# Initialize the sheets manager
sheets_manager = SheetsMetadataManager(
    credentials_path='path/to/credentials.json',
    spreadsheet_id='your_spreadsheet_id',
    db=db
)

# Initialize sheets with headers and reference data
sheets_manager.initialize_sheets()

# Sync documents from database to sheets
sheets_manager.sync_documents_to_sheets()

# After users have updated metadata in sheets, sync back to database
sheets_manager.sync_metadata_from_sheets()
```

### Searching Documents

```python
# Search documents using full-text search
results = db.search_documents("renewable energy storage")

# Print results
for doc in results:
    print(f"Document: {doc['title']}")
    print(f"Utility: {doc['utility_name']}")
    print(f"Relevant text: {doc['text_snippet']}")
    print("-" * 50)
```

### Collaborative Tagging

One of CAIRN's powerful features is collaborative tagging through Supabase's real-time capabilities:

```python
# Subscribe to changes in document tags
subscription = db.subscribe_to_table(
    table="document_tags",
    event="*",  # Listen for all events (INSERT, UPDATE, DELETE)
    callback=handle_tag_changes
)

# Define a callback to handle tag changes
def handle_tag_changes(payload):
    print(f"Tag change detected: {payload['eventType']}")
    print(f"Document ID: {payload['new']['document_id']}")
    print(f"Tag ID: {payload['new']['tag_id']}")
    
    # Update UI or perform other actions based on the change
    if payload['eventType'] == 'INSERT':
        update_document_tags_in_ui(payload['new']['document_id'])
```

Multiple users can tag documents simultaneously, with changes reflected in real-time across all connected clients.

## Development Roadmap

### Phase 1 (Q1–Q2 2025): Data Gathering & MVP Prototype

- [x] Define database schema
- [x] Implement B2 storage integration
- [x] Set up Supabase for collaborative database access
- [x] Create metadata management system
- [ ] Develop basic document processing pipeline
- [ ] Build MVP dashboard

### Phase 2 (Q2–Q3 2025): Advanced LLM-Based Interactions

- [ ] Implement Retrieval-Augmented Generation (RAG) architecture
  - [ ] Create vector embeddings for document content
  - [ ] Develop semantic search capabilities using embeddings
  - [ ] Build context retrieval systems for LLM prompting
  - [ ] Design prompt templates with domain-specific knowledge
- [ ] Integrate advanced LLM models (e.g., OpenAI GPT-4, Claude, or open-source alternatives)
- [ ] Implement source traceability and citation tracking
- [ ] Create visualization components for document relationships
- [ ] Develop notification system for docket updates

### Phase 3 (Q3–Q4 2025): Agentic Stakeholder Simulations

- [ ] Design multi-agent simulation engine
- [ ] Implement collaborative features
- [ ] Build scenario-modeling tools
- [ ] Create public access and documentation

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

