# CAIRN Tags Sync: BackBlaze <-> Supabase <-> Googlesheets 

A **one‑command bridge** between a Google Sheet that holds CAIRN document tags and a
three‑table Supabase schema (`files`, `tags`, `file_tags`).  

---

##  Quick Start Guide

```bash
# 1 – Clone & install
git clone https://github.com/<your‑org>/cairn‑sheet‑sync.git
cd cairn‑sheet‑sync
python -m pip install -r requirements.txt   # or `pipx run pipenv install`

# 2 – Add secrets
cp .env.example .env       # then open .env and fill in the values

# 3 – Run the sync
python sheet_to_supabase.py

⚙️ Configuration Steps

    Supabase tables – copy‑paste supabase_schema.sql into the SQL Editor and run.

    Google API creds – create a service account, enable Drive + Sheets APIs,
    download the JSON key, and share your Google Sheet with the account’s e‑mail.

    Environment variables – edit .env (see template below).
