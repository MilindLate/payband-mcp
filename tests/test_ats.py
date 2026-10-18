"""Job-board parsing tests. Offline: every input here is a literal.

The payloads are shaped like the real ones, including the escaping quirks,
because those quirks are where every bug so far has lived.
"""

from __future__ import annotations

from payband_mcp import ats, smartrecruiters


def test_greenhouse_double_escaped_pay_element():
    """Greenhouse escapes twice and separates the figures with markup.

    One unescape reveals the tags but leaves `&mdash;` an entity, so the two
    figures are divided by `</span><span class="divider">&mdash;</span><span>`
    rather than by a dash. Both regressions were real.
    """
    content = (
        "&lt;div class=&quot;pay-range&quot;&gt;&lt;span&gt;$152,900&lt;/span&gt;"
        "&lt;span class=&quot;divider&quot;&gt;&amp;mdash;&lt;/span&gt;"
        "&lt;span&gt;$210,155 USD&lt;/span&gt;&lt;/div&gt;"
    )
    pay = ats._pay_from_html(content)
    assert pay == {
        "min": 152900.0,
        "max": 210155.0,
        "currency": "USD",
        "interval": "year",
        "interval_stated": False,
        "basis": "base",
        "source": "posting_pay_field",
    }


def test_pay_falls_back_to_body_text():
    pay = ats._pay_from_html("<p>The range for this role is $120,000 - $160,000 CAD.</p>")
    assert (pay["min"], pay["max"], pay["currency"]) == (120000.0, 160000.0, "CAD")
    assert pay["source"] == "posting_text"


def test_k_suffixed_and_reversed_ranges_are_normalised():
    assert ats._pay_from_html("<p>Salary $152k - $200k</p>")["min"] == 152000.0
    pay = ats._pay_from_html("<p>$210,155 — $152,900 USD</p>")
    assert pay["min"] < pay["max"]


def test_no_pay_returns_none_not_a_guess():
    assert ats._pay_from_html("<p>Competitive salary and equity.</p>") is None
    assert ats._pay_from_html(None) is None


def test_matching_requires_every_word_in_the_title():
    posts = [
        {"title": "AI Engineer - FDE (Forward Deployed Engineer)"},
        {"title": "Forward Deployed Engineer, Public Sector"},
        {"title": "Software Engineer, Deployed Systems"},
        {"title": "Account Executive"},
    ]
    hits = ats.matching(posts, "forward deployed")
    assert len(hits) == 2
    assert all("forward" in h["title"].lower() for h in hits)


def test_board_slugs_are_ordered_and_unique():
    slugs = ats.board_slugs("Goldman Sachs")
    assert slugs[0] == "goldmansachs"
    assert "goldman-sachs" in slugs
    assert len(slugs) == len(set(slugs))


def test_summarise_spans_the_whole_band():
    from payband_mcp import levels
    band = [
        {"title": "Engineer", "pay": {"min": 100.0, "max": 200.0, "currency": "USD"}},
        {"title": "Engineer", "pay": {"min": 150.0, "max": 300.0, "currency": "USD"}},
        {"title": "Engineer", "pay": {"min": 120.0, "max": 250.0, "currency": "USD"}},
    ]
    s = levels.summarise(band)
    assert (s["low"], s["high"]) == (100.0, 300.0)
    assert s["postings"] == 3
    assert s["distinct_bands"] == 3


def test_explicit_board_rejects_unknown_provider():
    import pytest
    with pytest.raises(ValueError, match="Unknown board"):
        ats.fetch_postings("Acme", board="taleo:acme")


def test_smartrecruiters_lists_and_enriches_from_literal_payloads(monkeypatch):
    """List results omit pay; the detail endpoint keeps it in escaped HTML."""
    listing = {
        "offset": 0,
        "limit": 100,
        "totalFound": 1,
        "content": [
            {
                "id": "744000149999889",
                "name": "Account Executive - Mid Market",
                "company": {"identifier": "Freshworks", "name": "Freshworks"},
                "location": {
                    "city": "San Mateo",
                    "region": "CA",
                    "country": "us",
                    "fullLocation": "San Mateo, CA, United States",
                },
            }
        ],
    }
    detail = {
        "id": "744000149999889",
        "applyUrl": (
            "https://jobs.smartrecruiters.com/Freshworks/"
            "744000149999889-account-executive-mid-market"
        ),
        "jobAd": {
            "sections": {
                "jobDescription": {
                    "text": "&lt;p&gt;Build lasting customer relationships.&lt;/p&gt;"
                },
                "additionalInformation": {
                    "text": (
                        "&lt;p&gt;$100,000 - $150,000 Base Salary. "
                        "This role is also eligible for equity.&lt;/p&gt;"
                    )
                },
            }
        },
    }
    calls = []

    def fake_request(company, posting_id=None, **params):
        calls.append((company, posting_id, params))
        return detail if posting_id else listing

    monkeypatch.setattr(smartrecruiters, "_request", fake_request)
    board, postings = ats.fetch_postings(
        "Freshworks",
        board="smartrecruiters:Freshworks",
        role="account executive",
    )

    assert board == "smartrecruiters:Freshworks"
    assert postings[0] == {
        "title": "Account Executive - Mid Market",
        "location": "San Mateo, CA, United States",
        "url": "https://jobs.smartrecruiters.com/Freshworks/744000149999889",
        "pay": None,
        "company": "Freshworks",
        "board": "smartrecruiters",
        "_detail": {
            "provider": "smartrecruiters",
            "company": "Freshworks",
            "posting_id": "744000149999889",
        },
        "pay_known": False,
    }

    assert ats.enrich_pay(postings) == 1
    assert postings[0]["pay"] == {
        "min": 100000.0,
        "max": 150000.0,
        "currency": "USD",
        "interval": "year",
        "interval_stated": False,
        "basis": "base",
        "source": "posting_text",
    }
    assert postings[0]["pay_known"] is True
    assert calls == [
        ("Freshworks", None, {"limit": 100, "offset": 0, "q": "account executive"}),
        ("Freshworks", "744000149999889", {}),
    ]


def test_smartrecruiters_uses_posting_location_for_bare_dollars(monkeypatch):
    detail = {
        "location": {
            "country": "ca",
            "fullLocation": "Toronto, ON, Canada",
        },
        "jobAd": {
            "sections": {
                "additionalInformation": {
                    "text": "Salary range $120,000 - $150,000."
                }
            }
        },
    }
    monkeypatch.setattr(smartrecruiters, "_request", lambda *a, **k: detail)

    pay = smartrecruiters.fetch_pay("Acme", "posting-1")

    assert (pay["min"], pay["max"], pay["currency"]) == (120000, 150000, "CAD")


def test_smartrecruiters_pages_without_fetching_details(monkeypatch):
    """Listing is bounded and never turns into one detail request per job."""
    pages = {
        0: {
            "offset": 0,
            "limit": 2,
            "totalFound": 3,
            "content": [
                {"id": "1", "name": "Engineer I"},
                {"id": "2", "name": "Engineer II"},
            ],
        },
        2: {
            "offset": 2,
            "limit": 2,
            "totalFound": 3,
            "content": [{"id": "3", "name": "Engineer III"}],
        },
    }
    calls = []

    def fake_request(company, posting_id=None, **params):
        calls.append((company, posting_id, params))
        return pages[params["offset"]]

    monkeypatch.setattr(smartrecruiters, "PAGE", 2)
    monkeypatch.setattr(smartrecruiters, "_request", fake_request)

    jobs = list(smartrecruiters.list_postings("Acme", "engineer", cap=10))

    assert [job["id"] for job in jobs] == ["1", "2", "3"]
    assert calls == [
        ("Acme", None, {"limit": 2, "offset": 0, "q": "engineer"}),
        ("Acme", None, {"limit": 2, "offset": 2, "q": "engineer"}),
    ]


def test_smartrecruiters_auto_discovery_survives_an_unreachable_board(monkeypatch):
    """One provider closing a connection must not prevent later providers."""
    posting = {"title": "Engineer", "pay": None}

    def unreachable(_slug):
        raise OSError("connection closed")

    def smartrecruiters_loader(slug, role):
        assert (slug, role) == ("freshworks", "engineer")
        return [posting]

    monkeypatch.setattr(
        ats,
        "_BOARDS",
        (("greenhouse", unreachable), ("smartrecruiters", smartrecruiters_loader)),
    )
    monkeypatch.setattr(ats, "_CHEAP", {"greenhouse", "smartrecruiters"})

    assert ats.fetch_postings("Freshworks", role="engineer") == (
        "smartrecruiters:freshworks",
        [posting],
    )


def test_workday_spec_accepts_a_pasted_careers_url():
    """The site id is not derivable from a name, so a URL must be enough."""
    from payband_mcp import workday
    assert workday.parse_spec("nvidia/NVIDIAExternalCareerSite") == (
        "nvidia", "NVIDIAExternalCareerSite", None
    )
    assert workday.parse_spec(
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"
    ) == ("nvidia", "NVIDIAExternalCareerSite", "nvidia.wd5.myworkdayjobs.com")
    # Some tenants are served from the second Workday domain.
    assert workday.parse_spec("https://wd1.myworkdaysite.com/recruiting/paypal/jobs") == (
        "paypal", "jobs", "paypal.wd1.myworkdayjobs.com"
    )


def test_board_not_found_explains_how_to_recover(monkeypatch):
    """A dead end should say what to do next, not just that it failed."""
    from payband_mcp import workday

    monkeypatch.setattr(ats, "_BOARDS", ())      # no loader answers
    monkeypatch.setattr(                          # ...and no Workday tenant
        workday, "discover",
        lambda *a, **k: (_ for _ in ()).throw(workday.WorkdayNotFound("none")),
    )
    with __import__("pytest").raises(ats.BoardNotFound) as caught:
        ats.fetch_postings("Nonexistent Co")
    msg = str(caught.value)
    assert "board='greenhouse:<slug>'" in msg    # the recovery path
    assert "self-host" in msg                     # the other explanation
    assert "workday:<tenant>/<site>" in msg       # ...and the Workday one


def test_slugs_never_contain_characters_a_url_rejects():
    """"Bosch Group" used to yield a candidate with a space, and httpx raised
    InvalidURL from inside the request instead of BoardNotFound."""
    import re as _re

    for name in ["Bosch Group", "Ben & Jerry's", "Foo  Bar", "AT&T", "Zoom Video"]:
        for slug in ats.board_slugs(name):
            assert _re.fullmatch(r"[a-z0-9._~-]+", slug), (name, slug)


def test_slug_shaped_names_are_still_tried_verbatim():
    assert "goldman-sachs" in ats.board_slugs("goldman-sachs")
    assert ats.board_slugs("Roku") == ["roku"]


def test_board_label_uses_resolved_slug(monkeypatch):
    seen = []

    def fake_greenhouse(slug):
        seen.append(slug)
        return [{"title": "Engineer"}]

    # _BOARDS holds references to the loaders, so patching ats._greenhouse
    # would have no effect; replace the table entry instead.
    monkeypatch.setattr(ats, "_BOARDS", (("greenhouse", fake_greenhouse),))

    label, _ = ats.fetch_postings("Toast", board="greenhouse")
    assert label == "greenhouse:toast"
    assert seen == ["toast"]

    label, _ = ats.fetch_postings("Toast", board="greenhouse:toast")
    assert label == "greenhouse:toast"


def test_board_slugs_strips_trailing_inc():
    assert "toast" in ats.board_slugs("Toast, Inc.")


def test_board_slugs_strips_trailing_se():
    assert "zalando" in ats.board_slugs("Zalando SE")


def test_board_slugs_keeps_group():
    assert "boschgroup" in ats.board_slugs("Bosch Group")


def test_board_slugs_leading_ab_unchanged():
    assert ats.board_slugs("AB InBev") == ["abinbev", "ab-inbev"]


def test_board_slugs_strips_dotted_nv():
    assert "adyen" in ats.board_slugs("Adyen N.V.")


def test_board_slugs_strips_co_ltd():
    assert "samsungelectronics" in ats.board_slugs("Samsung Electronics Co., Ltd.")


def test_board_slugs_fold_accents_to_ascii():
    assert ats.board_slugs("Nestlé")[0] == "nestle"
    assert ats.board_slugs("Société Générale") == ["societegenerale", "societe-generale"]
    assert ats.board_slugs("Škoda Auto") == ["skodaauto", "skoda-auto"]
    assert ats.board_slugs("Ørsted") == ["orsted"]
    assert ats.board_slugs("Mærsk") == ["maersk"]
    assert "strasse" in ats.board_slugs("Straße AG")
    assert "strasseag" in ats.board_slugs("Straße AG")
    assert ats.board_slugs("Łukasiewicz") == ["lukasiewicz"]
    # ASCII names come out unchanged
    assert ats.board_slugs("Goldman Sachs") == ["goldmansachs", "goldman-sachs"]
    assert ats.board_slugs("Roku") == ["roku"]

