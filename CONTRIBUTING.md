# Contributing

Three ways in, cheapest first: a **job-board adapter**, a **parser fix**, a
**new tool**. All are small — this is a ~600 line project.

**Read [#12](https://github.com/dheerajjha/payband-mcp/issues/12) first.** Blind
now 403s every non-browser User-Agent, so the Blind tools cannot reach the site.
We will not spoof a browser to get around it, and PRs doing so will be closed.
The pay tools read public job-board APIs and are unaffected — that is where the
useful work is right now.

**The standing principle behind everything below: a wrong answer is worse than
no answer.** People ask this server whether a company will let them work from
home, how long their parental leave is, whether a team is worth joining — and
then act on it. A thread that looks relevant but isn't costs someone a real
decision; returning nothing costs them one search. So `find` returns an empty
list rather than falling back to a generic listing, `research` would rather
surface two good threads than pad to four, and every comment keeps its
**employer tag and date**, because that is how a reader weighs an anonymous
claim. If you are ever choosing between "more results" and "results the user
can trust", pick trust.

**The second principle: stay welcome.** This server reads a site that does not
owe us access. It honours `robots.txt` and fails closed if it can't read it, it
caches for six hours, it throttles to ~1.5s, and it sends an honest User-Agent
instead of impersonating a browser. It has **no `/search/` tool**, because
Blind disallows that path for every user-agent. A PR that speeds things up by
weakening any of those will not be merged, however much faster it is. Bulk
crawling is out of scope permanently.

**On AI-assisted contributions.** Plenty of this repo was written with AI help,
including the maintainer's. That's fine and you don't need to disclose it. What
isn't optional: a human has read the change and can answer questions about it.
Reviews here lean on *running the thing* — a claim like "this improves ranking"
gets checked against real output before merge.

**Review promise:** first review within 48 hours. An alias merges as soon as it
has a passing test. No bikeshedding your regex.

## 1. Add a job-board adapter (an hour, and the most useful thing you can do)

`ats.fetch_postings` reads Greenhouse, Ashby, Lever, SmartRecruiters and
Workday. Self-hosted employers — Google, Atlassian, Canva and many Indian
employers — still raise `BoardNotFound`. Each adapter you add is a whole
category of employer the tool can suddenly answer for. See
[#13](https://github.com/dheerajjha/payband-mcp/issues/13) for the candidates
and the shape of the work.

Prefer boards with a **documented public API**. If a board only yields to
scraping, keep it clearly separate so its breakage cannot affect the API-backed
paths.

## 2. Teach the pay parser a shape it cannot read (30 minutes)

[`money.py`](src/payband_mcp/money.py) turns posting text into a band, and
employers write money in more ways than you would believe. It has had to learn
`184,000 USD - 287,500 USD` (code trailing, no symbol), `65.000 - 90.000 EUR`
(dots as thousands), `₹25,00,000` (Indian grouping), `£150, 000` (typed with a
stray space), and `Zone A: $122,400 - $159,800` (label leading, three zones per
posting).

If you find a published range it returns `None` for, that is a bug worth
fixing. Add the shape to the table in
[`tests/test_money.py`](tests/test_money.py) and make it pass.

**Two things matter more than reading the shape.** A figure that is not salary
must stay refused — `£1,000 learning budget` and `we raised $50M - $80M` both
sit near salary text in real postings. And things that are not the same must
not merge: three geographic zones, or an OTE next to a base, are separate
bands, not one wide one. Every serious bug this project has had was a number
that looked authoritative and was not.

> The previous version of this section asked for **keyword aliases** for the
> `research` tool. That tool reads Blind, which has refused automated requests
> since around September 2026 (#12), so it is no longer registered by default.
> The work would have shipped dormant.

Include the posting you found it in, so the shape can be checked against a
real employer rather than a hypothetical.

## 3. Fix a parser (an hour)

Blind ships three overlapping copies of every post — plain HTML, a schema.org
`DiscussionForumPosting`, and the Next.js RSC payload. We read the last two;
see [`src/payband_mcp/parse.py`](src/payband_mcp/parse.py).

Fixtures are **synthetic** — see
[`tests/fixtures/make_fixtures.py`](tests/fixtures/make_fixtures.py). Do not
commit captured pages. Blind posts are written by anonymous people and
routinely name colleagues; a real thread in this repo republishes that
permanently, and contradicts what we tell users not to do. Extend the generator
instead: it is plain Python and reproduces the structural quirks that matter
(replies that also match the comment regex, a `commentCount` higher than the
schema list, an AI `abstract`).

```bash
uv run python tests/fixtures/make_fixtures.py
uv run pytest -q
```

## 4. Add a tool (an afternoon)

Tools live in [`src/payband_mcp/server.py`](src/payband_mcp/server.py) as
`@mcp.tool()` functions. A tool earns its place if it answers a question the
existing four answer badly. Write the docstring for the model that will read
it: say when to use it, and say what an empty result means.

Every request must go through `http.fetch` — that is where robots, caching and
throttling live. A tool that calls `httpx` directly bypasses all three.

## Setup

```bash
uv sync
uv run pytest -q          # 143 tests, all offline
uv run payband-mcp          # stdio, for an MCP client
uv run payband-mcp --http   # HTTP on :8787, for pm2
```

Tests never touch the network. If you need to check something against the real
site, do it in a scratch script, not a test.
