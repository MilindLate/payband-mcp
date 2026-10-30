# Changelog

Notable changes per release. Dates are UTC.

## 0.12.1 — 2026-10-30

- **Board slugs fold accented letters to plain ASCII.**
  ([#43](https://github.com/dheerajjha/payband-mcp/pull/43), from @MilindLate)
  - Job boards spell their slugs in ASCII, so "Ørsted" now tries `orsted`,
    "Mærsk" `maersk`, "Straße AG" `strasse` and "Łukasiewicz" `lukasiewicz`.
    Letters that Unicode normalization can't decompose (ø, æ, œ, ß, ł, đ, ð,
    þ, ı) go through a small table first.
  - The fold happens before the legal-suffix match, and the self-hosted
    employer lookup uses it too.
- **Three more legal suffixes come off board slugs.**
  ([#46](https://github.com/dheerajjha/payband-mcp/pull/46), from @MilindLate)
  - Danish and Norwegian `A/S` and `AS`, Icelandic `ehf` and South Slavic
    `d.o.o.`: "Novo Nordisk A/S" now tries `novonordisk` first. A name that
    merely ends in "as", such as "Atlas", is unchanged.
- **The lockfile picks up two security fixes:** certifi 2026.10.18
  (GHSA-6q48-6c7w-9gw2, #48) and opentelemetry-api 1.45.1
  (GHSA-xcq7-p3pf-p88h, #47). Both arrive through dependencies whose ranges
  already allowed the fixed versions, so a fresh install had them before this
  release.

## 0.12.0 — 2026-10-19

- **SmartRecruiters and Workday pass the posting's location to the pay
  parser.** ([#23](https://github.com/dheerajjha/payband-mcp/issues/23),
  [#41](https://github.com/dheerajjha/payband-mcp/pull/41), from
  @Rayan-and-beyond)
  - 0.11.0 taught the parser to read a bare `$` against the posting's
    location. These two adapters fetch pay in a separate request and passed
    no location, so a Toronto posting's `$120,000 - $150,000` still read as
    USD there.
  - Both now pass it. SmartRecruiters builds it the way its listing already
    did: `fullLocation`, otherwise city, region and country.
- **`board_slugs` tries the name without one trailing legal suffix first.**
  ([#38](https://github.com/dheerajjha/payband-mcp/issues/38),
  [#45](https://github.com/dheerajjha/payband-mcp/pull/45), from
  @subhrajeetshaw008-bit)
  - "Toast, Inc." now tries `toast` before `toastinc`. The same goes for SE,
    AB, AG, GmbH, LLC, Ltd and PLC, and for the dotted forms N.V., S.A., B.V.,
    S.p.A. and Co., Ltd.
  - Only one trailing suffix comes off, never a leading word, so "AB InBev"
    and "Bosch Group" are unchanged.
- **The board label names the board that was read.**
  ([#39](https://github.com/dheerajjha/payband-mcp/issues/39),
  [#42](https://github.com/dheerajjha/payband-mcp/pull/42), from
  @subhrajeetshaw008-bit) `board="greenhouse"` with no slug reported
  `"greenhouse:"`. It now reports the slug it filled in, such as
  `"greenhouse:toast"`.
- The lockfile moves to mcp 2.3.0 and PyJWT 2.15.1
  ([#36](https://github.com/dheerajjha/payband-mcp/pull/36)). Installs from
  PyPI already resolved those.

## 0.11.0 — 2026-09-17

- **A bare `$` is resolved against the posting's own location.** `$120,000 -
  $150,000` on a Toronto posting now reads CAD and the same string on a Sydney
  posting reads AUD, instead of every unmarked dollar figure being assumed USD.
  This was the currency bug the project already knew about, still live: since
  `pay_bands` groups by currency, a Canadian band did not merely carry the
  wrong label, it silently joined the USD bucket and was averaged against
  numbers it has no relationship to. Comparing unconverted currencies is one of
  the failures this repo exists to not commit.
- The location is only ever *read*, never inferred. A posting whose location
  carries no signal still reports USD, which is the documented fallback — the
  change is that a posting which does say gets believed. `on-site` is
  deliberately not treated as a location marker, in either position, so
  `On-site, Austin TX` stays USD rather than becoming Ontario.

## 0.10.0 — 2026-09-17

- **`interval_stated` on every pay reading.** Year is the only sane default
  for a salary band in prose and `_plausible` keeps it from swallowing an
  hourly rate — but a default is not a statement, and nothing in the output
  said which one you were looking at. `"$120,000 - $160,000"` and
  `"$120,000 - $160,000 per year"` both read as `year`; only the second one
  was told to us. This is the same error as reading Keka's `salaryPeriod: 0`
  ("not available") as annual, on the prose side of the codebase.
- `_INTERVAL_PATTERNS` had **no year pattern at all** — year existed only as
  the fallback, so an explicitly annual posting was indistinguishable from a
  silent one. Added last in the tuple, so every shorter period keeps priority
  and no existing interval value changes. Bare "annual" deliberately does not
  count: it attaches to bonuses and allowances as readily as to the band, and
  `$120,000 - $160,000 plus an annual bonus` still reports `interval_stated:
  false`.

## 0.9.0 — 2026-09-17

- **`market_rate` chooses the table's period before each employer's band, not
  after.** 0.8.1 fixed the unit per company, which is the obvious single pass
  and quietly loses comparable bands: an employer posting two contract roles
  hourly and one salaried annually has an hourly modal period, so it was set
  aside as an outlier while holding an annual band directly comparable with
  every other row. With only two such employers the table ranked one contract
  rate and discarded the only other annual band there was — both numbers
  correctly labelled, and the comparison still the wrong one.
- **`other_intervals_present` on each row** reports the periods an employer
  publishes on that the table did not use, so "we chose one" stays distinct
  from "there was only one".
- **Ties break toward the longer period** rather than by set ordering, which
  was not stable between runs. An employer posting the same title salaried and
  as a contract rate has published two different things, and the salaried one
  is what "what does this role pay" is asking about.

## 0.8.1 — 2026-09-17

- **Fixed: `market_rate` merged hourly rates into annual bands and could report
  the hourly figure as the band**
  ([#24](https://github.com/dheerajjha/payband-mcp/issues/24)). A company
  posting `Senior Engineer` at $200,000-260,000/year alongside
  `Senior Engineer, Contract` at $95-130/hour was reported as a senior band of
  **95-130**. `pay_bands` had fixed the unit as well as the currency since
  0.3.0; `market_rate` had not.
- Rows now carry `interval`, so a caller can see what period a number is in,
  and companies publishing a different unit are listed under
  `other_intervals` rather than ranked. A currency can be converted; a unit
  cannot, so ranking across units states an ordering that does not exist.
- A posting that states no period no longer outvotes one that does, and is
  never swept into the dominant period. Where nothing states one, the band is
  still reported with `interval: null` rather than withheld or guessed.

## 0.8.0 — 2026-09-17

- **Keka adapter** ([#13](https://github.com/dheerajjha/payband-mcp/issues/13)),
  reaching Indian employers for the first time. The endpoint is unauthenticated
  JSON at `https://{tenant}.keka.com/careers/api/jobs/{portal}/active`, and it
  answers only under the `/careers` prefix that Keka's own robots.txt permits —
  the bare `/api/` form is a 404, so the only reachable shape is the allowed one.
  On the board verified against, 9 of 26 postings publish an INR band.
  India compels no disclosure and these employers publish anyway, which is a
  sharper version of the premise than silence would have been.
- **A published band with no stated period is no longer read as annual.** Keka's
  `salaryPeriod` enum has `0` for *"Not Available"* — an employer who published
  figures and declined to say what period they cover — and roughly half the
  published bands use it. `INR 8,00,000 - 15,00,000` almost certainly is annual;
  the posting still does not say so. `interval` is `None` in that case, and the
  numeric fields are read rather than the pre-rendered `salaryRangeFormat`,
  which parses correctly but carries no period at all.
- **An unstated interval can no longer outvote a stated one.** `pay_bands` took
  the modal interval over every posting, so on a board where most employers
  state nothing, "unstated" won the vote and the postings carrying real evidence
  were the ones discarded — with nothing reporting the loss. Only postings that
  state an interval now decide which interval a band is in, and
  `interval_unstated_count` reports what was left out.
- **Fixed a crash**: `sorted({None, "month"})` raises, so a board carrying both
  an unstated band and an hourly rate took `pay_bands` down outright.
- Probed and rejected, recorded so nobody repeats it: **Darwinbox** gates its
  job API behind request-only credentials and serves a ~900-byte shell to
  everything else. **Zoho Recruit** has a robots-permitted RSS feed at
  `/jobs/Careers/rss`, but it is a per-account opt-in that was switched off on
  all six tenants sampled — unresolved rather than dead.
## 0.7.0 — 2026-09-17

- **Atlassian adapter**, the first self-hosted employer
  ([#13](https://github.com/dheerajjha/payband-mcp/issues/13)). One request
  returns all 287 open roles, 122 with a published range.
- **Prefix-labelled ranges** are kept apart. Atlassian publishes three US
  geographic zones per role as `Zone A: $122,400 - $159,800`; the label leads
  rather than trails, so the existing detector never saw it and three zones
  collapsed into one 1.6x range belonging to no single hire.
- **Registry publishing moved to CI** over GitHub Actions OIDC. The registry's
  JWT lives five minutes, which is too short to log in and publish by hand
  reliably — four attempts failed on an expired token.
- Probed and rejected, recorded so nobody repeats it: **amazon.jobs** serves
  clean JSON with no pay anywhere in it, **Netflix**/Eightfold the same, and
  **Apple** answers 401. Those ranges exist only in rendered HTML.

## 0.6.0 — 2026-09-17

- **SmartRecruiters adapter** ([#20](https://github.com/dheerajjha/payband-mcp/issues/20), thanks @YaoSong808).
  Covers the SmartRecruiters half of [#13](https://github.com/dheerajjha/payband-mcp/issues/13).
  Listings are title-filtered before any detail is fetched, so a large board does
  not become one request per posting, and unchecked postings stay distinct from
  postings confirmed to publish nothing.
  Freshworks is now the clearest demonstration the project has: 139 postings,
  72 US and 41 India, with a published band on the US ladder and silence on the
  identical Indian titles.
- **`--version` flag** ([#14](https://github.com/dheerajjha/payband-mcp/issues/14),
  thanks @HarshRajSinghania). Reuses the `__version__` behind the MCP handshake,
  so the CLI and the protocol cannot report different builds.
- **Fixed:** `fetch_postings("Bosch Group")` raised `InvalidURL` from inside httpx
  instead of `BoardNotFound`, because a company name with a space became a slug
  candidate with a space in it.

## 0.5.0 — 2026-09-16

- **Renamed from `blind-mcp` to `payband-mcp`.** The Blind half has been
  unreachable since Blind began refusing automated requests
  ([#12](https://github.com/dheerajjha/payband-mcp/issues/12)); reading published
  pay bands is what the project does. `blind-mcp` on PyPI is now a shim that
  installs and re-exports this package. `BLIND_MCP_*` environment variables still
  work; `PAYBAND_*` is preferred.
- **Fixed:** the `User-Agent` was hardcoded to `0.1.0` and had been misreporting
  the version to every job board since the first release.

## 0.4.x — 2026-09-16

- Only the three working tools are registered. The five Blind-backed tools could
  do nothing but raise, and a tool list is part of what a model reads before
  deciding what to do. `PAYBAND_ENABLE_BLIND=1` restores them.
- On-target earnings are no longer averaged into base-salary bands. A sales
  role's "£67,000 Total OTE" is base plus commission and is reported separately.
- `BoardNotFound` says what to do when an employer is genuinely unreachable:
  compare their competitors with `market_rate`.

## 0.3.x — 2026-09-16

- **Workday adapter.** Tenants are discovered by reading `robots.txt`, which
  names the public career site in its `Sitemap` line.
- **Pay ranges are read in any currency**, not just dollars — symbols and codes,
  prefix and suffix, regional digit grouping, and intervals, so an hourly rate is
  never averaged into annual bands. Monzo went from 0 to 55 priced postings.
- **Currencies are converted before markets are compared.** Side by side and
  unconverted, GitLab's Polish band reads as paying nearly twice the US one. It
  is about 0.48x.
- **Fixed:** `market_rate` ranked rows by raw midpoint, which orders mixed
  currencies by exchange rate rather than by pay.

## 0.2.0 — 2026-09-16

- Bands are reported **per seniority level**. One range across a whole ladder is
  a number nobody is offered: "forward deployed" at Databricks spans
  140,400–320,200 undivided.
- `distinct_bands` versus `postings`, so 58 listings sharing one band read as one
  data point rather than 58.
- `market_rate` for comparing the same rung across employers.

## 0.1.x — 2026-09-09

- First release: pay bands from Greenhouse, Ashby and Lever, plus the Blind
  research tools.
