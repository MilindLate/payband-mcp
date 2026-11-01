"""Employers who run their own careers site rather than a job board.

Greenhouse, Ashby, Lever, SmartRecruiters and Workday cover an enormous
number of employers, and then stop dead at the largest ones. Google, Meta,
Amazon and Apple all self-host, and #13 has been open since the first week
because of it.

There is no shared shape here -- each of these is one company's endpoint,
named explicitly rather than guessed from a slug, and each will break on its
own schedule. They are kept apart from `ats.py` so that when one does break
it cannot take the board adapters down with it.

What was probed and rejected, so nobody repeats it:

* **amazon.jobs** serves clean JSON (`/en/search.json`) and no pay whatsoever
  -- not in the list, not in `description`, not in the per-job `.json`. Amazon
  renders its Washington and California ranges into the HTML page only.
* **Netflix**, and Eightfold-hosted boards generally, return `job_description`
  over a documented API with no range in it.
* **Apple** (`jobs.apple.com/api`) answers 401 to an anonymous request.
* **Meta** and **Microsoft** did not answer a plain GET at all.

Each of those would need HTML scraping, which is a different kind of
dependency from a JSON API and belongs behind a clearly separate door.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import urllib.error
import urllib.request
from typing import Any

from . import money

TIMEOUT = 30

# One request returns every open role, so there is no pagination and no
# per-posting fetch. `payRanges` is a dedicated field, which makes it a far
# better place to read a range from than the body prose.
ATLASSIAN = "https://www.atlassian.com/endpoint/careers/listings"


class SelfHostedNotFound(LookupError):
    """The employer's own careers endpoint did not answer usefully."""


def _get(url: str, user_agent: str) -> Any:
    req = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"), strict=False)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        raise SelfHostedNotFound(url) from exc


def _atlassian_location(row: dict[str, Any]) -> str:
    """"Seattle - United States -   Seattle, Washington  United States"."""
    first = (row.get("locations") or [""])[0]
    return " ".join(first.replace(" - ", ", ").split())


def atlassian(user_agent: str = "") -> list[dict[str, Any]]:
    rows = _get(ATLASSIAN, user_agent)
    if not isinstance(rows, list):
        raise SelfHostedNotFound(ATLASSIAN)
    out = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("title"):
            continue
        out.append({
            "title": row["title"],
            "location": _atlassian_location(row),
            "url": row.get("applyUrl") or "",
            # payRanges is the field Atlassian renders the legally-required
            # figure into; the body is prose that happens to mention money.
            # Atlassian writes its non-US ranges as "CA$94,500", so the symbol
            # already disambiguates and this does not need #19's location
            # argument -- #23 should still pass it once that lands.
            "pay": money.parse(row.get("payRanges")),
            "company": "Atlassian",
            "board": "atlassian",
        })
    if not out:
        raise SelfHostedNotFound(ATLASSIAN)
    return out


EMPLOYERS = {"atlassian": atlassian}


@dataclass(frozen=True)
class Rejected:
    """An employer whose careers endpoint was probed and rejected."""

    reason: str
    endpoint: str = ""
    issue: int | None = 13
    date: str = ""

    def explain(self, company: str) -> str:
        name = company.strip()
        meta = []
        if self.issue:
            meta.append(f"#{self.issue}")
        if self.date:
            meta.append(f"probed {self.date}")
        cite = f" ({', '.join(meta)})" if meta else ""
        return (
            f"{name} self-hosts. {self.reason.rstrip('.')}. "
            f"This is a settled finding{cite}, not a lookup failure -- no slug will change it."
        )


UNREACHABLE: dict[str, Rejected] = {
    "amazon": Rejected(
        reason="Its Washington and California ranges are rendered into the HTML page only; the JSON API at amazon.jobs carries no pay at all",
        endpoint="amazon.jobs/en/search.json",
        issue=13,
        date="2026-09-01",
    ),
    "apple": Rejected(
        reason="jobs.apple.com/api answers 401 to anonymous requests",
        endpoint="jobs.apple.com/api",
        issue=13,
        date="2026-09-01",
    ),
    "netflix": Rejected(
        reason="Eightfold-hosted board returns job_description over a documented API with no salary range in it",
        endpoint="jobs.netflix.com",
        issue=13,
        date="2026-09-01",
    ),
    "meta": Rejected(
        reason="metacareers.com does not answer a plain GET request without browser session headers",
        endpoint="metacareers.com",
        issue=13,
        date="2026-09-01",
    ),
    "microsoft": Rejected(
        reason="careers.microsoft.com does not answer a plain GET request without browser session headers",
        endpoint="careers.microsoft.com",
        issue=13,
        date="2026-09-01",
    ),
    "google": Rejected(
        reason="careers.google.com renders postings client-side without a public unauthenticated salary API",
        endpoint="careers.google.com",
        issue=13,
        date="2026-09-01",
    ),
    "alphabet": Rejected(
        reason="careers.google.com renders postings client-side without a public unauthenticated salary API",
        endpoint="careers.google.com",
        issue=13,
        date="2026-09-01",
    ),
}

