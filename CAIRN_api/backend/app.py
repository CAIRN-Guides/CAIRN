# b2 debugging build 5.8.25
import os
import httpx # HTTP client for making API requests
import asyncio # For asynchronous operations and locks
import time # For token expiry management
import logging # For logging application events
from typing import Optional, Dict, Any, List, AsyncGenerator
import io # For in-memory file operations (e.g., zipping)
import zipfile # For creating ZIP archives

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel # For request body validation

from supabase import create_client, Client # Supabase Python client

# --- Configuration & Globals ---

# Configure logging (adjust as per your existing setup)
# logging.basicConfig(level=logging.INFO) # Basic config if not already set
logger = logging.getLogger("app") # Assuming your logger is named "app"

# Load B2 credentials from environment variables (matching Render variable names)
B2_APPLICATION_KEY_ID = os.getenv("B2_APP_KEY_ID") # Updated from B2_APPLICATION_KEY_ID
B2_APPLICATION_KEY = os.getenv("B2_APP_KEY")       # Updated from B2_APPLICATION_KEY
B2_API_AUTHORIZE_URL = "https://api.backblazeb2.com/b2api/v2/b2_authorize_account"

# Load Supabase credentials from environment variables (matching Render variable names)
SUPABASE_URL = os.getenv("SUPABASE_URL")
# Using SUPABASE_SERVICE_ROLE_KEY for backend operations
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") 

# Initialize Supabase client
# Ensure SUPABASE_URL and SUPABASE_KEY (SUPABASE_SERVICE_ROLE_KEY from env) are set
supabase_client: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized successfully using SERVICE_ROLE_KEY.")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}", exc_info=True)
        supabase_client = None # Ensure it's None if initialization fails
else:
    logger.warning("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables not set. Supabase functionality will be impaired.")

# Dependency to get Supabase client
async def get_supabase_client() -> Client:
    if supabase_client is None:
        logger.error("Supabase client is not available. Check configuration and environment variables (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).")
        raise HTTPException(status_code=503, detail="Database service is not configured or unavailable.")
    return supabase_client

# --- Backblaze B2 Management ---

class B2AuthData:
    """
    Holds Backblaze B2 authorization details and manages token validity.
    """
    def __init__(self, data: Dict[str, Any]):
        self.account_id: str = data["accountId"]
        self.api_url: str = data["apiUrl"] 
        self.authorization_token: str = data["authorizationToken"]
        self.download_url: str = data["downloadUrl"] 
        self.token_obtained_at: float = time.time()
        self.token_validity_duration: float = 23 * 60 * 60  # 23 hours in seconds

    def is_token_expired(self) -> bool:
        """Checks if the current authorization token has expired."""
        return (time.time() - self.token_obtained_at) > self.token_validity_duration

class B2Manager:
    """
    Manages Backblaze B2 authorization and file download operations.
    """
    _auth_data: Optional[B2AuthData] = None
    _lock = asyncio.Lock()

    @classmethod
    async def _authorize(cls) -> None:
        # Uses B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY which are now mapped to B2_APP_KEY_ID and B2_APP_KEY from env
        if not B2_APPLICATION_KEY_ID or not B2_APPLICATION_KEY:
            logger.error("B2_APP_KEY_ID or B2_APP_KEY is not configured in environment variables.")
            raise HTTPException(status_code=503, detail="B2 service is not configured by the administrator.")

        logger.info("Attempting to authorize with Backblaze B2...")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    B2_API_AUTHORIZE_URL,
                    auth=(B2_APPLICATION_KEY_ID, B2_APPLICATION_KEY) # These now correctly point to B2_APP_KEY_ID and B2_APP_KEY
                )
                response.raise_for_status()
                auth_response_data = response.json()
                cls._auth_data = B2AuthData(auth_response_data)
                logger.info(f"Successfully authorized with B2. Download URL base: {cls._auth_data.download_url}")
            except httpx.HTTPStatusError as e:
                logger.error(f"B2 authorization failed: HTTP {e.response.status_code} - {e.response.text}")
                cls._auth_data = None
                raise HTTPException(status_code=503, detail=f"Failed to authorize with B2 service: {e.response.status_code}")
            except Exception as e:
                logger.error(f"B2 authorization failed with an unexpected error: {str(e)}", exc_info=True)
                cls._auth_data = None
                raise HTTPException(status_code=503, detail="Unexpected error during B2 authorization.")

    @classmethod
    async def get_auth_data(cls, force_refresh: bool = False) -> B2AuthData:
        async with cls._lock:
            if force_refresh or not cls._auth_data or cls._auth_data.is_token_expired():
                logger.info(f"B2 token needs refresh (force_refresh={force_refresh}, has_auth={cls._auth_data is not None}, expired={cls._auth_data.is_token_expired() if cls._auth_data else 'N/A'}).")
                await cls._authorize()
            if not cls._auth_data:
                logger.error("B2 authorization data is unavailable after authorization attempt.")
                raise HTTPException(status_code=503, detail="B2 authorization data unavailable.")
            return cls._auth_data

    @classmethod
    async def get_download_headers(cls, force_refresh: bool = False) -> Dict[str, str]:
        auth_data = await cls.get_auth_data(force_refresh=force_refresh)
        return {"Authorization": auth_data.authorization_token}

    @classmethod
    async def get_b2_download_url_base(cls, force_refresh: bool = False) -> str:
        auth_data = await cls.get_auth_data(force_refresh=force_refresh)
        return auth_data.download_url

    @classmethod
    async def download_file_stream(cls, b2_file_id: str, client: httpx.AsyncClient) -> httpx.Response:
        if not b2_file_id:
            raise ValueError("b2_file_id cannot be empty for download.")
        try:
            download_url_base = await cls.get_b2_download_url_base()
            headers = await cls.get_download_headers()
            file_download_url = f"{download_url_base}/b2api/v1/b2_download_file_by_id?fileId={b2_file_id}"
            logger.info(f"Attempting B2 download for file ID: {b2_file_id}")
            response = await client.get(file_download_url, headers=headers, timeout=60.0)
            if response.status_code == 401:
                logger.warning(f"B2 download for {b2_file_id} received 401. Re-authorizing and retrying...")
                headers = await cls.get_download_headers(force_refresh=True)
                response = await client.get(file_download_url, headers=headers, timeout=60.0)
            response.raise_for_status()
            logger.info(f"B2 download successful for file ID: {b2_file_id}, status: {response.status_code}")
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"B2 download HTTPError for ID {b2_file_id}. Status: {e.response.status_code}, Response: {e.response.text[:200]}...")
            status_code_to_raise = 503 if e.response.status_code == 401 else e.response.status_code
            raise HTTPException(
                status_code=status_code_to_raise,
                detail=f"B2 download service error for file ID {b2_file_id}."
            )
        except Exception as e:
            logger.error(f"Unexpected error during B2 file download for ID {b2_file_id}: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Unexpected error during B2 file download of {b2_file_id}.")

# --- FastAPI Application Setup ---

app = FastAPI(
    title="CAIRN API",
    description="API for accessing CAIRN documents and metadata.",
)

@app.on_event("startup")
async def startup_event():
    """Handles application startup events, like initial B2 authorization."""
    if B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY: # Checks B2_APP_KEY_ID and B2_APP_KEY
        try:
            await B2Manager.get_auth_data(force_refresh=True)
            logger.info("B2 authorization successful on application startup.")
        except HTTPException as e:
            logger.error(f"B2 authorization failed on startup (HTTPException {e.status_code}): {e.detail}. B2 dependent features may fail.")
        except Exception as e:
            logger.error(f"B2 authorization failed on startup with an unexpected error: {str(e)}", exc_info=True)
    else:
        logger.warning("B2 credentials (B2_APP_KEY_ID, B2_APP_KEY) are not set. B2 functionality will be impaired.")
    
    if supabase_client is None: # Check if Supabase client (using SUPABASE_SERVICE_ROLE_KEY) was initialized
         logger.warning("Supabase client could not be initialized on startup. Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.")


# --- Pydantic Models for Request/Response ---

class DocumentIdentifier(BaseModel):
    id: int 
    b2_file_id: Optional[str] = None
    document_title: Optional[str] = "untitled_document.pdf" 

class BatchDownloadRequest(BaseModel):
    document_ids: List[int] 

class DownloadURLResponse(BaseModel):
    url: str
    filename: str

# --- Supabase Data Access Functions ---

async def fetch_document_metadata_from_supabase(document_pk: int, db: Client = Depends(get_supabase_client)) -> Optional[Dict[str, Any]]:
    """Fetches document metadata from Supabase by its primary key (id)."""
    try:
        logger.info(f"Querying Supabase for document PK: {document_pk}")
        response = await db.table("files").select("id, b2_file_id, document_title").eq("id", document_pk).maybe_single().execute()
        if response.data:
            logger.debug(f"Supabase response for PK {document_pk}: {response.data}")
            return response.data
        else:
            logger.warning(f"Document PK {document_pk} not found in Supabase.")
            return None
    except Exception as e:
        logger.error(f"Error fetching document PK {document_pk} from Supabase: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Database error while fetching document {document_pk}.")


async def fetch_batch_document_metadata_from_supabase(document_pks: List[int], db: Client = Depends(get_supabase_client)) -> List[Dict[str, Any]]:
    """Fetches metadata for multiple documents from Supabase by their primary keys (id)."""
    if not document_pks:
        return []
    try:
        logger.info(f"Querying Supabase for batch document PKs: {document_pks}")
        response = await db.table("files").select("id, b2_file_id, document_title").in_("id", document_pks).execute()
        if response.data:
            logger.debug(f"Supabase response for batch PKs {document_pks}: {response.data}")
            return response.data
        else:
            logger.warning(f"No documents found in Supabase for batch PKs: {document_pks}")
            return []
    except Exception as e:
        logger.error(f"Error fetching batch documents {document_pks} from Supabase: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Database error while fetching batch documents.")


# --- API Endpoints ---

@app.get("/documents/{document_pk}/download-url", response_model=DownloadURLResponse)
async def get_single_download_url(document_pk: int, request: Request, db: Client = Depends(get_supabase_client)):
    logger.info(f"Requesting single download URL for document PK: {document_pk}") 
    file_info = await fetch_document_metadata_from_supabase(document_pk, db) 
    if not file_info:
        raise HTTPException(status_code=404, detail="Document not found.") 
    b2_file_id = file_info.get("b2_file_id")
    document_title = file_info.get("document_title") or f"document_{document_pk}.pdf" 
    if not b2_file_id:
        logger.warning(f"Document PK {document_pk} (Title: {document_title}) found but has no associated B2 file ID.")
        raise HTTPException(status_code=404, detail="No downloadable file associated with this document.")
    try:
        proxy_url_path = request.url_for('b2_proxy_stream_endpoint', b2_file_id=b2_file_id, filename=document_title)
    except Exception as e: 
        logger.error(f"Error generating URL for proxy: {str(e)}", exc_info=True) 
        raise HTTPException(status_code=500, detail="Error generating download link.")
    logger.info(f"Generated proxy URL path for PK {document_pk} (B2 ID: {b2_file_id}): {proxy_url_path}")
    return DownloadURLResponse(url=str(proxy_url_path), filename=document_title)


@app.get("/api/b2-proxy/{b2_file_id}/{filename}")
async def b2_proxy_stream_endpoint(request: Request, b2_file_id: str, filename: str):
    logger.info(f"Proxy: Request for B2 File ID: {b2_file_id}, Filename: {filename}")
    if not (B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY): # Checks B2_APP_KEY_ID and B2_APP_KEY
        logger.error("B2 proxy request failed: B2 service not configured on server.")
        raise HTTPException(status_code=503, detail="File download service is not configured.")
    async with httpx.AsyncClient() as client:
        try:
            b2_response = await B2Manager.download_file_stream(b2_file_id, client)
            response_headers = {
                "Content-Type": b2_response.headers.get("Content-Type", "application/octet-stream"),
                "Content-Disposition": f'attachment; filename="{filename}"' 
            }
            if 'Content-Length' in b2_response.headers:
                response_headers["Content-Length"] = b2_response.headers['Content-Length']
            async def content_streamer() -> AsyncGenerator[bytes, None]:
                async for chunk in b2_response.aiter_bytes():
                    yield chunk
                await b2_response.aclose() 
            return StreamingResponse(content_streamer(), headers=response_headers)
        except HTTPException as e:
            logger.error(f"Proxy: HTTPException during B2 download for ID {b2_file_id}. Status: {e.status_code}, Detail: {e.detail}")
            raise e 
        except Exception as e:
            logger.error(f"Proxy: Unexpected error during B2 download for ID {b2_file_id}. Error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Unexpected error while proxying B2 download.")


@app.post("/documents/batch-download-url", response_model=DownloadURLResponse)
async def get_batch_download_url(request_payload: BatchDownloadRequest, fastapi_request_context: Request):
    document_pks = request_payload.document_ids
    logger.info(f"Requesting batch download URL for {len(document_pks)} document PKs: {document_pks}")
    if not document_pks:
        raise HTTPException(status_code=400, detail="No document IDs provided for batch download.")
    pks_param = ",".join(map(str, document_pks))
    try:
        zip_serve_url_path = fastapi_request_context.url_for('serve_batch_zip_endpoint', pks_query_param=pks_param)
        zip_filename = f"cairn_batch_{int(time.time())}.zip"
        logger.info(f"Generated URL for batch ZIP: {zip_serve_url_path}")
        return DownloadURLResponse(url=str(zip_serve_url_path), filename=zip_filename)
    except Exception as e:
        logger.error(f"Batch: Unexpected error generating batch download URL. Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error generating batch download URL.")


@app.get("/api/serve-batch-zip") 
async def serve_batch_zip_endpoint(pks_query_param: str, db: Client = Depends(get_supabase_client)):
    try:
        document_pks = [int(pk_str) for pk_str in pks_query_param.split(',') if pk_str.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document PKs format in query parameter.")
    if not document_pks:
        raise HTTPException(status_code=400, detail="No document PKs provided for zipping.")
    logger.info(f"Serving batch ZIP for PKs: {document_pks}")
    all_file_metadata = await fetch_batch_document_metadata_from_supabase(document_pks, db)
    valid_files_to_zip: List[DocumentIdentifier] = []
    pks_requested = set(document_pks)
    pks_found_with_b2id = set()
    for meta in all_file_metadata:
        pk = meta.get("id")
        b2_id = meta.get("b2_file_id")
        title = meta.get("document_title") or f"file_{pk}.pdf" 
        if b2_id:
            valid_files_to_zip.append(DocumentIdentifier(id=pk, b2_file_id=b2_id, document_title=title))
            pks_found_with_b2id.add(pk)
        else:
            logger.warning(f"Batch ZIP: Document PK {pk} (Title: {title}) has no B2 file ID. Skipping.")
    pks_missing_or_no_b2id = pks_requested - pks_found_with_b2id
    if pks_missing_or_no_b2id:
         logger.warning(f"Batch ZIP: PKs requested but not found with B2 ID (or not in DB): {pks_missing_or_no_b2id}")
    if not valid_files_to_zip:
        logger.error("Batch ZIP: No valid files with B2 IDs found for zipping from the requested PKs.")
        raise HTTPException(status_code=404, detail="No downloadable files found for the selected documents.")
    zip_filename = f"cairn_documents_{int(time.time())}.zip"
    response_headers = {
        "Content-Disposition": f'attachment; filename="{zip_filename}"',
        "Content-Type": "application/zip"
    }
    async def zip_content_streamer() -> AsyncGenerator[bytes, None]:
        zip_buffer = io.BytesIO()
        files_added_to_zip = 0
        async with httpx.AsyncClient() as client:
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for doc_to_zip in valid_files_to_zip:
                    try:
                        logger.info(f"Batch ZIP: Fetching B2 file ID {doc_to_zip.b2_file_id} for PK {doc_to_zip.id}")
                        b2_response = await B2Manager.download_file_stream(doc_to_zip.b2_file_id, client)
                        file_content = await b2_response.aread() 
                        await b2_response.aclose()
                        entry_filename = doc_to_zip.document_title 
                        zf.writestr(entry_filename, file_content)
                        files_added_to_zip += 1
                        logger.info(f"Batch ZIP: Added {entry_filename} (B2 ID: {doc_to_zip.b2_file_id}) to ZIP.")
                    except HTTPException as e:
                        logger.error(f"Batch ZIP: Failed to download/add file PK {doc_to_zip.id} (B2 ID: {doc_to_zip.b2_file_id}) to ZIP. Detail: {e.detail}")
                    except Exception as e:
                        logger.error(f"Batch ZIP: Unexpected error processing file PK {doc_to_zip.id} (B2 ID: {doc_to_zip.b2_file_id}). Error: {str(e)}", exc_info=True)
            if files_added_to_zip == 0:
                logger.error("Batch ZIP: All B2 download attempts failed for initially valid files. ZIP will be empty or incomplete.")
            zip_buffer.seek(0)
            chunk_size = 8192 
            while True:
                chunk = zip_buffer.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    return StreamingResponse(zip_content_streamer(), headers=response_headers)

# --- Main execution (for local testing if needed) ---
# if __name__ == "__main__":
#     import uvicorn
#     # Ensure B2_APP_KEY_ID, B2_APP_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY are set
#     if not all([os.getenv("B2_APP_KEY_ID"), os.getenv("B2_APP_KEY"), os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")]):
#         print("ERROR: B2_APP_KEY_ID, B2_APP_KEY, SUPABASE_URL, and SUPABASE_SERVICE_ROLE_KEY environment variables must be set.")
#     else:
#         # Example: uvicorn your_module_name:app --reload
#         uvicorn.run(app, host="0.0.0.0", port=8000)

