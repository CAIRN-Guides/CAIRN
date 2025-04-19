# utc_downloader_nb.py  –  v2.1  (with detailed inline documentation)
"""
Helper utilities for downloading **all** filings in a Washington UTC docket.

Key improvements vs. the original:
1.  Keeps the *native* file extension (xlsx, pptx, etc.) when the portal
    already shows it in the link text.
2.  If the link text is missing / extension‑less, we read the
    Content‑Disposition response header and rename the file accordingly.
3.  Falls back to MIME sniffing via the Content‑Type header and, only
    as a last resort, appends '.pdf'.

Typical use in a notebook
-------------------------
>>> from utc_downloader_nb import fetch_docket
>>> fetch_docket("220066", 2022)             # downloads to ./utc_220066
"""

from __future__ import annotations
import datetime as _dt
import logging, os, re, time, mimetypes
from pathlib import Path
from typing import Dict, Tuple
from urllib.parse import quote_plus, unquote

import requests
from bs4 import BeautifulSoup


# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #
BASE_PORTAL = "https://www.utc.wa.gov/casedocket"        # HTML docket pages
BASE_PROXY  = "https://apiproxy.utc.wa.gov/cases/GetDocument"  # file endpoint
HEADERS     = {"User-Agent": "utc-downloader/nb-2.1"}    # polite UA string

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOG = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Helper functions                                                            #
# --------------------------------------------------------------------------- #
def _clean(text: str) -> str:
    """
    Make the link text filesystem‑safe **without** forcing a .pdf suffix.

    * quote_plus(.., safe=…) keeps spaces but removes shell‑hostile chars.
    * unquote() after quote_plus handles accidental double‑encoding.
    * We do NOT tack on '.pdf' here—that is handled downstream once we
      know the server’s real MIME type.
    """
    text = quote_plus(text, safe="()[]{}&-_.").replace("+", " ")
    # Strip weird Unicode control chars (zero‑width spaces, NBSP, etc.)
    return re.sub(r"[^\w\s\-\.\(\)\[\]\{\}&]", "", unquote(text)).strip()


def _scrape_year(docket: str, year: int) -> Dict[str, Tuple[str, str]]:
    """
    Parse one docket‑year page and return:

        {docID: (download_url, filename_guess)}

    * filename_guess is whatever text the portal shows (cleaned).
    * docID serves as the de‑duplication key across years.
    """
    url = f"{BASE_PORTAL}/{year}/{docket}/docsets"
    LOG.debug("Fetching %s", url)

    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 404:
        LOG.info("No filings for %s in %s", docket, year)
        return {}
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    links: Dict[str, Tuple[str, str]] = {}

    # Look for every <a> whose href points to the proxy endpoint
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(BASE_PROXY):
            doc_id   = re.search(r"docID=(\d+)", href).group(1)
            raw_name = a.get_text(strip=True) or f"UTC_doc_{doc_id}"
            links[doc_id] = (href, _clean(raw_name))

    LOG.info("• %s – %d docs", year, len(links))
    return links


def _filename_from_headers(resp: requests.Response, fallback: str) -> str:
    """
    Decide the *final* filename after we receive the HTTP response.

    Priority order:
    1. Content‑Disposition 'filename=' wins (most accurate).
    2. If no filename but Content‑Type maps cleanly via mimetypes,
       append that extension to the fallback.
    3. Otherwise default to '.pdf' for legacy scans or odd servers.
    """
    cd = resp.headers.get("Content-Disposition", "")
    match = re.search(r'filename="?(?P<fn>[^"]+)"?', cd)
    if match:
        fn_server = _clean(match.group("fn"))
        ext       = Path(fn_server).suffix.lower()
        # Use the server‑supplied name *only* if our earlier guess lacked an ext
        if ext and not Path(fallback).suffix:
            return fn_server

    # Still no extension?  Try inferring from Content‑Type
    if not Path(fallback).suffix:
        ext = mimetypes.guess_extension(resp.headers.get("Content-Type", ""))
        if ext:
            return f"{fallback}{ext}"
        # Truly unknown – assume PDF (same as legacy behaviour)
        return f"{fallback}.pdf"

    return fallback


# --------------------------------------------------------------------------- #
# Public‑facing helpers                                                       #
# --------------------------------------------------------------------------- #
def list_document_links(
    docket: str,
    start_year: int,
    end_year: int | None = None,
) -> Dict[str, Tuple[str, str]]:
    """
    Crawl every docket year from start_year → end_year (inclusive) and collect
    unique download links.  Returns the same mapping structure as `_scrape_year`.
    """
    end_year  = end_year or _dt.datetime.now().year
    all_links: Dict[str, Tuple[str, str]] = {}

    for yr in range(start_year, end_year + 1):
        all_links.update(_scrape_year(docket, yr))   # update() de‑dupes on key

    LOG.warning("Total unique documents: %d", len(all_links))
    return all_links


def download_documents(
    links: Dict[str, Tuple[str, str]],
    outdir: Path,
    delay: float = 0.75,
) -> None:
    """
    Download each filing to `outdir`.

    * delay throttles requests so we don’t hammer the UTC servers.
    * Existing files with the same name are skipped (idempotent re‑runs).
    * Each response is analysed to fix the Excel/PPT naming issue.
    """
    outdir.mkdir(parents=True, exist_ok=True)

    for url, name_guess in links.values():
        tmp_path = outdir / name_guess
        if tmp_path.exists():       # user already has the file
            continue

        LOG.debug("Downloading %s", name_guess)
        time.sleep(delay)           # be polite; servers rate‑limit

        with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
            r.raise_for_status()

            # Decide the *real* filename now that headers are known
            final_name = _filename_from_headers(r, name_guess)
            fpath      = outdir / final_name

            # Stream‑to‑disk in chunks (handles large multi‑MB PDFs gracefully)
            with fpath.open("wb") as fh:
                for chunk in r.iter_content(8192):
                    fh.write(chunk)

        LOG.info("✓ %s", final_name)


def fetch_docket(
    docket: str,
    start_year: int,
    end_year: int | None = None,
    outdir: str | Path | None = None,
    delay: float = 0.75,
) -> None:
    """
    One‑liner convenience wrapper:
        • Pull the link list
        • Download every file

    Example
    -------
    >>> fetch_docket("220066", 2022)   # current docket
    >>> fetch_docket("200001", 2000, 2010,
                     outdir="~/Downloads/utc_200001", delay=1.0)
    """
    outdir = Path(os.path.expanduser(outdir or f"./utc_{docket}"))
    links  = list_document_links(docket, start_year, end_year)
    download_documents(links, outdir, delay)
