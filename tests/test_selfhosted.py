"""Self-hosted careers endpoints. No network: recorded response shapes only."""

import pytest

from payband_mcp import ats, money, selfhosted

# Trimmed from the live endpoint. Atlassian publishes three US geographic
# zones per role, and its non-US ranges with a CA$ symbol.
ROWS = [
    {
        "title": "Software Engineer, 2027 Graduate U.S.",
        "locations": ["Seattle - United States -   Seattle, Washington  United States"],
        "applyUrl": "https://example.invalid/25813",
        "payRanges": (
            "<p>In The <strong>United States</strong>, we have three geographic pay "
            "zones. For this role, our current base pay ranges for new hires in each "
            "zone are:</p>\n<p><strong>Zone A</strong>: $122,400 - $159,800</p>\n"
            "<p><strong>Zone B</strong>: $110,160 - $143,820</p>\n"
            "<p><strong>Zone C</strong>: $101,592 - $132,634</p>"
        ),
    },
    {
        "title": "Software Engineer, 2027 Graduate Canada",
        "locations": ["Canada -     Canada"],
        "applyUrl": "https://example.invalid/25812",
        "payRanges": (
            "<p>In <strong>Canada</strong>, for this role, our current base pay range "
            "for new hires is:</p>\n<p><strong>Canada</strong>: CA$94,500 - CA$123,375</p>"
        ),
    },
    {
        "title": "Software Engineer Intern, 2027 Canada",
        "locations": ["Canada -     Canada"],
        "applyUrl": "https://example.invalid/25811",
        # Atlassian really does publish zeroes on some intern postings.
        "payRanges": "<p><strong>Canada</strong>: CA$0 - CA$0</p>",
    },
    {
        "title": "Account Executive",
        "locations": ["Remote - Japan - Remote"],
        "applyUrl": "https://example.invalid/25583",
        "payRanges": "",
    },
]


@pytest.fixture
def atlassian(monkeypatch):
    monkeypatch.setattr(selfhosted, "_get", lambda url, ua: ROWS)
    return selfhosted.atlassian("test")


def test_every_row_becomes_a_posting(atlassian):
    assert len(atlassian) == 4
    assert {p["company"] for p in atlassian} == {"Atlassian"}
    assert {p["board"] for p in atlassian} == {"atlassian"}


def test_the_us_zones_are_kept_apart(atlassian):
    """Their union is 101,592-159,800, which is nobody's band."""
    pay = atlassian[0]["pay"]
    assert (pay["min"], pay["max"], pay["currency"]) == (122400, 159800, "USD")
    assert [(b["label"], b["min"]) for b in pay["bands"]] == [
        ("Zone A", 122400), ("Zone B", 110160), ("Zone C", 101592)
    ]


def test_the_ca_dollar_symbol_is_not_usd(atlassian):
    pay = atlassian[1]["pay"]
    assert (pay["min"], pay["max"], pay["currency"]) == (94500, 123375, "CAD")


def test_a_zero_range_is_not_a_published_band(atlassian):
    assert atlassian[2]["pay"] is None


def test_a_posting_with_no_payranges_is_silent_not_guessed(atlassian):
    assert atlassian[3]["pay"] is None


def test_location_is_flattened_for_reading(atlassian):
    assert atlassian[0]["location"] == (
        "Seattle, United States, Seattle, Washington United States"
    )


def test_an_empty_or_wrong_shaped_response_is_an_error(monkeypatch):
    monkeypatch.setattr(selfhosted, "_get", lambda url, ua: [])
    with pytest.raises(selfhosted.SelfHostedNotFound):
        selfhosted.atlassian("test")
    monkeypatch.setattr(selfhosted, "_get", lambda url, ua: {"jobs": []})
    with pytest.raises(selfhosted.SelfHostedNotFound):
        selfhosted.atlassian("test")


def test_fetch_postings_routes_a_known_employer_to_its_own_endpoint(monkeypatch):
    monkeypatch.setattr(selfhosted, "_get", lambda url, ua: ROWS)
    monkeypatch.setattr(
        ats, "_BOARDS", ()
    )  # no board may answer; the name alone must route
    board, postings = ats.fetch_postings("Atlassian")
    assert board == "atlassian"
    assert len(postings) == 4


def test_prefix_labels_do_not_swallow_ordinary_prose():
    """"...ranges are:" must not become a band label."""
    pay = money.parse("Our base pay range is: $120,000 - $150,000")
    assert pay["min"] == 120000
    assert "bands" not in pay or pay["bands"][0]["label"] != "is"


def test_unreachable_employers_are_documented():
    """Settled negative findings carry reason, endpoint, issue, and recorded date."""
    expected = {"amazon", "apple", "netflix", "meta", "microsoft"}
    assert expected.issubset(set(selfhosted.UNREACHABLE))

    for key in expected:
        entry = selfhosted.UNREACHABLE[key]
        assert entry.reason, f"{key} missing reason"
        assert entry.date == "2026-09-17", f"{key} wrong date"
        assert entry.issue == 13

    # Meta, Microsoft, and Netflix endpoints are not in the record
    assert selfhosted.UNREACHABLE["meta"].endpoint == ""
    assert selfhosted.UNREACHABLE["microsoft"].endpoint == ""
    assert selfhosted.UNREACHABLE["netflix"].endpoint == ""

    # Amazon and Apple have endpoints from the record
    assert selfhosted.UNREACHABLE["amazon"].endpoint == "amazon.jobs/en/search.json"
    assert selfhosted.UNREACHABLE["apple"].endpoint == "jobs.apple.com/api"

    amazon = selfhosted.UNREACHABLE["amazon"]
    explained = amazon.explain("Amazon")
    assert "Amazon self-hosts." in explained
    assert "settled finding (#13, recorded 2026-09-17)" in explained
    assert "not a lookup failure -- no slug will change it" in explained


def test_fetch_postings_explains_amazon_instead_of_slug_hunting(monkeypatch):
    """Calling fetch_postings('Amazon') explains why it cannot be read (issue #29)."""
    monkeypatch.setattr(ats, "_BOARDS", ())
    monkeypatch.setattr(ats, "_workday", lambda slug, role="": [])
    with pytest.raises(ats.BoardNotFound) as caught:
        ats.fetch_postings("Amazon")
    msg = str(caught.value)
    assert "Amazon self-hosts." in msg
    assert "ranges are rendered into the HTML page only" in msg
    assert "settled finding" in msg
    assert "not a lookup failure" in msg
    # Crucially: it must NOT suggest hunting for Greenhouse / Ashby / Lever slugs
    assert "job-boards.greenhouse.io" not in msg
    assert "open their careers page" not in msg


def test_fetch_postings_explains_other_rejected_employers(monkeypatch):
    """Each probed-and-rejected employer gets its own finding, as a sentence that
    starts with the name it was asked about and claims nothing the record does not."""
    monkeypatch.setattr(ats, "_BOARDS", ())
    monkeypatch.setattr(ats, "_workday", lambda slug, role="": [])
    expected = {
        "Apple": "Apple self-hosts, and jobs.apple.com/api answers 401 to an anonymous request.",
        "Apple Inc.": "Apple Inc. self-hosts, and jobs.apple.com/api answers 401",
        "Netflix": "Netflix's board is on Eightfold, whose documented API returns job_description with no range in it.",
        "Netflix Inc.": "Netflix Inc.'s board is on Eightfold",
        "Meta": "Meta self-hosts, and its careers site did not answer a plain GET at all.",
        "Meta Platforms": "Meta Platforms self-hosts, and its careers site",
        "Microsoft": "Microsoft's careers site did not answer a plain GET at all.",
        "Amazon.com": "Amazon.com self-hosts. Its Washington and California ranges",
    }
    for company, finding in expected.items():
        with pytest.raises(ats.BoardNotFound) as caught:
            ats.fetch_postings(company)
        msg = str(caught.value)
        assert msg.startswith(finding), msg
        assert "settled finding (#13, recorded 2026-09-17)" in msg
        assert "not a lookup failure" in msg
    # The record says Amazon, Apple and Meta self-host. It does not say so of
    # Microsoft, and Netflix is on Eightfold.
    for company in ("Netflix", "Microsoft"):
        with pytest.raises(ats.BoardNotFound) as caught:
            ats.fetch_postings(company)
        assert "self-hosts" not in str(caught.value)


def test_google_not_probed_falls_through_to_unprobed_slug_advice(monkeypatch):
    """Google was never probed, so it stays in the unprobed bucket with slug advice."""
    assert "google" not in selfhosted.UNREACHABLE
    assert "alphabet" not in selfhosted.UNREACHABLE
    monkeypatch.setattr(ats, "_BOARDS", ())
    monkeypatch.setattr(ats, "_workday", lambda slug, role="": [])
    with pytest.raises(ats.BoardNotFound) as caught:
        ats.fetch_postings("Google")
    msg = str(caught.value)
    assert "Two common reasons: the board token differs from the company name" in msg


def test_explicit_board_for_rejected_employer_is_honored(monkeypatch):
    """An explicit board= must be honoured and not blocked by the rejection table."""
    seen = []

    def fake_greenhouse(slug):
        seen.append(slug)
        return [{"title": "Software Engineer", "_detail": {}}]

    monkeypatch.setattr(ats, "_BOARDS", (("greenhouse", fake_greenhouse),))
    board, postings = ats.fetch_postings("Amazon", board="greenhouse:amazon")
    assert board == "greenhouse:amazon"
    assert len(postings) == 1
    assert seen == ["amazon"]


def test_explicit_rejected_selfhosted_name_explains_finding():
    """Passing board='amazon' directly explains the finding rather than unknown board."""
    with pytest.raises(ats.BoardNotFound) as caught:
        ats.fetch_postings("Amazon", board="amazon")
    msg = str(caught.value)
    assert "Amazon self-hosts." in msg
    assert "settled finding" in msg


def test_unknown_employer_still_receives_slug_advice(monkeypatch):
    """An unknown company still gets the standard slug hunting advice."""
    monkeypatch.setattr(ats, "_BOARDS", ())
    monkeypatch.setattr(ats, "_workday", lambda slug, role="": [])
    with pytest.raises(ats.BoardNotFound) as caught:
        ats.fetch_postings("Unknown Corp")
    msg = str(caught.value)
    assert "Two common reasons: the board token differs from the company name" in msg
    assert "job-boards.greenhouse.io" in msg

