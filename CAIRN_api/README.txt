# CAIRN API

## 📂 Repository Structure

```
├── backend/
│   ├── app.py            # FastAPI backend
│   ├── requirements.txt  # Backend dependencies
│   └── .env              # Environment variables for Supabase & B2
├── frontend/
│   ├── streamlit_app.py  # Streamlit UI
│   ├── requirements.txt  # Frontend dependencies
│   └── .env              # Environment variable (API_URL)
└── README.md             # This documentation
```

---

## 🔧 Prerequisites

- Python 3.10+
- PowerShell (Windows) or bash (macOS/Linux)
- Supabase project with `files`, `tags`, `file_tags`, `document_summaries`
- Backblaze B2 bucket & App Key
- (Optional) Google Sheets creds for sync scripts

---

## 🚀 Backend Setup (FastAPI)

1. **Navigate & create venv**
   ```powershell
   cd \path\to\cairn-sync\backend
   & C:/Users/shugs/anaconda3/python.exe -m venv .venv
   . .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Configure `.env`**  
   Create `backend/.env`:
   ```ini
   SUPABASE_URL=your_supabase_url
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
   B2_APP_KEY_ID=your_b2_key_id
   B2_APP_KEY=your_b2_app_key
   B2_BUCKET_NAME=your_bucket_name
   ```

4. **Run the server**
   ```powershell
   uvicorn app:app --reload --port 8000
   ```

5. **Test**  
   Open in browser or `curl`:  
   ```bash
   http://localhost:8000/documents?page=1&page_size=20
   ```

---

## 🎨 Frontend Setup (Streamlit)

1. **Navigate & create venv**
   ```powershell
   cd \path\to\cairn-sync\frontend
   & C:/Users/shugs/anaconda3/python.exe -m venv .venv
   . .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Configure `.env`**  
   Create `frontend/.env`:
   ```ini
   API_URL=http://localhost:8000/documents
   ```

4. **Run Streamlit**
   ```powershell
   streamlit run streamlit_app.py
   ```

5. **Use UI**  
   - Fill filters in the sidebar for any column.
   - Click **Load Documents**.
   - View results dynamically.

---

## ⚙️ API Reference

### `GET /documents`

| Parameter              | Type             | Notes                                     |
|------------------------|------------------|-------------------------------------------|
| `page`                 | `int`            | Page number (default: 1)                  |
| `page_size`            | `int`            | Rows per page (default: 20, max: 200)     |
| `include_download_url` | `bool`           | Attach B2 presigned URL (default: false)  |
| *All other columns*    | `str`, `List[str]`, `bool` | Exact-match filters per Supabase schema |

**Response**:  
```json
{
  "data": [ /* array of objects matching DocumentOut schema */ ],
  "page": 1,
  "page_size": 20
}
```

---

## ❓ Troubleshooting

- `Missing env vars`: Ensure `.env` files are in correct folder and activated.
- `ModuleNotFoundError`: Activate the correct venv before `pip install` and running.
- `ResponseValidationError`: All Pydantic fields are `Optional[...]`—the backend must match the Supabase schema exactly.

---

## 📖 License

MIT © Your Name

