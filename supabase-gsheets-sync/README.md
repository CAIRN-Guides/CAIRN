## CAIRN Full Sync  
*A  script that keeps Google Sheets, Supabase, and Backblaze B2 in sync*  

---

### What the script does — at a glance

| Phase | Action | Where |
|-------|--------|-------|
| **1. Sheet → Supabase** | • Pulls the **Document Tags** worksheet from your Google Sheet<br>• Cleans & normalises every column (dates, enums, booleans, arrays)<br>• Upserts one row per document into **`files`** and links tags through **`tags` / `file_tags`** | Google Sheets → Supabase Postgres |
| **2. Supabase → Backblaze B2** | • Looks for rows whose `b2_file_id` is empty or recently updated<br>• Finds the matching PDF in `LOCAL_BACKUPS_DIR` (file name == *File ID*)<br>• Uploads to B2 *only if the object isn’t already there*<br>• Stores `b2_file_id` and a fresh presigned download URL in `files` | Filesystem → B2 → Supabase |

---

## Folder structure (recommended)

```
project-root/
├─ cairn_full_sync.py          # <- the script
├─ requirements.txt            # see below
├─ .env                        # your secrets (never commit!)
└─ docs/
   └─ supabase_ddl.sql         # table & enum creation script
```

---

## Requirements

| Tool | Version notes |
|------|---------------|
| Python ≥ 3.10 | `pip install -r requirements.txt` |
| Google service-account JSON | Path set in `GOOGLE_CREDS_FILE` |
| Supabase project | URL + **service-role** key |
| Backblaze B2 bucket | Application key & key-ID |

### `requirements.txt`

```text
b2sdk
google-auth
gspread
python-dotenv
pandas
supabase-py
```

---

## Environment variables (`.env`)

```ini
# ─── Supabase ───
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...

# ─── Google Sheets & Drive ───
GSHEET_NAME=CAIRN_Labels_Gsheets_Input
GSHEET_WORKSHEET=Document_Tags
GOOGLE_CREDS_FILE=./cairn_google_creds.json

# ─── Local PDF folder ───
LOCAL_BACKUPS_DIR=C:\path\to\pdfs

# ─── Backblaze B2 ───
B2_APP_KEY_ID=...
B2_APP_KEY=...
B2_BUCKET=cairn-docs

# (optional) behaviour tweaks
B2_URL_TTL=604800         # presigned-URL lifetime (seconds)
SYNC_WINDOW_DAYS=30       # only re-upload rows touched N days
LOAD_CHUNK=100            # Supabase page size
```

---

## Quick-start guide

1. **Clone or copy the repo**

   ```bash
   git clone <your-repo>
   cd project-root
   ```

2. **Install dependencies**

   ```bash
   python -m venv .venv && source .venv/bin/activate   # PowerShell: .venv\Scripts\Activate
   pip install -r requirements.txt
   ```

3. **Create `.env`**  
   Paste the template above and fill in your own keys & paths.

4. **Create tables (first run only)**  

   In Supabase → SQL editor, run `docs/supabase_ddl.sql`  
   (or the DO block supplied earlier).

5. **Populate `LOCAL_BACKUPS_DIR`**  
   Put every PDF in that folder; file name **must equal the File ID**  
   from your Sheet (case-insensitive `.pdf` extension is OK).

6. **Run the sync**

   ```bash
   python cairn_full_sync.py
   ```

   You’ll see log lines like:

   ```
   INFO Rows to process: 68
   INFO Uploading C250001_PSE_RATECASE_2025 …
   INFO Synced: 42, Skipped: 24, Errors: 2
   ```

7. **Verify**

   * Supabase → `files` table now has `b2_file_id` & `b2_temp_url`.
   * Backblaze console shows the newly-uploaded PDFs.

---

## Common troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `source_file_id missing` skip | “File ID” blank in Sheet | Fill it in & re-run |
| `local file … not found` skip | PDF not in folder or wrong name | Ensure `FileID.pdf` lives in `LOCAL_BACKUPS_DIR` |
| `already has b2_file_id` skip but file isn’t really on B2 | Placeholder value in Sheet | Clear `b2_file_id` (SQL) or change placeholder string |

