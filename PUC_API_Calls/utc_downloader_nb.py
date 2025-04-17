# utc_downloader_nb.py
"""
Jupyter‑notebook helper for downloading *all* PDFs in a Washington UTC docket.

Core functions:
    list_document_links(docket: str, start_year: int, end_year: int | None) -> dict
    download_documents(links: dict, outdir: Path, delay: float)

Usage in a notebook:
    from utc_downloader_nb import fetch_docket

    # downloads every filing in docket 220066 (2022‑present) to ./utc_220066
    fetch_docket("220066", 2022)

Requirements:
    pip install requests beautifulsoup4
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, Tuple

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

BASE_PORTAL = "https://www.utc.wa.gov/casedocket"
BASE_PROXY = "https://apiproxy.utc.wa.gov/cases/GetDocument"
HEADERS = {"User-Agent": "utc-downloader/nb-2.0"}

# configure a root logger once per kernel
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOG = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _sanitize_filename(title: str) -> str:
    fn = quote_plus(title).replace("+", " ")
    return fn if fn.lower().endswith(".pdf") else f"{fn}.pdf"


def _scrape_year(docket: str, year: int) -> Dict[str, Tuple[str, str]]:
    """Return {docID: (url, filename)} for one year of a docket or {} if none."""
    url = f"{BASE_PORTAL}/{year}/{docket}/docsets"
    LOG.debug("Fetching %s", url)

    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 404:
        LOG.info("No filings for %s in %s", docket, year)
        return {}
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    links: Dict[str, Tuple[str, str]] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(BASE_PROXY):
            doc_id = re.search(r"docID=(\d+)", href).group(1)
            title = a.get_text(strip=True) or f"UTC_doc_{doc_id}"
            links[doc_id] = (href, _sanitize_filename(title))
    LOG.info("• %s – %d docs", year, len(links))
    return links


# --------------------------------------------------------------------------- #
# Public functions                                                            #
# --------------------------------------------------------------------------- #
def list_document_links(
    docket: str,
    start_year: int,
    end_year: int | None = None,
) -> Dict[str, Tuple[str, str]]:
    """Collect unique proxy URLs for every year in range."""
    end_year = end_year or _dt.datetime.now().year
    all_links: Dict[str, Tuple[str, str]] = {}
    for yr in range(start_year, end_year + 1):
        yearly = _scrape_year(docket, yr)
        all_links.update(yearly)  # de‑dupes via docID key
    LOG.warning("Total unique documents: %d", len(all_links))
    return all_links


def download_documents(
    links: Dict[str, Tuple[str, str]],
    outdir: Path,
    delay: float = 0.75,
) -> None:
    """Download each URL to `outdir` (skips if file already exists)."""
    outdir.mkdir(parents=True, exist_ok=True)
    for url, fname in links.values():
        fpath = outdir / fname
        if fpath.exists():
            continue
        LOG.debug("Downloading %s", fname)
        time.sleep(delay)
        with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
            r.raise_for_status()
            with fpath.open("wb") as fh:
                for chunk in r.iter_content(8192):
                    fh.write(chunk)
        LOG.info("✓ %s", fname)


def fetch_docket(
    docket: str,
    start_year: int,
    end_year: int | None = None,
    outdir: str | Path | None = None,
    delay: float = 0.75,
) -> None:
    """
    Convenience wrapper: list → download in one call.

    Examples
    --------
    >>> fetch_docket("220066", 2022)
    >>> fetch_docket("250108", 2025, outdir="~/Downloads/utc_250108", delay=1.0)
    """
    outdir = Path(outdir or f"./utc_{docket}")
    links = list_document_links(docket, start_year, end_year)
    download_documents(links, outdir, delay)
