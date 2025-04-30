# CAIRN API

##  Repository Structure

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

## Prerequisites

- Python 3.10+
- PowerShell (Windows) or bash (macOS/Linux)
- Supabase project 
- Backblaze B2 bucket & App Key

---

## CAIRN Backend Setup Guide (FastAPI)

This guide will walk you through setting up the FastAPI backend for CAIRN  on your local machine. This backend handles the interactions between the frontend and the rest of CAIRN. 

### Prerequisites

Before you begin, ensure you have the following installed:

1.  **Python:** Version 3.7 or higher is recommended. You can check your version with `python --version` or `python3 --version`.
2.  **pip:** Python's package installer. Usually comes with Python. You can check with `pip --version` or `pip3 --version`.
3.  **Git:** For cloning the repository.

### Setup Steps

1.  **Clone the Repository:**
    Open your terminal or command prompt and clone the CAIRN project repository (replace `<repository_url>` with the actual URL):
    ```bash
    git clone <repository_url>
    cd cairn # Or your project's root directory name
    ```

2.  **Navigate to the Backend Directory:**
    Change into the backend code directory:
    ```bash
    cd backend # Assuming your backend code is in a 'backend' subfolder
    ```

3.  **Create and Activate a Virtual Environment:**
    It's highly recommended to use a virtual environment to manage project dependencies separately.

    * **Create the environment** (we'll name it `.venv`):
        ```bash
        python -m venv .venv
        ```
        *(Use `python3` if `python` doesn't point to Python 3)*

    * **Activate the environment:**
        * **Windows (Command Prompt):**
            ```cmd
            .\.venv\Scripts\activate
            ```
        * **Windows (PowerShell):**
            ```powershell
            .\.venv\Scripts\Activate.ps1
            ```
            *(If you encounter execution policy issues, you might need to run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` first)*
        * **macOS / Linux (Bash/Zsh):**
            ```bash
            source .venv/bin/activate
            ```
        You'll know the environment is active when you see `(.venv)` prepended to your command prompt line.

4.  **Install Dependencies:**
    With the virtual environment active, install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure Environment Variables:**
    The backend requires connection details and API keys to interact with external services like Supabase (for database) and Backblaze B2 (for file storage). These are stored in an environment file.

    * Create a file named `.env` inside the `backend` directory.
    * Copy and paste the following content into `.env`, replacing the placeholder values with your actual credentials:

        ```dotenv
        # .env file for CAIRN Backend

        # Supabase Credentials (obtain from your Supabase project settings)
        SUPABASE_URL=your_supabase_url
        SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

        # Backblaze B2 Credentials (obtain from your Backblaze B2 account)
        B2_APP_KEY_ID=your_b2_key_id
        B2_APP_KEY=your_b2_app_key
        B2_BUCKET_NAME=your_b2_bucket_name

        # Add any other required environment variables here
        ```

    * **Important:**
        * Obtain the `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from your Supabase project dashboard (Settings -> API).
        * Obtain the `B2_APP_KEY_ID`, `B2_APP_KEY`, and `B2_BUCKET_NAME` from your Backblaze B2 account settings.
        * **Never commit your `.env` file to version control (Git).** Ensure `.env` is listed in your `.gitignore` file.

6.  **Run the Development Server:**
    Now you can start the FastAPI development server using Uvicorn:
    ```bash
    uvicorn app.main:app --reload --port 8000
    ```
    * `app.main:app`: Tells Uvicorn where to find your FastAPI application instance (assuming it's named `app` in `app/main.py` - adjust if your structure differs).
    * `--reload`: Automatically restarts the server when code changes are detected. Useful for development.
    * `--port 8000`: Specifies the port the server will run on.

    If successful, you should see output indicating the server is running, typically listening on `http://127.0.0.1:8000`.

7.  **Test the Setup (Optional but Recommended):**
    You can quickly test if the server is running and responding.

    * **Using a Web Browser:** Open your browser and navigate to `http://127.0.0.1:8000/docs`. FastAPI automatically generates interactive API documentation (Swagger UI) here, which is great for exploring endpoints.
    * **Using `curl` (or similar tool):** Test a specific endpoint mentioned in your original guide (assuming it exists and doesn't require authentication for a basic GET):
        ```bash
        curl "http://localhost:8000/documents?page=1&page_size=20"
        ```
        You should receive a JSON response from your API if the endpoint is working correctly.


-----

## CAIRN Frontend Setup Guide (Streamlit)

This guide details how to set up and run the Streamlit frontend for CAIRN. This frontend provides a web-based user interface to interact with the CAIRN backend API, allowing you to to query CAIRN for documents based on tags. 

### Prerequisites

1.  **Python:** Version 3.7+ recommended (`python --version`).
2.  **pip:** Python package installer (`pip --version`).
3.  **Git:** For cloning the repository.
4.  **Running Backend:** The CAIRN backend service must be running, as the frontend needs to connect to its API. Please follow the [Backend Setup Guide](https://www.google.com/search?q=link-to-your-backend-guide.md) first. By default, the frontend expects the backend to be available at `http://localhost:8000`.

### Setup Steps

1.  **Navigate to the Project Directory:**
    If you cloned the project repository during the backend setup, ensure you are in the main project directory. If not, clone it first:

    ```bash
    # Skip if you already cloned the project
    git clone <repository_url>
    cd cairn # Or your project's root directory name
    ```

2.  **Navigate to the Frontend Directory:**
    Change into the frontend code directory:

    ```bash
    cd frontend # Assuming your frontend code is in a 'frontend' subfolder
    ```

3.  **Create and Activate a Virtual Environment:**
    Just like the backend, it's best practice to use a separate virtual environment for the frontend to manage its specific dependencies.

      * **Create the environment** within the `frontend` directory:

        ```bash
        python -m venv .venv
        ```

        *(Use `python3` if `python` doesn't point to Python 3)*

      * **Activate the environment:**

          * **Windows (Command Prompt):**
            ```cmd
            .\.venv\Scripts\activate
            ```
          * **Windows (PowerShell):**
            ```powershell
            .\.venv\Scripts\Activate.ps1
            ```
            *(You may need to adjust your execution policy: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process`)*
          * **macOS / Linux (Bash/Zsh):**
            ```bash
            source .venv/bin/activate
            ```

        Your command prompt should now show `(.venv)` at the beginning.

4.  **Install Frontend Dependencies:**
    Install the necessary Python packages listed in the frontend's requirements file:

    ```bash
    pip install -r requirements.txt
    ```

    *(Ensure a `requirements.txt` file exists in your `frontend` directory).*

5.  **Configure Backend API Connection:**
    The frontend needs to know where the backend API is located. This is configured using an environment file.

      * Create a file named `.env` inside the `frontend` directory.

      * Add the following content, specifying the URL where your CAIRN backend is running:

        ```dotenv
        # .env file for CAIRN Frontend

        # URL of the running CAIRN backend API
        API_URL=http://localhost:8000
        ```

      * **Notes:**

          * The default `http://localhost:8000` assumes your backend is running locally on port 8000. Adjust the hostname, port, or add any necessary base path (e.g., `http://localhost:8000/api/v1`) if your backend API is configured differently.
          * Ensure this `.env` file (in the `frontend` directory) is included in your project's `.gitignore` file to avoid committing sensitive information or local configurations.

6.  **Run the Streamlit Application:**
    With the virtual environment active and the `.env` file configured, start the Streamlit app:

    ```bash
    streamlit run streamlit_app.py
    ```

    *(Make sure `streamlit_app.py` is the correct name of your main Streamlit script).*

    Streamlit will typically output lines like:

    ```
    You can now view your Streamlit app in your browser.

    Local URL: http://localhost:8501
    Network URL: http://<your-local-ip>:8501
    ```

7.  **Access the Frontend UI:**
    Open your web browser and navigate to the "Local URL" provided by Streamlit (usually `http://localhost:8501`). You should see the CAIRN frontend interface load.

### Using the UI

Once the application is running in your browser:

1.  Use the **sidebar** (usually on the left) to find filter options for different data columns.
2.  Enter your desired filter criteria.
3.  Click the "**Load Documents**" button (or similar) to send a request to the backend API.
4.  The main area of the page should dynamically update to display the results returned by the backend.

### Troubleshooting

  * **Cannot Connect to Backend / API Errors:**
      * Verify the `API_URL` in `frontend/.env` is correct and points exactly where your backend API is accessible.
      * Ensure the **backend server is running** and responding correctly (you can test backend endpoints directly, e.g., using `curl` or visiting its `/docs` URL).
      * Check the terminal output where you ran the backend (`uvicorn ...`) for any errors.
  * **`ModuleNotFoundError`:**
      * Make sure you have **activated the frontend's virtual environment** (`.venv` inside the `frontend` folder) before running `streamlit run ...`.
      * Confirm you ran `pip install -r requirements.txt` while the frontend virtual environment was active.
  * **Streamlit App Fails to Load:**
      * Check the terminal output where you ran `streamlit run ...` for specific Python errors.
      * Ensure `streamlit_app.py` (or your main script name) exists and is correctly specified in the command.


---

## Troubleshooting

- `Missing env vars`: Ensure `.env` files are in correct folder and activated.
- `ModuleNotFoundError`: Activate the correct venv before `pip install` and running.
- `ResponseValidationError`: All Pydantic fields are `Optional[...]`—the backend must match the Supabase schema exactly.

