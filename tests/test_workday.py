"""Workday adapter. No network: every response here is a recorded shape."""

import pytest

from payband_mcp import ats, workday

ROBOTS = """Sitemap: https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/siteMap.xml

User-agent: *
Allow: /NVIDIAExternalCareerSite/
Disallow: /talentcommunity/
Disallow: /refreshFacet/
"""

ROBOTS_SECOND_DOMAIN = """Sitemap: https://wd1.myworkdaysite.com/recruiting/paypal/jobs/siteMap.xml

User-agent: *
Allow: /jobs/
Disallow: /refreshFacet/
"""


def test_discover_reads_the_site_out_of_robots(monkeypatch):
    """robots.txt is the file the site publishes to say what may be read."""
    monkeypatch.setattr(workday, "_robots", lambda host, ua: ROBOTS)
    assert workday.discover("nvidia") == (
        "nvidia.wd5.myworkdayjobs.com", "NVIDIAExternalCareerSite"
    )


def test_discover_handles_the_second_workday_domain(monkeypatch):
    monkeypatch.setattr(workday, "_robots", lambda host, ua: ROBOTS_SECOND_DOMAIN)
    host, site = workday.discover("paypal")
    assert site == "jobs"


def test_discover_skips_hosts_that_do_not_answer(monkeypatch):
    tried = []

    def robots(host, ua):
        tried.append(host)
        if "wd3" not in host:
            raise OSError("no such host")
        return ROBOTS.replace("nvidia.wd5", "acme.wd3").replace(
            "NVIDIAExternalCareerSite", "Acme_Careers"
        )

    monkeypatch.setattr(workday, "_robots", robots)
    assert workday.discover("acme") == ("acme.wd3.myworkdayjobs.com", "Acme_Careers")
    assert len(tried) == 3          # wd5, wd1, then wd3


def test_discover_says_what_to_do_when_nothing_answers(monkeypatch):
    monkeypatch.setattr(
        workday, "_robots", lambda host, ua: (_ for _ in ()).throw(OSError())
    )
    with pytest.raises(workday.WorkdayNotFound, match="workday:<tenant>/<site>"):
        workday.discover("nope")


def test_discover_ignores_paths_robots_disallows(monkeypatch):
    """'Disallow: /apply/' must never be mistaken for the career site."""
    monkeypatch.setattr(
        workday, "_robots",
        lambda host, ua: "User-agent: *\nDisallow: /apply/\nAllow: /refreshFacet/\n",
    )
    with pytest.raises(workday.WorkdayNotFound):
        workday.discover("acme")


def test_listing_stops_at_the_last_page(monkeypatch):
    calls = []

    def request(url, payload=None, user_agent=""):
        calls.append(payload["offset"])
        remaining = 25 - payload["offset"]
        return {
            "total": 25,
            "jobPostings": [
                {"title": f"Engineer {i}", "externalPath": f"/job/x/E_{i}"}
                for i in range(min(workday.PAGE, max(0, remaining)))
            ],
        }

    monkeypatch.setattr(workday, "_request", request)
    jobs = list(workday.list_postings("h", "t", "s", "engineer"))
    assert len(jobs) == 25
    assert calls == [0, 20]          # stops once the page is short


def test_pay_is_read_from_the_description(monkeypatch):
    monkeypatch.setattr(
        workday, "_request",
        lambda *a, **k: {"jobPostingInfo": {
            "jobDescription": "<p>The base salary range is 184,000 USD - 287,500 USD.</p>"
        }},
    )
    pay = workday.fetch_pay("h", "t", "s", "/job/x")
    assert (pay["min"], pay["max"], pay["currency"]) == (184000, 287500, "USD")


def test_pay_uses_posting_location_for_bare_dollars(monkeypatch):
    monkeypatch.setattr(
        workday,
        "_request",
        lambda *a, **k: {
            "jobPostingInfo": {
                "jobDescription": "Salary range $120,000 - $150,000.",
                "location": "Toronto, ON, Canada",
            }
        },
    )

    pay = workday.fetch_pay("h", "t", "s", "/job/x")

    assert (pay["min"], pay["max"], pay["currency"]) == (120000, 150000, "CAD")


def test_unchecked_postings_are_not_reported_as_publishing_nothing(monkeypatch):
    """Cisco matched 111 postings while only 40 were looked at."""
    postings = [
        ats._posting(f"Engineer {i}", "US", "u", None, "acme", "workday",
                     detail={"host": "h", "tenant": "t", "site": "s", "path": "/p"})
        for i in range(5)
    ]
    monkeypatch.setattr(workday, "fetch_pay", lambda *a, **k: None)

    assert all(p["pay_known"] is False for p in postings)
    assert ats.enrich_pay(postings, limit=2) == 2
    assert [p["pay_known"] for p in postings] == [True, True, False, False, False]


def test_inline_boards_are_known_without_a_second_request():
    posting = ats._posting("Engineer", "US", "u", None, "acme", "greenhouse")
    assert "pay_known" not in posting      # nothing deferred, so nothing unknown
    assert ats.enrich_pay([posting]) == 0
