"""Public job-board APIs, for the pay ranges employers are legally made to publish.

Colorado, California, New York, Washington and Illinois require a salary range
on covered postings. Most other markets -- India, Singapore, much of the EU --
require nothing, so the same role at the same company is posted with a range in
Denver and without one in Bengaluru.

These are documented, public, JSON APIs intended to be read by machines. That
matters: everything here is a supported integration, not scraping, and it does
not break when a marketing site is redesigned.
"""

from __future__ import annotations

import html as _html
import json
import re
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable

import httpx

from . import money, selfhosted, smartrecruiters, workday
from . import __version__

USER_AGENT = f"payband-mcp/{__version__} (+https://github.com/dheerajjha/payband-mcp)"
TIMEOUT = 30

GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
LEVER = "https://api.lever.co/v0/postings/{board}?mode=json"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"

# Greenhouse renders the legally-required range into its own element. Reading
# that is far more reliable than finding two figures in prose, so it is handed
# to the parser as the preferred region.
_PAY_DIV = re.compile(r'<div class="pay-range">(.*?)</div>', re.S)


class BoardNotFound(LookupError):
    """No public job board for this company under the name we tried."""


def _get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            # Some boards emit raw control characters inside description HTML.
            return json.loads(resp.read().decode("utf-8"), strict=False)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            raise BoardNotFound(url) from exc
        raise


def _pay_from_html(
    content: str | None, location: str = ""
) -> dict[str, Any] | None:
    """Published range for a posting, in whatever currency it is published in."""
    raw = _html.unescape(content or "")
    block = _PAY_DIV.search(raw)
    return money.parse(
        content, prefer=block.group(1) if block else None, location=location
    )


def _posting(title, location, url, pay, company, board, detail=None) -> dict[str, Any]:
    posting = {
        "title": title,
        "location": location or "",
        "url": url,
        "pay": pay,
        "company": company,
        "board": board,
    }
    if detail:
        # Some boards only publish a range inside the description, so the pay
        # for this posting costs another request. Carry what that request needs
        # and let the caller decide which postings are worth it.
        posting["_detail"] = detail
        # Until that request is made, pay=None means "not looked at", which
        # is a different claim from "the employer published nothing".
        posting["pay_known"] = False
    return posting


def _greenhouse(board: str) -> list[dict[str, Any]]:
    data = _get(GREENHOUSE.format(board=board))
    return [
        _posting(
            j.get("title"),
            (j.get("location") or {}).get("name"),
            j.get("absolute_url"),
            _pay_from_html(
                j.get("content"), (j.get("location") or {}).get("name") or ""
            ),
            j.get("company_name") or board,
            "greenhouse",
        )
        for j in data.get("jobs", [])
    ]


def _lever(board: str) -> list[dict[str, Any]]:
    data = _get(LEVER.format(board=board))
    if not isinstance(data, list):
        raise BoardNotFound(board)
    out = []
    for j in data:
        body = (j.get("descriptionPlain") or "") + " " + (j.get("description") or "")
        out.append(
            _posting(
                j.get("text"),
                (j.get("categories") or {}).get("location"),
                j.get("hostedUrl"),
                _pay_from_html(
                    body, (j.get("categories") or {}).get("location") or ""
                ),
                board,
                "lever",
            )
        )
    return out


def _ashby(board: str) -> list[dict[str, Any]]:
    data = _get(ASHBY.format(board=board))
    out = []
    for j in data.get("jobs", []):
        pay = None
        # Ashby is the only board that publishes this as real numbers.
        for tier in (j.get("compensation") or {}).get("compensationTiers") or []:
            for comp in tier.get("components") or []:
                if comp.get("compensationType") == "Salary" and comp.get("maxValue"):
                    pay = {
                        "min": float(comp.get("minValue") or comp["maxValue"]),
                        "max": float(comp["maxValue"]),
                        "currency": comp.get("currencyCode") or "USD",
                        "interval": (comp.get("interval") or "year").lower(),
                        "source": "structured",
                    }
                    break
            if pay:
                break
        out.append(
            _posting(
                j.get("title"),
                j.get("location"),
                j.get("jobUrl"),
                pay
                or _pay_from_html(
                    j.get("descriptionHtml"), j.get("location") or ""
                ),
                board,
                "ashby",
            )
        )
    return out


def _workday(slug: str, role: str = "") -> list[dict[str, Any]]:
    if "/" in slug or "://" in slug:
        tenant, site, host = workday.parse_spec(slug)
    else:
        # A bare tenant is the common case, from both the automatic path and
        # board="workday:nvidia". robots.txt names the site, so ask for it
        # rather than making the caller look it up.
        tenant, site, host = slug, "", None
    if not host or not site:
        host, site = workday.discover(tenant, USER_AGENT)
    out = []
    for job in workday.list_postings(host, tenant, site, role, user_agent=USER_AGENT):
        path = job.get("externalPath") or ""
        out.append(
            _posting(
                job.get("title"),
                job.get("locationsText"),
                f"https://{host}/{site}{path}",
                None,
                tenant,
                "workday",
                detail={
                    "provider": "workday",
                    "host": host,
                    "tenant": tenant,
                    "site": site,
                    "path": path,
                },
            )
        )
    return out


def _smartrecruiters(slug: str, role: str = "") -> list[dict[str, Any]]:
    out = []
    for job in smartrecruiters.list_postings(slug, role):
        location = job.get("location") or {}
        posting_id = str(job.get("id") or job.get("uuid") or "")
        if not posting_id:
            continue
        company = job.get("company") or {}
        out.append(
            _posting(
                job.get("name"),
                smartrecruiters.format_location(location),
                f"https://jobs.smartrecruiters.com/{slug}/{posting_id}",
                None,
                company.get("name") or slug,
                "smartrecruiters",
                detail={
                    "provider": "smartrecruiters",
                    "company": slug,
                    "posting_id": posting_id,
                },
            )
        )
    return out


_BOARDS = (
    ("greenhouse", _greenhouse),
    ("ashby", _ashby),
    ("lever", _lever),
    ("smartrecruiters", _smartrecruiters),
    ("workday", _workday),
)
# Boards that answer with everything in one request, so guessing a slug
# against them is cheap. Workday needs host discovery plus a search, so it is
# only tried once these have all missed.
_CHEAP = {"greenhouse", "ashby", "lever", "smartrecruiters"}


def enrich_pay(postings: list[dict[str, Any]], limit: int = 40) -> int:
    """Fetch the published range for postings that keep it behind a second call.

    Returns how many were filled. Bounded, because this is one request per
    posting: the point of doing it after title matching is that the bound is
    reached by the postings a question is actually about.
    """
    pending = [
        p for p in postings if p.get("_detail") and not p.get("pay")
    ][:limit]
    if not pending:
        return 0

    def _one(posting: dict[str, Any]) -> None:
        detail = posting["_detail"]
        if detail.get("provider") == "smartrecruiters":
            posting["pay"] = smartrecruiters.fetch_pay(
                detail["company"], detail["posting_id"]
            )
        else:
            posting["pay"] = workday.fetch_pay(
                detail["host"], detail["tenant"], detail["site"], detail["path"],
                user_agent=USER_AGENT,
            )

    # Workers overlap the waiting, not the asking: each detail-backed adapter
    # has a global throttle, so concurrency never raises its request rate.
    with ThreadPoolExecutor(max_workers=workday.WORKERS) as pool:
        list(pool.map(_one, pending))
    for posting in pending:
        posting["pay_known"] = True
    return len(pending)


_LATIN = str.maketrans({
    "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ß": "ss",
    "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ð": "d", "Ð": "D", "þ": "th", "Þ": "TH", "ı": "i",
})


def _fold_ascii(s: str) -> str:
    """Fold accents and non-ASCII characters to plain lowercase ASCII."""
    return (
        unicodedata.normalize("NFKD", s.translate(_LATIN))
        .encode("ascii", "ignore")
        .decode()
        .strip()
        .lower()
    )


def _slugs_for_name(company: str) -> list[str]:
    """Plausible job-board tokens for a company name, most likely first.

    The raw name is only a candidate when it is already slug-shaped. It used
    to be included unconditionally, so "Bosch Group" produced a candidate with
    a space in it, which went straight into a URL and raised InvalidURL from
    deep inside httpx instead of the BoardNotFound that tells a caller what to
    do next. No job board has a slug with whitespace in it.
    """
    base = _fold_ascii(company)
    collapsed = re.sub(r"[^a-z0-9]+", "", base)
    hyphen = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    candidates = [collapsed, hyphen]
    if base and re.fullmatch(r"[a-z0-9._~-]+", base):
        candidates.append(base)
    seen: set[str] = set()
    return [s for s in candidates if s and not (s in seen or seen.add(s))]


_LEGAL_SUFFIX = re.compile(
    r"[\s,]+(?:inc|llc|ltd|limited|plc|gmbh|ag|se|ab|corp|corporation|company"
    r"|co(?:\.?,?\s*ltd)?|s\.?a|s\.?p\.?a|n\.?v|b\.?v"
    r"|a[./]?s|ehf|d\.?o\.?o)\.?\s*$",
    re.I,
)


def _strip_legal_suffix(company: str) -> str | None:
    """The name without one trailing legal suffix, or None if it has none."""
    name = company.strip()
    stripped = _LEGAL_SUFFIX.sub("", name)
    return stripped if stripped and stripped != name else None


def board_slugs(company: str) -> list[str]:
    """Job-board tokens for a company name, most likely first.

    A trailing legal suffix ("Inc.", "SE", "AB") is not part of a board's
    token, so the name without it is tried first, then the full name.
    """
    folded = _fold_ascii(company)
    stripped = _strip_legal_suffix(folded)
    names = [stripped, folded] if stripped else [folded]
    seen: set[str] = set()
    return [
        s
        for name in names
        for s in _slugs_for_name(name)
        if not (s in seen or seen.add(s))
    ]


def fetch_postings(
    company: str, board: str | None = None, role: str = ""
) -> tuple[str, list[dict[str, Any]]]:
    """Find a company's public job board and return every posting on it.

    Tries Greenhouse, Ashby, Lever and SmartRecruiters against each plausible
    slug, then Workday discovery. Pass `board` as "greenhouse:slug" (or another
    provider name) to skip guessing when the token differs from the company.

    Raises BoardNotFound if nothing answers.
    """
    if board:
        name, _, slug = board.partition(":")
        # A self-hosted employer is one endpoint, not a board with tenants,
        # so it is addressed by name alone: board="atlassian".
        if name in selfhosted.EMPLOYERS and not slug:
            return name, selfhosted.EMPLOYERS[name](USER_AGENT)
        loader = dict(_BOARDS).get(name)
        if not loader:
            raise ValueError(
                f"Unknown board {name!r}; expected one of "
                f"{', '.join(n for n, _ in _BOARDS)}."
            )
        target = slug or board_slugs(company)[0]
        postings = (
            loader(target, role)
            if name in {"workday", "smartrecruiters"}
            else loader(target)
        )
        if not postings:
            raise BoardNotFound(f"{board} has no postings.")
        if name == "workday":
            found = postings[0]["_detail"]
            return f"workday:{found['tenant']}/{found['site']}", postings
        return f"{name}:{target}", postings

    # Self-hosted employers first: an exact name match, one request, and no
    # slug guessing. Only fires for a company we have written an adapter for,
    # so it costs nothing for everyone else.
    own = selfhosted.EMPLOYERS.get(re.sub(r"[^a-z0-9]+", "", _fold_ascii(company)))
    if own:
        try:
            postings = own(USER_AGENT)
            if postings:
                return company.strip().lower(), postings
        except (selfhosted.SelfHostedNotFound, urllib.error.URLError,
                json.JSONDecodeError, OSError):
            pass  # fall through to the boards rather than fail outright

    for name, loader in _BOARDS:
        if name not in _CHEAP:
            continue
        for slug in board_slugs(company):
            try:
                postings = (
                    loader(slug, role) if name == "smartrecruiters" else loader(slug)
                )
            except (
                BoardNotFound,
                smartrecruiters.SmartRecruitersNotFound,
                urllib.error.URLError,
                httpx.HTTPError,
                json.JSONDecodeError,
                OSError,
            ):
                continue
            if postings:
                return f"{name}:{slug}", postings

    # Last, because it costs host discovery before it can answer at all.
    for slug in board_slugs(company)[:1]:
        try:
            postings = _workday(slug, role)
        except (workday.WorkdayNotFound, ValueError, urllib.error.URLError,
                json.JSONDecodeError, OSError):
            postings = []
        if postings:
            found = postings[0]["_detail"]
            return f"workday:{found['tenant']}/{found['site']}", postings
    raise BoardNotFound(
        f"No public Greenhouse, Ashby, Lever or SmartRecruiters board found "
        f"for {company!r} "
        f"(tried slugs {board_slugs(company)}). Two common reasons: the board "
        f"token differs from the company name -- open their careers page and "
        f"read it out of the URL (job-boards.greenhouse.io/<slug>, "
        f"jobs.ashbyhq.com/<slug>, jobs.lever.co/<slug>, "
        f"careers.smartrecruiters.com/<slug>), then pass "
        f"board='greenhouse:<slug>' -- or the employer self-hosts and is on "
        f"none of these boards, which is the case for Google, Meta, Amazon "
        f"and Apple. Workday tenants are found automatically, but only under "
        f"the company name: if theirs differs, pass "
        f"board='workday:<tenant>/<site>' or paste the careers URL. "
        f"If the employer really is unreachable, market_rate across their "
        f"direct competitors is the closest available answer -- those are the "
        f"offers they are competing with, and several of them do publish."
    )


def matching(postings: Iterable[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    """Postings whose title contains every significant word in `role`."""
    words = [w for w in re.findall(r"[a-z0-9+#]{2,}", role.lower())]
    if not words:
        return list(postings)
    out = []
    for p in postings:
        title = (p.get("title") or "").lower()
        if all(w in title for w in words):
            out.append(p)
    return out
