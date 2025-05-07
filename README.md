

## 1 Why CAIRN?


 CAIRN turns thousands of PDFs into a living knowledge graph you can search, tag, and interrogate in minutes instead of day to help utilities, advocates, and commissions must make faster climate‑risk decisions. 

* **Collect** – scrape or upload filings from commissions, utilities, and intervenors.  
* **Organise** – normalise metadata, enrich with tags, and store in a relational backbone.  
* **Surface** – run keyword or semantic search, receive instant summaries, and (road‑mapped) chat with a RAG agent that cites its sources.

---

## 2 System Architecture

```
┌──────────────┐   files   ┌──────────────┐   sync   ┌──────────────┐
│  Backblaze   │──────────▶│  Supabase    │◀────────▶│ Google‑Sheets│
│     B2       │           │ PostgreSQL   │          │  Metadata    │
└──────────────┘           └────┬─────────┘          └──────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │ Processing & RAG │
                        └──────────────────┘
```

* **Storage** – low‑cost, S3‑compatible Backblaze B2 for original files.  
* **Database** – Supabase/PostgreSQL for structured metadata, full‑text, and embeddings.  
* **Sheets** – a no‑code UI for mass‑editing metadata.  
* **Pipeline** – ingestion, OCR, chunking, embedding, summarisation.

---

## 3 Core Components & Key Capabilities  

### 3.1 Document Storage – Backblaze B2  
| Capability | Why it matters |
|------------|----------------|
| **Low‑cost object storage** | Docket archives grow fast; keep costs \< \$0.005/GB‑month. |
| **11 × 9s durability + encryption** | Guarantees public records remain intact and private. |
| **Versioning & lifecycle rules** | Recover accidental overwrites, tier off stale drafts. |
| **S3‑compatible API** | Works with standard ETL tooling and multi‑cloud fallbacks. |

`B2Uploader` handles deduplication, checksum validation, resumable uploads, and metadata tagging (utility, docket, year).

---

### 3.2 Relational Backbone – Supabase (PostgreSQL + Realtime)  
* **Row‑level security** for granular access control (e.g. agency‑only drafts).  
* **Realtime change feeds** so tags update across all open dashboards instantly.  
* **REST & GraphQL** auto‑generated for rapid prototyping.  
* **pgvector & tsvector** for hybrid semantic + keyword search.  
* **PostGIS / pg_cron extensions** available when you need them.

**Key tables**

| Table | Purpose |
|-------|---------|
| `utilities` | Master list of companies. |
| `regulatory_bodies` | PUCs, FERC, city councils, etc. |
| `dockets` | Proceeding metadata. |
| `documents` | One row per filing, linked to B2 object. |
| `document_content` | Extracted text + embeddings. |
| `tags`, `document_tags` | Folksonomy for discovery. |
| `document_summaries` | LLM‑generated abstracts. |

---

### 3.3 Human‑Friendly Metadata – Google Sheets  
Bi‑directional sync lets policy analysts bulk‑edit without touching SQL:

* Data‑validation keeps tag vocabularies clean.  
* Conditional formatting flags missing fields.  
* Sheet history provides an audit trail.

`SheetsMetadataManager` initialises the workbook, mirrors reference tables, and resolves row‑level diffs during sync.

---

### 3.4 Document Processing Pipeline  
1. **Ingest** – watch B2 or scrape commission sites, enqueue new files.  
2. **Extract** – parse text (pdfplumber/unstructured); OCR if needed.  
3. **Chunk & normalise** – ~1 k‑token segments with page refs.  
4. **Index** – write to `document_content`, build tsvector + embeddings.  
5. **Enrich** – run LLM summariser and entity extractor.  
6. **Log & monitor** – metrics into Prometheus; job status into Supabase.

Planned upgrades: auto‑classification, advanced NER (statutes, \$ amounts), incremental embedding refresh.

---

## 4 Tagging Workflow & Column Model  

| Column (snake_case) | What it captures |
|---------------------|------------------|
| `document_id` | **Primary key** – `UD‑CYY###` convention. |
| `title` | Full published title. |
| `published_date` | When the doc was released. |
| `author` | Individual or firm that wrote it. |
| `organization` | Utility / NGO / agency associated. |
| `docket_number` | Official proceeding ID (nullable for misc. uploads). |
| `document_type` | Top‑level class – e.g., *IRP, Rate Case Filing, Testimony*. |
| `document_subtype` | Finer grain – e.g., *Load Forecast Chapter*. |
| `source_url` | Original web link. |
| `cairn_url` | Public B2 link or signed URL. |
| `rate_impact` | Does it discuss bill or tariff impacts? *(boolean)* |
| `utility_reform` | Focus on governance / business model change? *(boolean)* |
| `energy_resources` | Comma list: *gas, solar, storage, EE…* |
| `customer_classes` | *residential, C&I, low‑income*, etc. |
| `distributed_energy_resources` | DER focus? *(boolean)* |
| `physical_climate_risk` | Wildfire, heat, flood, etc. *(boolean)* |
| `keywords` | Extra search terms. |
| `tagger` | Person / team that tagged it. |
| `tagged_at` | Timestamp of tagging. |
| `quality_check` | Verified? (*“pending” | “pass” | “fail”*). |
| `processing_notes` | Free‑text anomalies, OCR issues, etc. |
| `state_region` | e.g., *WA, OR, WECC*. |
| `regulatory_body` | *UTC, PUC, FERC*; “National” if none. |
| `jurisdiction_type` | *state, federal, tribal, regional, national*. |

> **Editing tags** – Use drop‑downs or check‑boxes in Sheets; on save, the sync job updates Supabase and triggers realtime downstream listeners.

---

### 5 Getting Started (3‑Step Quick Start)

<Work-in-progress>
---

## 6 Roadmap (2025)

| Phase | Key deliverables |
|-------|------------------|
| **MVP (Q2)** | Schema finalised, B2 uploads, Sheets↔Supabase sync, keyword search. |
| **RAG (Q3)** | pgvector embeddings, semantic search, chat‑with‑citations. |
| **Sim (Q4)** | Multi‑agent scenario engine, public dashboard. |

---

## 7 Contributing

PRs and issues are welcome—open a discussion for major features so we can scope together.

---

## 8 License

MIT. Fork, improve, and share alike.

    Collect – scrape or upload filings from commissions, utilities, and intervenors.

    Organise – normalise metadata, enrich with tags, and store in a relational backbone.

    Surface – run keyword or semantic search, receive instant summaries, and (road‑mapped) chat with a RAG agent that cites its sources.

