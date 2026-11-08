"""MCP server exposing Blind company research.

Blind's own /search/ is robots-disallowed and ranks badly ("Roku India RTO"
returns twelve unrelated referral posts). But the company topic path accepts
*any* keyword, not only the ones Blind suggests, so
/company/Intuit/posts/intuit-maternity returns exactly the maternity threads.
That is how `find` and `research` search: precise, company-scoped, and on a
path robots.txt permits.
"""

from __future__ import annotations

import argparse
import os
import sys
import re
from functools import lru_cache
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import ats, fx, http, levels, parse

from . import __version__

mcp = MCPServer("payband", version=__version__)

# Blind has answered every non-browser request with 403 since around September
# 2026 (#12), so the five tools that read it can only raise. A tool list is
# part of what the model reads before deciding what to do, and five entries
# that always fail cost context and invite dead ends -- so they are not
# registered unless asked for. The code and its tests stay exactly where they
# are, and PAYBAND_ENABLE_BLIND=1 brings them back the moment the block
# lifts or an operator has a legitimate route through it.
BLIND_ENABLED = (http.env("ENABLE_BLIND", "") or "").strip().lower() in {
    "1", "true", "yes", "on",
}


def blind_tool():
    """Register a Blind-backed tool only when Blind is reachable."""
    return mcp.tool() if BLIND_ENABLED else (lambda fn: fn)

_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "how", "what", "and", "or",
    "in", "at", "of", "for", "to", "on", "many", "much", "they", "give",
    "their", "from", "side", "it", "its", "with", "you", "your", "can", "i",
}


# Blind threads are dominated by low-content replies. Ranking comments by
# upvotes surfaces these over the actual answer, so they are filtered out
# before ranking rather than after.
_NOISE = re.compile(
    r"^(tc\??|tc or gtfo|tc and yoe|tc\?? ?/? ?yoe\??|yoe\??|same|same question|"
    r"watching|following|rn|bt|bt please|updoot|commenting|remindme.*|\+1|"
    r"can you refer.*|.{0,40}referral.{0,40})[\s.!?]*$",
    re.I,
)


# Referral and job-hunt posts swamp every Blind listing and never answer a
# question about the company. Dropped before ranking.
_JUNK_TITLE = re.compile(
    r"referral|refer me|looking for (a )?(job|role|referr)|seeking (a )?(job|role|referr)"
    r"|laid off|resume review|open to work|hiring\?|need referr",
    re.I,
)


def _is_junk(card: dict[str, Any]) -> bool:
    return bool(_JUNK_TITLE.search(card.get("title") or ""))


def _informative(text: str) -> bool:
    stripped = text.strip()
    has_duration_answer = bool(
        re.search(r"\b\d+\s+(day|days|week|weeks|month|months|year|years)\b", stripped, re.I)
    )
    return (len(stripped) > 25 or has_duration_answer) and not _NOISE.match(stripped)


def _rank_comments(
    comments: list[dict[str, Any]], words: set[str], limit: int
) -> list[dict[str, Any]]:
    """Rank by overlap with the question, then by upvotes. Noise is dropped."""
    flat: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for c in comments:
        for node in (c, *(c.get("replies") or [])):
            key = (node.get("author"), node.get("text"))
            if key not in seen:
                seen.add(key)
                flat.append(node)

    def score(c: dict[str, Any]) -> tuple[int, int]:
        overlap = len(words & set(_keywords(c.get("text") or "")))
        return (overlap, c.get("likes") or 0)

    useful = [c for c in flat if _informative(c.get("text") or "")]
    ranked = sorted(useful, key=score, reverse=True)
    return [
        {k: v for k, v in c.items() if k != "replies"}
        for c in ranked
        if score(c)[0] > 0
    ][:limit] or [
        {k: v for k, v in c.items() if k != "replies"} for c in ranked[:limit]
    ]


# Blind's topic slugs are terse; questions are not. Map the common ones so
# "work life balance" still finds the `wlb` topic.
_TOPIC_ALIASES = {
    "wlb": {"work", "life", "balance", "wlb", "hours", "burnout", "overtime"},
    "rsu": {"rsu", "stock", "equity", "grant", "vest", "refresher"},
    "refresher": {"refresher", "refresh", "rsu", "grant"},
    "layoffs": {"layoff", "layoffs", "fired", "riff", "rif", "cuts", "severance"},
    "interview": {"interview", "loop", "onsite", "screen", "hiring", "rounds"},
    "culture": {"culture", "toxic", "management", "manager", "politics", "morale"},
    "india": {"india", "indian", "bengaluru", "bangalore", "blr", "hyderabad",
              "gurugram", "gurgaon", "mumbai", "noida", "pune"},
}


def _match_topic(topics: list[str], words: set[str]) -> str | None:
    """Pick the topic a question is really about."""
    best, best_score = None, 0
    for topic in topics:
        vocab = _TOPIC_ALIASES.get(topic, set()) | set(_keywords(topic.replace("-", " ")))
        score = len(words & vocab)
        if score > best_score:
            best, best_score = topic, score
    return best


# Common in questions, useless as Blind keywords: they match hundreds of
# loosely-related threads instead of narrowing. "maternity" is a good probe;
# "policy" is not.
_LOW_SIGNAL = {
    "policy", "policies", "details", "detail", "know", "want", "tell", "about",
    "like", "any", "company", "employee", "employees", "people", "actually",
    "really", "still", "need", "question", "questions", "get", "getting",
    "good", "bad", "better", "best", "worth", "there", "here", "who", "when",
    "where", "why", "which", "some", "more", "most", "new", "old", "one",
    "time", "year", "years", "guys", "anyone", "someone", "thing", "things",
    "give", "given", "does", "doing", "have", "has", "had", "was", "were",
}
_MAX_PROBES = 4


def _probe_terms(question: str, company: str, topics: list[str]) -> list[str]:
    """Keywords worth probing, most distinctive first.

    A matched suggested topic leads (Blind curates those), then the question's
    own words longest-first -- length is a cheap proxy for specificity.
    """
    words = set(_keywords(question))
    terms: list[str] = []

    topic = _match_topic(topics, words)
    if topic:
        terms.append(topic)

    skip = set(_keywords(company)) | _LOW_SIGNAL
    rest = [w for w in set(_keywords(question)) if w not in skip and len(w) > 3]
    for word in sorted(rest, key=len, reverse=True):
        if word not in terms:
            terms.append(word)
    return terms[:_MAX_PROBES]


def _slug(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")


def _keywords(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]{2,}", text.lower()) if w not in _STOPWORDS]


def _company_candidates(company: str) -> list[str]:
    """Blind URL spellings to try, most-likely first.

    The slug is case-insensitive, so one lowercase-hyphenated candidate covers
    most companies in a single request -- including multi-word names, which
    Blind writes with hyphens ('Goldman Sachs' -> 'goldman-sachs'). The
    remaining forms are fallbacks for names we guess wrong. Order matters:
    each candidate is a throttled request, so a company that resolves on the
    first try costs ~1.5s and one that fails costs the whole list.
    """
    collapsed = re.sub(r"\s+", "-", company.strip())
    ordered = [
        collapsed.lower(),
        collapsed,
        collapsed.title(),
        company.strip(),
        collapsed.upper(),
    ]
    seen: set[str] = set()
    return [c for c in ordered if c and not (c in seen or seen.add(c))]


@lru_cache(maxsize=128)
def _resolve(company: str) -> str:
    """Find a company's Blind URL segment, trying the likely spellings."""
    candidates = _company_candidates(company)
    for name in candidates:
        try:
            http.fetch(f"/company/{name}/posts")
            return name
        except http.BlindBlocked:
            raise  # an outage, not a bad company name -- say so plainly
        except Exception:
            continue
    raise ValueError(
        f"No Blind company page found for {company!r} (tried {candidates}). "
        f"Blind writes multi-word names with hyphens, e.g. 'Goldman-Sachs'; "
        f"if the company trades under a different name there, try that."
    )


@blind_tool()
def company_topics(company: str) -> dict[str, Any]:
    """List the discussion topics Blind itself suggests for a company.

    These are the highest-signal entry points -- e.g. Roku exposes india, wlb,
    culture, layoffs, interview, rsu. Use one as the `topic` for company_posts.
    """
    name = _resolve(company)
    meta = parse.parse_company_topics(http.fetch(f"/company/{name}/posts"))
    prefix = f"{_slug(name)}-"
    return {
        "company": name,
        "topics": [t.removeprefix(prefix) for t in meta["topics"]],
        "total_posts": meta["total_results"],
        "max_page": meta["max_page"],
    }


@blind_tool()
def company_posts(
    company: str, topic: str | None = None, page: int = 1, limit: int = 25
) -> dict[str, Any]:
    """List posts about a company, optionally narrowed to one topic.

    `topic` accepts a bare keyword from company_topics (e.g. "india", "wlb").
    """
    name = _resolve(company)
    path = f"/company/{name}/posts"
    if topic:
        path += f"/{_slug(name)}-{_slug(topic)}"
    if page > 1:
        path += f"?page={page}"

    posts = parse.parse_listing(http.fetch(path))
    return {
        "company": name,
        "topic": topic,
        "page": page,
        "count": len(posts[:limit]),
        "posts": posts[:limit],
    }


@blind_tool()
def read_post(url: str, max_comments: int = 40) -> dict[str, Any]:
    """Read one Blind post in full.

    Returns the body, Blind's own AI summary of the comment thread, and the
    comments with each commenter's employer -- which is how you weigh a claim
    (an answer from someone at the company differs from a passer-by).
    """
    if "/post/" not in url:
        raise ValueError("Expected a Blind post URL containing /post/.")
    post = parse.parse_post(http.fetch(url))
    post["comments"] = post["comments"][:max_comments]
    return post


@blind_tool()
def find(
    company: str, keyword: str, limit: int = 25, page: int = 1
) -> dict[str, Any]:
    """Find a company's posts about one keyword.

    This is how you search Blind. The company topic path accepts any keyword,
    so `find("Intuit", "maternity")` returns exactly the maternity threads --
    which paging the main listing will not surface, since they can be years
    deep. Prefer one distinctive noun ("maternity", "rto", "refresher");
    vague words like "policy" match hundreds of loosely-related posts.

    Fetches only the requested page (1-based); pagination is caller-driven.
    `total_matches` counts all matches, while `posts` contains at most `limit`
    cards from this page. `max_page` is the last page linked by Blind (defaults
    to 1 if no pagination is present). Request page=2, etc. to see more; use a
    larger limit to avoid truncating cards within a page. `limit=0` returns
    metadata only. An empty later page is normal: stop paging, not a signal
    that the keyword has no matches. An empty first page means no matches.
    Never falls back to the generic listing.
    """
    if type(page) is not int or page < 1:
        raise ValueError("page must be a positive integer")
    if type(limit) is not int or limit < 0:
        raise ValueError("limit must be a non-negative integer")
    name = _resolve(company)
    path = f"/company/{name}/posts/{_slug(name)}-{_slug(keyword)}"
    if page > 1:
        path += f"?page={page}"
    html = http.fetch(path)
    meta = parse.parse_company_topics(html)
    return {
        "company": name,
        "keyword": keyword,
        "page": page,
        "max_page": meta["max_page"],
        "total_matches": meta["total_results"] or 0,
        "posts": parse.parse_listing(html)[:limit],
    }


@blind_tool()
def research(company: str, question: str, max_posts: int = 4) -> dict[str, Any]:
    """Answer a question about a company by pulling the most relevant threads.

    Probes the distinctive words in the question against Blind's keyword-scoped
    company pages, merges the hits, then returns the best threads in full with
    Blind's own AI summary and the comments that actually address the question.

    Ask naturally: "how many days in office in India", "what is the maternity
    leave policy", "do they require a PhD".
    """
    name = _resolve(company)
    words = set(_keywords(question))
    probes = _probe_terms(question, name, company_topics(name)["topics"])

    cards: list[dict[str, Any]] = []
    tried: dict[str, int] = {}
    seen: set[str] = set()
    for term in probes:
        try:
            hits = find(name, term, limit=40)["posts"]
        except Exception:
            continue
        tried[term] = len(hits)
        for card in hits:
            if card["url"] not in seen:
                seen.add(card["url"])
                # A term matching 7 posts is a sharper signal than one matching
                # 300: "maternity" means one thing, "leave" means three.
                card["matched_keyword"] = term
                card["_specific"] = len(hits) <= 10
                cards.append(card)

    cards = [c for c in cards if not _is_junk(c)]
    if not cards:  # no keyword matched anything; fall back to recent posts
        cards = [c for c in company_posts(name, limit=60)["posts"] if not _is_junk(c)]

    def score(card: dict[str, Any]) -> int:
        title = set(_keywords(card.get("title") or ""))
        preview = set(_keywords(card.get("preview") or ""))
        base = 3 * len(words & title) + len(words & preview)
        return base + (2 if base and card.get("_specific") else 0)

    ranked = sorted(cards, key=score, reverse=True)
    chosen = [c for c in ranked if score(c) > 0][:max_posts] or ranked[:max_posts]

    threads = []
    for card in chosen:
        card.pop("_specific", None)
        thread = read_post(card["url"])
        thread["matched_keyword"] = card.get("matched_keyword")
        # The answer is usually a quiet reply, not the top-voted one.
        thread["key_comments"] = _rank_comments(thread["comments"], words, 6)
        del thread["comments"]
        threads.append(thread)

    return {
        "company": name,
        "question": question,
        "keywords_tried": tried,
        "considered": len(cards),
        "threads": threads,
        "note": (
            "Blind is anonymous and unverified. Weigh claims by the commenter's "
            "employer and corroborate anything load-bearing. Check thread dates "
            "-- policy answers go stale."
        ),
    }



# ---------------------------------------------------------------- pay ranges


def _dominant(postings: list[dict[str, Any]], field: str) -> str | None:
    counts: dict[str, int] = {}
    for p in postings:
        if p.get("pay"):
            counts[p["pay"][field]] = counts.get(p["pay"][field], 0) + 1
    return max(counts, key=counts.get) if counts else None


def _dominant_currency(postings: list[dict[str, Any]]) -> str | None:
    return _dominant(postings, "currency")


def _dominant_interval(postings: list[dict[str, Any]]) -> str | None:
    """The modal interval among postings that actually state one.

    A posting that declines to state its period must not outvote one that
    states it. Some boards publish a band with the period field set to "not
    available", and counting those as a category of their own means the
    better-attested postings lose the election and are then filtered out --
    silently, because they are not missing a range, just a unit.
    """
    stated = [p for p in postings if p.get("pay") and p["pay"].get("interval")]
    return _dominant(stated, "interval") if stated else None


def _by_market(
    priced: list[dict[str, Any]], base: str | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """The same role at the same employer, in each currency it is posted in.

    An employer subject to pay-transparency law in one market often posts the
    same job in several. Anthropic advertises a software engineer band in USD,
    GBP and EUR; reading only the dominant currency threw two of those away.
    Ratios between them are the closest thing to a published answer for what
    the same job is worth in a market that requires no disclosure at all.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for p in priced:
        groups.setdefault(p["pay"]["currency"], []).append(p)

    table = fx.rates(base, ats.USER_AGENT) if base and len(groups) > 1 else None
    out = []
    for currency, rows in groups.items():
        summary = levels.summarise(rows)
        if not summary:
            continue
        entry = {
            "currency": currency,
            "postings": len(rows),
            "typical": summary["typical"],
            "distinct_bands": summary["distinct_bands"],
            "locations": sorted({r["location"] for r in rows if r["location"]})[:5],
        }
        # No table means no conversion happened, so emit no converted field
        # -- an unconverted figure relabelled as the base currency would read
        # as a comparison that was never made.
        low = fx.convert(summary["typical"]["min"], currency, base, table) if table else None
        high = fx.convert(summary["typical"]["max"], currency, base, table) if table else None
        if low and high:
            # The published figure stays; this is the estimate beside it.
            entry[f"typical_in_{base}"] = {"min": round(low), "max": round(high)}
        out.append(entry)

    out.sort(key=lambda r: r["postings"], reverse=True)
    if out and table:
        anchor = out[0].get(f"typical_in_{base}") or out[0]["typical"]
        pivot = (anchor["min"] + anchor["max"]) / 2
        for entry in out[1:]:
            converted = entry.get(f"typical_in_{base}")
            if converted and pivot:
                entry["vs_largest_market"] = round(
                    (converted["min"] + converted["max"]) / 2 / pivot, 2
                )
    meta = {
        "base": base,
        "rate_date": table.get("date"),
        "source": "ECB daily reference rates via frankfurter.dev",
        "caveat": (
            "Converted figures are an estimate on the rate date; the published "
            "figure in its own currency is the fact. Neither adjusts for cost "
            "of living or tax."
        ),
    } if table else None
    return out, meta


def _level_breakdown(postings: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for p in postings:
        buckets.setdefault(levels.classify(p["title"]), []).append(p)
    by_level = {
        lvl: levels.summarise(rows)
        for lvl in levels.ORDER
        if (rows := buckets.get(lvl)) and levels.summarise(rows)
    }
    return by_level


@mcp.tool()
def job_openings(
    company: str, role: str = "", with_pay_only: bool = False,
    limit: int = 25, board: str = "",
) -> dict[str, Any]:
    """List a company's open roles, with the pay range where one is published.

    Reads the company's public job-board API (Greenhouse, Ashby, Lever,
    SmartRecruiters, Keka or Workday).
    `role` filters to titles containing every word you give, so "forward
    deployed" matches "AI Engineer - FDE (Forward Deployed Engineer)".

    Not every employer is reachable: Google, Meta, Amazon and Apple self-host
    their careers sites and are not on these boards. Workday tenants (NVIDIA,
    Salesforce, Adobe, Cisco, HPE) are, and are found from the company name.
    Keka tenants are rarely the company name; read the tenant from
    `<tenant>.keka.com/careers` and pass `board="keka:<tenant>"`.
    """
    board, postings = ats.fetch_postings(company, board or None, role=role)
    hits = ats.matching(postings, role) if role else postings
    # Only the postings about to be returned are worth a second request.
    ats.enrich_pay(hits[: limit if not with_pay_only else limit * 3])
    if with_pay_only:
        hits = [p for p in hits if p["pay"]]
    for p in hits[:limit]:
        p["level"] = levels.classify(p["title"])
        p.pop("_detail", None)
    return {
        "company": company,
        "board": board,
        "total_open_roles": len(postings),
        "matched": len(hits),
        "with_published_pay": sum(1 for p in hits if p["pay"]),
        "postings": hits[:limit],
    }


@mcp.tool()
def pay_bands(
    company: str, role: str, board: str = "", max_lookups: int = 40
) -> dict[str, Any]:
    """What a role pays at one company, broken down by seniority.

    Colorado, California, New York, Washington and Illinois require a salary
    range on covered postings; India, Singapore and most of the EU require
    none. So the same title at the same company carries a band in Denver and
    nothing in Bengaluru, and the published one is the best available anchor
    for the silent one -- same employer, same title, same week.

    Bands are reported per level, because a single range across seniorities is
    a number nobody is offered: "forward deployed" at Databricks spans
    140,400-320,200 undivided, but resolves into a mid band, a senior band
    carried by 48 postings, and several management bands.

    `typical` is the modal band -- the one the most postings carry -- and is
    usually what you want. `distinct_bands` versus `postings` shows how much
    independent evidence there is: 48 postings sharing one band is one data
    point advertised 48 times, not 48 data points.
    """
    board, postings = ats.fetch_postings(company, board or None, role=role)
    hits = ats.matching(postings, role)
    # Workday keeps the range inside each description. Fetch those now that
    # the list is down to the postings this question is actually about.
    ats.enrich_pay(hits, limit=max_lookups)
    if not hits:
        return {
            "company": company, "board": board, "role": role, "matched": 0,
            "note": f"No open title contains all of {role!r}.",
            "sample_titles": sorted({p["title"] for p in postings})[:12],
        }

    # On-target earnings are base plus commission. A sales role's OTE in the
    # same band as an engineer's base overstates what the job pays in salary,
    # so it is reported separately rather than averaged in.
    on_target = [p for p in hits if p["pay"] and p["pay"].get("basis") == "ote"]
    base_pay = [p for p in hits if not (p["pay"] and p["pay"].get("basis") == "ote")]

    currency = _dominant_currency(base_pay)
    same_currency = [
        p for p in base_pay if p["pay"] and p["pay"]["currency"] == currency
    ]
    # An hourly contract rate averaged into a band of annual salaries produces
    # a number that is wrong rather than merely imprecise, so the two never mix.
    # Only postings that state a period vote on what it is -- see
    # _dominant_interval. market_rate applies the same rule.
    interval = _dominant_interval(same_currency)
    priced = [p for p in same_currency if p["pay"]["interval"] == interval]
    # Counted rather than quietly dropped, for the reason not_checked_count
    # exists: a posting left out of the band is a fact about our reading of it.
    # Empty when nothing states an interval, because then they are the band.
    unstated = (
        [p for p in same_currency if p["pay"]["interval"] is None]
        if interval is not None
        else []
    )
    silent = [p for p in base_pay if not p["pay"] and p.get("pay_known", True)]
    # Boards that hide pay behind a second request are only checked up to
    # max_lookups. Counting the rest as "publishes nothing" would be a claim
    # about the employer that we never actually tested.
    unchecked = [p for p in base_pay if not p["pay"] and not p.get("pay_known", True)]
    other_cur = sorted({
        p["pay"]["currency"] for p in base_pay
        if p["pay"] and p["pay"]["currency"] != currency
    })
    # None is excluded here as well as being counted separately: it is not an
    # "other interval", and sorting it against strings raises outright.
    other_int = sorted({
        p["pay"]["interval"] for p in same_currency
        if p["pay"]["interval"] is not None and p["pay"]["interval"] != interval
    })

    by_level = _level_breakdown(priced)
    markets, fx_meta = _by_market(
        [p for p in base_pay if p["pay"] and p["pay"]["interval"] == interval],
        currency,
    )
    return {
        "company": company,
        "board": board,
        "role": role,
        "matched": len(hits),
        "currency": currency,
        "interval": interval,
        "by_level": by_level,
        "markets": markets,
        "fx": fx_meta,
        "band_width_ratio": levels.band_width_ratio(by_level.values()),
        "level_steps": levels.level_steps(by_level),
        "other_currencies_present": other_cur,
        "other_intervals_present": other_int,
        "publishes_no_range": [
            {"title": p["title"], "level": levels.classify(p["title"]),
             "location": p["location"], "url": p["url"]}
            for p in silent[:15]
        ],
        "no_range_count": len(silent),
        "not_checked_count": len(unchecked),
        # Published a band, did not say what period it covers. Left out of the
        # figures above rather than assumed annual, and counted here so that
        # leaving them out is visible instead of silent.
        "interval_unstated_count": len(unstated),
        "on_target_earnings_excluded": [
            {"title": p["title"], "published": p["pay"]["min"],
             "currency": p["pay"]["currency"], "url": p["url"]}
            for p in on_target[:5]
        ],
        "note": (
            f"{len(priced)} of {len(hits)} matching postings publish a {interval}ly "
            f"range in {currency}. `by_level` covers that currency only; "
            f"`markets` shows every currency this role is posted in, which is "
            f"the like-for-like way to compare countries -- same employer, same "
            f"title, same week. Figures do not convert at face value; "
            f"`level_steps` and market ratios travel better than absolutes. "
            f"Seniority is inferred from the title -- check `titles` on each "
            f"level, since role names like 'Engagement Manager' can read as "
            f"management when they are not. Check `precision` before relying "
            f"on a band: 'wide' means the employer published one range across "
            f"several levels and it narrows little."
            + (
                f" {len(unchecked)} further matching postings were not checked, "
                f"because this board stores the range inside each posting and "
                f"the lookup budget is {max_lookups}; raise max_lookups to "
                f"include them. They are not counted as publishing nothing."
                if unchecked else ""
            )
        ),
    }


@mcp.tool()
def market_rate(
    role: str, companies: list[str], level: str = ""
) -> dict[str, Any]:
    """Compare what a role pays across several companies at the same seniority.

    One company's band tells you what that company pays; several tell you
    whether an offer is competitive. Pass `level` (mid, senior, staff, lead,
    principal, manager, senior_manager, director) to compare like with like --
    without it, each company's largest band is used, which may not be the
    same rung.

    Rows are sorted by what each band is worth in one currency, not by its
    raw number: a Polish band of 340,000 PLN outranks a US one of 187,200 USD
    numerically and is worth about half. Each row keeps its published figure
    and carries the converted one beside it.

    Companies on none of the supported boards are listed under `unreachable`
    rather than silently dropped. This is also the fallback when the company
    you actually care about is one of those: Google, Meta, Amazon and Apple
    publish nothing readable, but the employers competing for the same people
    do, and that is the band those offers are set against.
    """
    # Two passes: what each employer publishes, then which period the table is
    # in, then each employer's band in that period. The period cannot be
    # chosen per company, because it depends on what every other company
    # published.
    candidates: dict[str, tuple[str | None, dict[Any, tuple[str, dict[str, Any]]]]] = {}
    unreachable: list[dict[str, Any]] = []
    for company in companies[:12]:
        try:
            board, postings = ats.fetch_postings(company, role=role)
        except Exception as exc:
            unreachable.append({"company": company, "reason": type(exc).__name__})
            continue
        hits = ats.matching(postings, role)
        ats.enrich_pay(hits, limit=25)
        hits = [p for p in hits if not (p["pay"] and p["pay"].get("basis") == "ote")]
        currency = _dominant_currency(hits)
        # Fix the unit as well as the currency. An hourly contract rate in the
        # same band as annual salaries does not merely widen it -- the modal
        # band can land on the hourly pair, and the tool then states a senior
        # engineer band of "95 - 130".
        # A band per period this employer publishes on, rather than one band
        # from its own modal period. Choosing here -- before the table's
        # period is known -- locks an employer to whichever unit it happens to
        # post most often, and an employer with two contract postings and one
        # salaried one is then set aside as "hourly" while holding the annual
        # band every other row is being compared on.
        #
        # Exact match per period, never a fallback. Sweeping postings that
        # state no period into a stated one is the silent assumption this
        # whole guard exists to prevent, so None is its own group.
        per_period: dict[Any, tuple[str, dict[str, Any]]] = {}
        for unit in {p["pay"].get("interval") for p in hits
                     if p["pay"] and p["pay"]["currency"] == currency}:
            at_unit = [
                p for p in hits
                if p["pay"]
                and p["pay"]["currency"] == currency
                and p["pay"].get("interval") == unit
            ]
            by_level = _level_breakdown(at_unit)
            if not by_level:
                continue
            chosen = level if level and level in by_level else max(
                by_level, key=lambda k: by_level[k]["postings"]
            )
            per_period[unit] = (chosen, by_level[chosen])
        if not per_period:
            unreachable.append({"company": company, "reason": "no published range"})
            continue
        candidates[company] = (currency, per_period)

    # A currency can be converted. A unit cannot: 200,000 per year and 130 per
    # hour have no exchange rate between them, and ranking them in one list
    # would state an ordering that does not exist. So rank within one unit and
    # report the rest beside it, rather than merging or discarding them.
    #
    # Ties break toward the longer period, which is a preference and not a
    # coin toss: an employer posting the same title salaried and as a contract
    # rate has published two different things, and the salaried one is what
    # "what does this role pay" is asking about. It is also stable, where
    # picking the larger of a set is not and the period would silently change
    # between runs.
    _LONGEST_FIRST = ("year", "two_weeks", "month", "week", "day", "hour")
    votes = [u for _, per in candidates.values() for u in per if u is not None]
    period = min(
        set(votes),
        key=lambda u: (
            -votes.count(u),
            _LONGEST_FIRST.index(u) if u in _LONGEST_FIRST else len(_LONGEST_FIRST),
            u,
        ),
    ) if votes else None

    rows, other_period = [], []
    for company, (currency, per_period) in candidates.items():
        unit = period if period in per_period else sorted(
            per_period, key=lambda u: (u is None, str(u))
        )[0]
        chosen, band = per_period[unit]
        row = {
            "company": company,
            "level": chosen,
            "typical": band["typical"],
            "currency": currency,
            # Without this a caller cannot tell 200,000/year from 130/hour,
            # and the two sort into one list as though they were comparable.
            "interval": unit,
            # This employer publishes the same title on another period too.
            # Saying so keeps "we chose one" distinct from "there was only one".
            "other_intervals_present": sorted(
                u for u in per_period if u is not None and u != unit
            ),
            "postings": band["postings"],
            "distinct_bands": band["distinct_bands"],
            "example_titles": band["titles"][:3],
            "matched_requested_level": bool(level) and chosen == level,
        }
        (rows if unit == period else other_period).append(row)
    ranked = rows

    # Sorting mixed currencies by their raw numbers ranks by exchange rate
    # rather than by pay, so convert to whichever currency most rows use.
    # Ties are broken towards USD and then alphabetically, because picking the
    # larger of a set is not stable between runs and the base currency would
    # silently change.
    present = {r["currency"] for r in ranked}
    base = sorted(
        present,
        key=lambda c: (-sum(r["currency"] == c for r in ranked), c != "USD", c),
    )[0] if present else None
    table = fx.rates(base, ats.USER_AGENT) if base and len(present) > 1 else None
    for row in ranked:
        low = fx.convert(row["typical"]["min"], row["currency"], base, table) if table else None
        high = fx.convert(row["typical"]["max"], row["currency"], base, table) if table else None
        if low and high:
            row[f"typical_in_{base}"] = {"min": round(low), "max": round(high)}
        converted = row.get(f"typical_in_{base}") or row["typical"]
        row["_rank"] = (converted["min"] + converted["max"]) / 2
    ranked.sort(key=lambda r: r.pop("_rank"), reverse=True)
    rows = ranked

    mixed = sorted({r["currency"] for r in rows})
    return {
        "role": role,
        "level_requested": level or None,
        "compared": len(rows),
        "rates": rows,
        "fx": {
            "base": base,
            "rate_date": table.get("date"),
            "source": "ECB daily reference rates via frankfurter.dev",
        } if table else None,
        "currencies_compared": mixed,
        "interval": period,
        # Not ranked with the rest: there is no conversion between an hourly
        # rate and an annual salary, so these are reported rather than merged.
        "other_intervals": [
            {"company": r["company"], "level": r["level"], "interval": r["interval"],
             "typical": r["typical"], "currency": r["currency"]}
            for r in other_period
        ],
        "unreachable": unreachable,
        "note": (
            f"Sorted by band midpoint among companies publishing a {period or 'comparable'} "
            "rate, converted to a common currency where the rows use more than "
            "one -- an unconverted ranking would order by exchange rate rather "
            "than by pay. Companies publishing a different unit are listed "
            "under other_intervals rather than ranked, because no rate converts "
            "an hourly figure into an annual one. Rows where "
            "matched_requested_level is false fell back to the company's "
            "largest band and may be a different rung -- read `level` before "
            "comparing them."
        ),
    }


def main() -> None:
    """stdio by default; --http serves a long-lived process for pm2 et al.

    stdio servers are spawned per client and talk over stdin/stdout, so there
    is nothing for a process supervisor to keep alive. --http gives one
    persistent endpoint that any number of clients can connect to.
    """
    parser = argparse.ArgumentParser(prog="payband-mcp")
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="serve over streamable HTTP instead of stdio",
    )
    parser.add_argument("--host", default=http.env("HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(http.env("PORT", "8787"))
    )
    args = parser.parse_args()

    if not BLIND_ENABLED:
        print(
            "payband-mcp: Blind tools are not registered -- Blind returns 403 to "
            "automated requests (see issue #12). The pay tools are unaffected. "
            "Set PAYBAND_ENABLE_BLIND=1 to register them anyway.",
            file=sys.stderr,
        )

    if not args.http:
        mcp.run()
        return

    # Stateless: clients reconnect freely across pm2 restarts without the
    # server having to remember a session that died with the old process.
    mcp.run(
        "streamable-http",
        host=args.host,
        port=args.port,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
