"""SmartRecruiters' public Posting API.

The list endpoint carries titles and locations but not the job description,
which is where employers publish a pay range.  Keep those two steps separate:
list and title-filter first, then let the caller fetch details only for the
postings it is about to use.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Iterator

import httpx

from . import __version__, money

BASE = "https://api.smartrecruiters.com/v1/companies/{company}/postings"
PAGE = 100
CAP = 200
TIMEOUT = 30
MIN_INTERVAL = 0.25
USER_AGENT = (
    f"payband-mcp/{__version__} (+https://github.com/dheerajjha/payband-mcp)"
)

_last_request = 0.0
_throttle_lock = threading.Lock()


class SmartRecruitersNotFound(LookupError):
    """No public SmartRecruiters board exists under this company id."""


def _throttle() -> None:
    global _last_request
    with _throttle_lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _request(
    company: str, posting_id: str | None = None, **params: Any
) -> dict[str, Any]:
    _throttle()
    url = BASE.format(company=company)
    if posting_id:
        url += f"/{posting_id}"
    try:
        response = httpx.get(
            url,
            params=params or None,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 404):
            raise SmartRecruitersNotFound(company) from exc
        raise
    data = response.json()
    if not isinstance(data, dict):
        raise SmartRecruitersNotFound(company)
    return data


def list_postings(
    company: str, role: str = "", cap: int = CAP
) -> Iterator[dict[str, Any]]:
    """Page through public postings, using the API's search to narrow first."""
    seen = 0
    for offset in range(0, cap, PAGE):
        page_size = min(PAGE, cap - seen)
        params: dict[str, Any] = {"limit": page_size, "offset": offset}
        if role:
            params["q"] = role
        data = _request(company, **params)
        batch = data.get("content")
        if not isinstance(batch, list):
            raise SmartRecruitersNotFound(company)
        for job in batch:
            if isinstance(job, dict):
                yield job
                seen += 1
        total = data.get("totalFound")
        available = total if isinstance(total, int) else cap
        if len(batch) < page_size or seen >= min(cap, available):
            return


def format_location(location: Any) -> str:
    """Use the same location label for list results and detail pay parsing."""
    if not isinstance(location, dict):
        return ""
    full = location.get("fullLocation")
    if isinstance(full, str) and full.strip():
        return full
    return ", ".join(
        part
        for key in ("city", "region", "country")
        if isinstance((part := location.get(key)), str) and part.strip()
    )


def fetch_pay(company: str, posting_id: str) -> dict[str, Any] | None:
    """Read a published range from the sections of one posting detail."""
    try:
        data = _request(company, posting_id)
    except (SmartRecruitersNotFound, httpx.HTTPError, ValueError):
        return None
    sections = (data.get("jobAd") or {}).get("sections") or {}
    if not isinstance(sections, dict):
        return None
    content = " ".join(
        section.get("text") or ""
        for section in sections.values()
        if isinstance(section, dict)
    )
    return money.parse(content, location=format_location(data.get("location")))
