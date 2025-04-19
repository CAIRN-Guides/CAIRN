/*──────────────────────────────────────────────────────────────────────────────
  CAIRN · Minimal Schema for Google‑Sheet → Supabase Tag Sync
  -----------------------------------------------------------------------------
  HOW TO USE:
    1. Log in to https://app.supabase.io   ▸  open your project
    2. Go to  “SQL Editor”  ▸  “+ New query”
    3. Paste this entire script and click  RUN
    4. You should see 3 “Success” messages (one per CREATE TABLE)

  NOTES:
    • All tables live in the default “public” schema
    • You can enable Row‑Level‑Security later—keep it OFF while prototyping
    • If you add columns to the sync script, ALTER TABLE here to match
──────────────────────────────────────────────────────────────────────────────*/

-- ────────────────────────────────────────────────────────────────────────────
-- 1. FILES  (one row per document)
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS files (
  id               BIGSERIAL PRIMARY KEY,              -- internal PK
  created_at       TIMESTAMPTZ DEFAULT NOW(),          -- auto timestamp
  document_id      TEXT UNIQUE NOT NULL,               -- stable sheet ID (e.g. C250001)
  local_backup_name TEXT,                              -- original filename or B2 key
  published_date   DATE,                               -- from Google Sheet
  date_tagged      DATE,                               -- when tagger finished work
  last_synced_at   TIMESTAMPTZ                         -- updated every script run
);

-- Optional: speed up lookups by document_id
CREATE INDEX IF NOT EXISTS idx_files_document_id ON files(document_id);

COMMENT ON TABLE  files                IS 'Master list of documents ingested from the Google tagging sheet.';
COMMENT ON COLUMN files.document_id    IS 'Unique identifier from the sheet (CYY###).';
COMMENT ON COLUMN files.local_backup_name IS 'Filename or storage key of the local/B2 copy.';
COMMENT ON COLUMN files.published_date IS 'Publication date parsed from the sheet.';
COMMENT ON COLUMN files.date_tagged    IS 'Date the tagging task was completed.';
COMMENT ON COLUMN files.last_synced_at IS 'Timestamp of the most recent sync run.';

-- ────────────────────────────────────────────────────────────────────────────
-- 2. TAGS  (one row per distinct tag string)
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tags (
  id         BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  tag_name   TEXT UNIQUE NOT NULL           -- e.g. Solar, RateImpact_Y, UTC
);

CREATE INDEX IF NOT EXISTS idx_tags_tag_name ON tags(tag_name);

COMMENT ON TABLE  tags              IS 'Dictionary of unique tag values.';
COMMENT ON COLUMN tags.tag_name      IS 'Exact tag string, case‑sensitive.';

-- ────────────────────────────────────────────────────────────────────────────
-- 3. FILE_TAGS  (junction: many‑to‑many files ↔ tags)
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS file_tags (
  file_id BIGINT REFERENCES files(id) ON DELETE CASCADE,
  tag_id  BIGINT REFERENCES tags(id)  ON DELETE CASCADE,
  PRIMARY KEY (file_id, tag_id)           -- prevents duplicate links
);

COMMENT ON TABLE  file_tags          IS 'Link table joining documents to their tags.';
COMMENT ON COLUMN file_tags.file_id   IS 'FK → files.id';
COMMENT ON COLUMN file_tags.tag_id    IS 'FK → tags.id';

-- ────────────────────────────────────────────────────────────────────────────
-- End of schema
-- ────────────────────────────────────────────────────────────────────────────
