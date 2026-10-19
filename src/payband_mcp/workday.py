"""Workday, which hosts the enterprises that are on none of the startup boards.

Greenhouse, Ashby and Lever cover startups and scale-ups well and large
incumbents hardly at all. NVIDIA, Salesforce, Adobe, Cisco, HPE and eBay are
all on Workday, and every one of them was previously unreachable.

Two things make Workday different from the other boards:

* **The search response carries no pay.** A range only appears in the job
  description, which is a second request per posting. So postings are listed
  first, filtered by title, and only the survivors are fetched in full --
  otherwise answering one question about NVIDIA would mean 1,693 requests.
* **There is no slug to guess.** A tenant lives on one of several numbered
  hosts and exposes a site whose id is arbitrary ("NVIDIAExternalCareerSite",
  "External_Career_Site", "Jobsathpe"). Rather than brute-force that space,
  we read robots.txt, which names the public site in its Sitemap line. That
  is the file the site publishes to tell automated clients what to read, so
  discovery costs one cheap request per host and respects the site's own
  statement of what is public.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Iterator

from . import money

TIMEOUT = 30
# Observed frequency, so the common case resolves on the first request.
HOSTS = (5, 1, 3, 2, 12, 10, 103, 101)
PAGE = 20
# Workday is not rate-limited in any documented way, but a detail fetch per
# posting is a real load. One request every 250ms is slower than a person
# clicking and fast enough to be useful. The gap is enforced across threads,
# so fetching in parallel overlaps the waiting on Workday's side without
# ever raising the rate we ask at.
MIN_INTERVAL = 0.25
WORKERS = 4

_SITEMAP = re.compile(r"^Sitemap:\s*https?://[^/]+/(?:recruiting/[^/]+/)?([^/\s]+)/", re.M | re.I)
_ALLOW = re.compile(r"^Allow:\s*/([^/\s]+)/\s*$", re.M | re.I)
_DISALLOWED_SITE = {"apply", "refreshfacet", "talentcommunity", "wday"}

_last_request = 0.0
_throttle_lock = threading.Lock()


class WorkdayNotFound(LookupError):
    """No public Workday career site for this tenant."""


def _throttle() -> None:
    global _last_request
    with _throttle_lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _request(url: str, payload: dict[str, Any] | None = None, user_agent: str = "") -> Any:
    _throttle()
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"), strict=False)


def _robots(host: str, user_agent: str) -> str:
    _throttle()
    req = urllib.request.Request(
        f"https://{host}/robots.txt", headers={"User-Agent": user_agent}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", "replace")


def discover(tenant: str, user_agent: str = "") -> tuple[str, str]:
    """Find which host a tenant is on and which site it publishes.

    Returns (host, site_id). Raises WorkdayNotFound if no host answers with a
    robots.txt that names one.
    """
    for number in HOSTS:
        host = f"{tenant}.wd{number}.myworkdayjobs.com"
        try:
            text = _robots(host, user_agent)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            continue
        for match in (_SITEMAP.search(text), _ALLOW.search(text)):
            if match and match.group(1).lower() not in _DISALLOWED_SITE:
                return host, match.group(1)
    raise WorkdayNotFound(
        f"No public Workday site found for tenant {tenant!r} on hosts "
        f"{', '.join('wd%d' % n for n in HOSTS)}. If the careers page is a "
        f"Workday one its URL reads https://<tenant>.wd<n>.myworkdayjobs.com/"
        f"<site>; pass board='workday:<tenant>/<site>' with those two values."
    )


def parse_spec(spec: str) -> tuple[str, str, str | None]:
    """Accept 'tenant/site', or a pasted careers URL, and return both parts."""
    spec = spec.strip()
    url = re.match(
        r"https?://(?:([\w-]+)\.)?(wd\d+)\.myworkday(?:jobs|site)\.com/"
        r"(?:wday/cxs/([\w-]+)/)?(?:recruiting/([\w-]+)/)?(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)",
        spec,
    )
    if url:
        tenant = url.group(1) or url.group(3) or url.group(4)
        return tenant, url.group(5), f"{tenant}.{url.group(2)}.myworkdayjobs.com"
    tenant, _, site = spec.partition("/")
    if not tenant or not site:
        raise ValueError(
            "Expected board='workday:<tenant>/<site>' or a careers-page URL, "
            f"got {spec!r}."
        )
    return tenant, site, None


def _endpoint(host: str, tenant: str, site: str) -> str:
    return f"https://{host}/wday/cxs/{tenant}/{site}"


def list_postings(
    host: str, tenant: str, site: str, role: str = "", cap: int = 200,
    user_agent: str = "",
) -> Iterator[dict[str, Any]]:
    """Page through the search endpoint, narrowing server-side when we can."""
    base = _endpoint(host, tenant, site)
    seen = 0
    for offset in range(0, cap, PAGE):
        payload = {
            "appliedFacets": {}, "limit": PAGE, "offset": offset, "searchText": role,
        }
        try:
            data = _request(f"{base}/jobs", payload, user_agent)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            if offset == 0:
                raise WorkdayNotFound(f"{tenant}/{site}: {exc}") from exc
            return
        batch = data.get("jobPostings") or []
        for job in batch:
            yield job
            seen += 1
        if len(batch) < PAGE or seen >= min(cap, data.get("total", cap)):
            return


def fetch_pay(
    host: str, tenant: str, site: str, external_path: str, user_agent: str = ""
) -> dict[str, Any] | None:
    """A posting's published range, which only exists in its description."""
    try:
        data = _request(_endpoint(host, tenant, site) + external_path, None, user_agent)
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        return None
    info = data.get("jobPostingInfo") or {}
    location = info.get("location") or ""
    return money.parse(
        info.get("jobDescription"),
        location=location if isinstance(location, str) else "",
    )
