# Washington UTC Docket Downloader

A small helper library + notebook demo for grabbing every public PDF in a
Washington Utilities & Transportation Commission (UTC) docket, even when the
case spans multiple years.

## Washington UTC Docket Downloader – User Guide

### 1  What’s a “docket”?

A **docket** is the UTC’s formal case record. Whenever a utility proposes a tariff change, rate case, acquisition, integrated resource plan, etc., the Commission opens a docket (e.g., **“UE‑220066”**).  
* Every filing—petitions, data responses, public comments, orders—is stamped with a **docket number** and stored as a PDF (or Excel) in the public record.  
* UTC’s website splits those filings by **calendar year**:  
  `…/casedocket/<YEAR>/<DOCKET>/docsets`.

### 2  What does the downloader do?

The script in **`utc_downloader_nb.py`** automates three chores:

1. **Discover** every “docsets” page for a docket from the **opening year to today**.  
2. **Parse** each page’s HTML and collect the hidden download links (`https://apiproxy.utc.wa.gov/cases/GetDocument?docID=…`).  
3. **Download** every unique file to a local folder, waiting a short time between requests so we don’t overload the UTC server.

### 3  How the code is organised

| Component | Location | Role |
|-----------|----------|------|
| `list_document_links()` | `utc_downloader_nb.py` | Returns `{docID: (url, filename)}` for all years. |
| `download_documents()` | same file | Streams each URL to disk; skips existing files. |
| `fetch_docket()` | same file | Convenience wrapper that calls the two functions above. |
| Notebook demo | `notebook_demo.ipynb` | Hands‑on example you can run cell‑by‑cell. |

All functions use only **`requests`** and **`beautifulsoup4`**—no external APIs or credentials.

### 4  Quick start (command palette)

```bash
# 0) clone + install deps
git clone https://github.com/<your‑org>/utc-downloader.git
cd utc-downloader
pip install -r requirements.txt

# 1) start Jupyter
jupyter lab  # or jupyter notebook

# 2) in a new notebook cell
from utc_downloader_nb import fetch_docket
fetch_docket("220066", start_year=2022)   # downloads to ./utc_220066/
```

### 5  Typical notebook workflow

```python
from utc_downloader_nb import list_document_links, download_documents
links = list_document_links("250108", start_year=2025)  # discover
download_documents(links, outdir="~/Downloads/utc_250108", delay=1.0)  # fetch
```

### 6  Choosing parameters

| Parameter | Meaning | Example |
|-----------|---------|---------|
| `docket`  | Digits only, no “UE‑” prefix | `"220066"` |
| `start_year` | Year the docket opened | `2022` |
| `end_year` | (optional) stop year; defaults to current year | `2024` |
| `outdir` | Local save folder; defaults to `./utc_<docket>` | `"./data/ue_220066"` |
| `delay`  | Seconds between downloads (≥ 0.5 recommended) | `0.75` |

### 7  Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `No filings for docket … in YEAR` | That year’s folder hasn’t been created yet. | Ignore—the script continues. |
| `404 Client Error` when downloading | Document has been sealed/confidential. | The script skips after logging the error. |
| Very slow / connection reset | UTC server throttling. | Increase `delay` to 1 – 2 s. |
