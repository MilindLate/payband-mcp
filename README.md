# payband-mcp

[![tests](https://github.com/dheerajjha/payband-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/dheerajjha/payband-mcp/actions/workflows/test.yml)
[![good first issues](https://img.shields.io/github/issues/dheerajjha/payband-mcp/good%20first%20issue?label=good%20first%20issues&color=7057ff)](https://github.com/dheerajjha/payband-mcp/issues?q=is%3Aopen+label%3A%22good+first+issue%22)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://github.com/dheerajjha/payband-mcp/blob/main/pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green)](https://github.com/dheerajjha/payband-mcp/blob/main/LICENSE)

**Find out what a role actually pays — including in markets where the employer
publishes nothing.**

> Renamed from `blind-mcp` in 0.5.0. The Blind tools are still here (see
> [below](#culture--not-registered-by-default)), but reading published pay
> bands is what this does, so the name now says so. The old GitHub URL
> redirects; the old PyPI package points here. `BLIND_MCP_*` environment
> variables still work — `PAYBAND_*` is preferred.

Colorado, California, New York, Washington and Illinois require a salary range
on covered job postings. India, Singapore and most of the EU require none. So
the same title, at the same company, in the same week, is posted with a band in
Denver and without one in Bengaluru.

The band is still there. It is just attached to a different listing.

```
pay_bands(company="Databricks", role="forward deployed")

  101 matching openings · band width ratio x1.37 · 33 publish no range

  LEVEL            TYPICAL BAND        BANDS  POSTS  PRECISION
  mid              152,900–210,155         2      3  tight
  senior           182,000–250,208         1     58  tight
  lead             178,800–245,850         1      1  tight
  manager          211,800–291,300         4      5  tight
  senior_manager   232,900–320,200         1      1  tight

  steps: mid→senior +19.1% · lead→manager +18.5% · manager→sr_mgr +9.9%
  silent: Remote-India, Seoul, London, Berlin, Amsterdam
```

Per level, because one range across seniorities is a number nobody is
offered — undivided, that role reads as `140,400–320,200`, a 2.3x spread
covering five different jobs.

`typical` is the modal band. **`distinct_bands` vs `postings` is the honest
measure of evidence**: 58 postings sharing one band is one data point
advertised 58 times. `precision` flags how much a band actually narrows
things — Databricks posts tight per-level bands, Figma posts a single x2.5
band spanning its whole ladder, and both are real.


That is the same employer, the same title, the same moment — a far better
anchor for an unpublished number than any salary survey, and it takes one call.

### The same job, in every market the employer posts it in

Employers covered by transparency law in one country often post the same role
in several. That is the closest thing to a controlled experiment you can get:
same company, same title, same week.

```
pay_bands(company="Anthropic", role="software engineer")

  MARKET   PUBLISHED BAND            POSTS   ≈ IN USD              vs US
  USD      405,000–485,000              78   —                     —
  GBP      325,000–390,000              10   438,206–525,847       1.08x
  EUR      235,000–295,000               2   271,165–340,399       0.69x

  fx: ECB daily reference rates, 2026-09-15
```

The published figure is always kept; the conversion sits beside it, dated.
Without it the comparison misleads — GitLab's Polish band reads as
`272,000–408,000` against a US `139,200–235,200`, which looks like Poland
paying more and is actually **0.48x**.

Reads the **public job-board APIs** — Greenhouse, Ashby, Lever,
SmartRecruiters and Workday — plus a small number of employers who run their
own endpoint. Documented, intended for machines, and stable — not scraping.

## Tools

### Pay

| Tool | What it does |
| --- | --- |
| `pay_bands(company, role, board=, max_lookups=)` | Published bands per seniority, plus every currency the role is posted in, converted |
| `market_rate(role, companies, level=)` | The same rung across several employers, sorted by midpoint |
| `job_openings(company, role=, with_pay_only=)` | The underlying postings, with inferred level |

### Culture — not registered by default

| Tool | What it does |
| --- | --- |
| `find(company, keyword, limit=, page=)` | Search a company's [Blind](https://www.teamblind.com) posts by keyword |
| `research(company, question, max_posts=)` | Pick the topic, rank threads against the question, return them in full |
| `company_topics` / `company_posts` / `read_post` | Listings and single threads |

These five are **switched off unless you ask for them** (`PAYBAND_ENABLE_BLIND=1`).
A tool list is part of what a model reads before deciding what to do, and five
entries that can currently only raise cost context and invite dead ends. The
code and its tests are untouched, so the flag brings them straight back.

> ⚠️ **Blind began returning 403 to all automated requests around September 2026.**
> This is site-wide bot protection, not a block on this project: `curl` and an
> empty User-Agent are refused too, and only a browser User-Agent gets through.
> `robots.txt` still permits `/company/`, but the WAF does not.
>
> We do not spoof a browser to get around it — that would be circumventing an
> access control, and it is the first thing their next escalation defeats. The
> Blind tools now raise `BlindBlocked` with an explanation rather than
> returning empty results that would read as "no discussion found".
>
> The pay tools are unaffected. See [#12](https://github.com/dheerajjha/payband-mcp/issues/12).

## Coverage

Measured, not estimated:

| Company | Board | Open roles | With a published range |
| --- | --- | --- | --- |
| Company | Board | Open roles | With a published range | Currencies |
| --- | --- | --- | --- | --- |
| Databricks | Greenhouse | 880 | 471 (54%) | USD 451 · CAD 12 · EUR 8 |
| Anthropic | Greenhouse | 595 | 525 (88%) | USD 466 · GBP 44 · EUR 14 |
| Ramp | Ashby | 148 | 141 (95%) | USD 132 · CAD 6 · GBP 2 |
| Monzo | Greenhouse | 66 | 55 (83%) | GBP 47 · EUR 8 |
| Notion | Ashby | 127 | 83 (65%) | USD 71 · EUR 12 |
| Figma | Greenhouse | 156 | 101 (65%) | USD 101 |
| GitLab | Greenhouse | 224 | 94 (42%) | USD 85 · PLN 9 |
| Stripe | Greenhouse | 648 | 22 (3%) | USD 21 · EUR 1 |
| Freshworks | SmartRecruiters | 139 | on demand | USD |
| NVIDIA | Workday | 1,693 | on demand | USD, level-labelled |
| Cisco · Adobe · Salesforce · HPE · eBay | Workday | — | on demand | — |
| Atlassian | self-hosted | 287 | 122 (43%) | USD 119 · CAD 3 |

SmartRecruiters and Workday say **on demand** because they keep the range
inside each posting rather than in the listing. Postings are filtered by title
first and only the survivors are fetched, so a question about NVIDIA costs
about forty requests instead of 1,693. `max_lookups` sets that budget, and
anything beyond it is reported as `not_checked_count` — never as the employer
publishing nothing.

Workday tenants are found by reading their `robots.txt`, which names the
public career site in its `Sitemap` line. If the tenant differs from the
company name, paste the careers URL or pass
`board="workday:<tenant>/<site>"`.

SmartRecruiters company ids come from
`careers.smartrecruiters.com/<company-id>` and are also guessed from the
company name. Pass `board="smartrecruiters:<company-id>"` when they differ.

Atlassian self-hosts and is reached by name, through its own endpoint. Its US
roles publish three geographic zones (`Zone A/B/C`), which are reported as
separate bands rather than collapsed — their union spans 1.6x and is nobody's
offer.

**Not covered:** Google, Meta, Amazon and Apple, and most Indian-headquartered
companies. Amazon and Netflix were probed and both serve clean JSON with no
pay in it at all — their ranges exist only in rendered HTML. Apple answers 401. `BoardNotFound` explains the causes
rather than just failing.

If a company *is* on one of these boards under a token you can't guess, read
it out of their careers URL and pass it directly:

```
pay_bands("Some Rebranded Co", "engineer", board="greenhouse:theirslug")
```

Self-hosted Indian employers are still open in
[#13](https://github.com/dheerajjha/payband-mcp/issues/13).

## Install

```bash
uv sync
```

Register with Claude Code:

```bash
uv tool install --editable .          # puts `payband-mcp` on PATH
claude mcp add --scope user payband -- payband-mcp
```

Or in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "payband": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/payband-mcp", "payband-mcp"]
    }
  }
}
```

## Do I need to log in?

**No — and you probably shouldn't.** This was measured, not assumed:

- Post bodies, full comment threads, Blind's AI comment summaries, company
  listings, topic pages, reviews and salary pages **all return HTTP 200
  anonymously**, with no gating.
- Driving an authenticated session with automation tripped Blind's anomaly
  detection after roughly six navigations: `Automatic Logout — we noticed a
  login from a new device or location (code 2009)`, with a redirect to
  `/session-out`.

So a cookie buys no extra read access and costs you session stability. The only
thing it would unlock is company-internal channels, which are gated to verified
employees of that company.

If you still want it, set `BLIND_COOKIE` to your session cookie header (copy it
from a logged-in browser request in DevTools). There is no login flow — the
server only replays a cookie you supply, read once at startup and attached to
each request. It is off by default, and the client raises immediately if Blind
invalidates it rather than silently returning logged-out HTML.

The cookie itself is never written to disk, but responses fetched with it are
cached under a separate `auth/` directory so authenticated and anonymous
results can never be served for each other. Don't commit the cookie.

## Being a good citizen

Blind's `robots.txt` disallows `/search/` for every user-agent, so **this server
has no search tool** and refuses to fetch that path. It also:

- sends an honest `User-Agent` (no browser impersonation — Blind serves it a 200 anyway)
- caches every response on disk for 6h, so repeat questions cost zero requests
- spaces requests ~1.5s apart
- fetches `robots.txt` first and fails closed if it can't be read

Configure via `PAYBAND_CACHE_DIR`, `PAYBAND_CACHE_TTL`,
`PAYBAND_MIN_INTERVAL`, `PAYBAND_USER_AGENT`.

The job boards get the same treatment. SmartRecruiters and Workday need one
request per posting to read a range, so those are spaced 250ms apart behind a
lock shared by all four workers — the workers overlap the board's latency
without ever raising the rate we ask at — and the number of lookups is capped
per question. Workday site discovery reads `robots.txt` and takes its word for
what is public, including never treating a `Disallow`ed path as a career site.
Exchange rates are cached for a day, because the ECB publishes them once a
working day.

Blind's Terms of Service restrict automated access. This reads public pages at
human pace for personal research; bulk crawling is both a ToS problem and, given
that Blind's value rests on anonymity, a privacy one. Don't build a dataset of
posts joined to employers and nicknames.

## Reading the output

Four things the output says that are easy to skim past:

- **`distinct_bands` vs `postings`** — 58 postings sharing one band is one data
  point advertised 58 times.
- **`precision`** — `wide` means the employer published one range across
  several levels, so it narrows almost nothing.
- **`not_checked_count`** — postings whose range we did not look at, kept
  apart from ones the employer genuinely left blank. Raise `max_lookups`.
- **`on_target_earnings_excluded`** — sales roles often publish OTE, which is
  base plus commission. Those are reported separately, never averaged into a
  base band.

Converted figures are estimates on a dated exchange rate, and adjust for
neither cost of living nor tax. The published figure in its own currency is
the fact; the conversion is there so the comparison is not nonsense.

Blind is anonymous and unverified. Weight claims by the commenter's employer
(`company` on each comment) and treat a single loud voice as one data point. In
testing, the Roku India RTO answer was corroborated by two independent
commenters *and* an unrelated Glassdoor review — that's when it's worth trusting.

## Contributing

Small project, easy to contribute to. The most useful change is **a board we
can't reach yet** — each adapter is a whole category of employer the tool can
suddenly answer for, and two of the last three releases were built by outside
contributors doing exactly that. Non-US employers most of all, since markets
that publish nothing are the whole point.

Next most useful: **a band that's wrong.** A number that looks authoritative and
isn't is the worst failure this project has, and every serious bug so far has
been one. Those get priority over new coverage.

Maintainers: see [MAINTAINING.md](MAINTAINING.md).

Start with [**good first issues**](https://github.com/dheerajjha/payband-mcp/blob/main/.github/GOOD_FIRST_ISSUES.md), then
[CONTRIBUTING.md](https://github.com/dheerajjha/payband-mcp/blob/main/CONTRIBUTING.md). Issues are labelled by size (`size: XS`
is under 30 minutes) and `mentored` means ask questions in the thread and
you'll get walked through it. Claim one in a comment, so nobody else starts on it.
First review within 48 hours — reviewed by running it, not just reading it.

Two hard rules, both explained in CONTRIBUTING: **don't commit captured Blind
pages** (fixtures are generated), and **don't weaken robots/cache/throttle** for
speed.

## Publishing

`mcp-name: io.github.dheerajjha/payband-mcp`

See [RELEASING.md](https://github.com/dheerajjha/payband-mcp/blob/main/RELEASING.md).

## License

MIT
