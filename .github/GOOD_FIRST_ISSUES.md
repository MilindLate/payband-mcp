# Good first issues

Real, reproduced, and currently open. Each issue says where the code is, what
the fix probably looks like, and how to test it. `mentored` means ask questions
in the thread and you'll get walked through it — that's the point, not a
formality.

Comment on the issue to claim it, so two people don't collide; that has
already happened once. GitHub only lets a maintainer assign collaborators, so
a claimed issue says so in its title instead.

> This list is short on purpose. It was previously eight issues, five of which
> were already fixed and closed, and the other three unrunnable. A list padded
> with work that cannot be done wastes the time of exactly the people it is
> trying to attract.

> **Maintainer invariant, because nothing in CI checks it.** The `good first
> issue` label must mark exactly the issues under *Available now* — the label
> is what feeds the README badge and GitHub's /contribute page, and neither
> renders a caveat written in a title or in this file. If an issue is blocked,
> claimed, dormant or folded into another, it goes in a section below **and**
> loses the label. This file drifted from the labels once already.

## Available now

| # | Size | What's wrong | Why it matters |
| --- | --- | --- | --- |
| [#37](https://github.com/dheerajjha/payband-mcp/issues/37) | XS | `board_slugs` deletes accented letters, so Nestlé is looked up as `nestl` | European employer names are where the accents are, and the whole point is markets outside the US. A pure function, tested offline. |
| [#38](https://github.com/dheerajjha/payband-mcp/issues/38) | XS | `board_slugs` keeps legal suffixes, so "Toast, Inc." never tries `toast` | The legal name is what an offer letter says. Same function as #37, so whichever lands second rebases. |
| [#39](https://github.com/dheerajjha/payband-mcp/issues/39) | XS | `board="greenhouse"` with no slug reports `"greenhouse:"` as the board it read | A one-word fix in `ats.py`, and the caller can finally see which board answered. |
| [#26](https://github.com/dheerajjha/payband-mcp/issues/26) | S | Workday tenants can't be found from a company name | Mostly a **data** contribution, and **no Python needed to start**: open a careers page, read the tenant out of the URL, add a row, add a test. One verified row is a real contribution. **Take the Workday half** — Workday is in `_BOARDS`, so your row is live on merge. The Keka half of that issue is dormant until [#27](https://github.com/dheerajjha/payband-mcp/issues/27) lands. |

## Bigger, and also open

Each of these is `help wanted` and `mentored`, but not a first issue.

| # | Size | What's wrong |
| --- | --- | --- |
| [#27](https://github.com/dheerajjha/payband-mcp/issues/27) | S | The Keka adapter is wired to nothing, so no tool can reach a Keka board. About 15 lines mirroring `_smartrecruiters`, and it unblocks the Indian-employer half of the project's premise. |
| [#29](https://github.com/dheerajjha/payband-mcp/issues/29) | S | An employer we already probed and rejected is reported as a lookup failure, so callers go slug-hunting for a board that doesn't exist |
| [#28](https://github.com/dheerajjha/payband-mcp/issues/28) | M | `no_range_count` merges "published nothing where a band is required" with "published nothing where none is" |
| [#30](https://github.com/dheerajjha/payband-mcp/issues/30) | M | `classify()` reports `mid` for any unmarked title, so the mid band is a default presented as a reading |
| [#13](https://github.com/dheerajjha/payband-mcp/issues/13) | M | Google, Meta, Amazon and Apple self-hosted sites, and no Recruitee adapter. Workday and SmartRecruiters are **done**. Google Careers is scraping, not an API, so it stays behind `selfhosted.py`. |

## Open, but wait

| # | Size | Status |
| --- | --- | --- |
| [#23](https://github.com/dheerajjha/payband-mcp/issues/23) | XS | Claimed by @Rayan-and-beyond. If there's no reply by 2026-10-25, it opens up again. |
| [#18](https://github.com/dheerajjha/payband-mcp/issues/18) | S | Folded into [#26](https://github.com/dheerajjha/payband-mcp/issues/26) — same registry, one issue. Still open, and still the place the Workday URL shapes are written up, which is what #26 links to. Take #26 |

## Open, but currently dormant

[#1](https://github.com/dheerajjha/payband-mcp/issues/1),
[#4](https://github.com/dheerajjha/payband-mcp/issues/4) and
[#5](https://github.com/dheerajjha/payband-mcp/issues/5) are in the Blind code
path. Blind has returned 403 to every non-browser request since around
September 2026 ([#12](https://github.com/dheerajjha/payband-mcp/issues/12)), so
those tools are no longer registered unless `PAYBAND_ENABLE_BLIND=1`.

They are still real bugs, still fixable and testable offline against the
synthetic fixtures, and still reviewed and merged on the same terms as anything
else. But your fix ships dormant, and you cannot check it against reality — if
the fixture and the real page disagree, the fixture wins and neither of us finds
out. Worth doing if the logic interests you; not if you want a change users feel
this month.

## Not on this list?

**A board we can't reach.** If the tool says `BoardNotFound` for an employer
you care about, that's the most useful thing you can report — especially
outside the US, since the whole premise is markets that publish nothing. Open a
[coverage gap issue](https://github.com/dheerajjha/payband-mcp/issues/new?template=coverage_gap.md).

**A band that's wrong.** A number that looks authoritative and isn't is the
worst failure this project has. If `pay_bands` reports something that
contradicts what you know from the inside, that is a bug and we want it.

## Setup

```bash
git clone https://github.com/dheerajjha/payband-mcp && cd payband-mcp
uv sync --dev
uv run pytest -q     # 143 tests, all offline, a couple of seconds
```

Tests never touch the network — mock at the adapter boundary. See
[CONTRIBUTING.md](../CONTRIBUTING.md) for the hard rules (fixtures are
generated, never captured; don't weaken robots/cache/throttle; no defeating an
access control).
