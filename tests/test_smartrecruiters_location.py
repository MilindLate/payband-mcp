"""Regression tests for SmartRecruiters location fallbacks."""

from payband_mcp import ats, smartrecruiters


def test_smartrecruiters_location_components_used_for_listing_and_pay(monkeypatch):
    """A detail without fullLocation must still identify Canadian bare dollars."""
    location = {"city": "Toronto", "region": "ON", "country": "ca"}
    listing = {
        "content": [{"id": "posting-1", "name": "Engineer", "location": location}],
        "totalFound": 1,
    }
    detail = {
        "location": location,
        "jobAd": {
            "sections": {
                "additionalInformation": {"text": "Salary range $120,000 - $150,000."}
            }
        },
    }

    def fake_request(company, posting_id=None, **params):
        return detail if posting_id else listing

    monkeypatch.setattr(smartrecruiters, "_request", fake_request)
    board, postings = ats.fetch_postings("Acme", board="smartrecruiters:Acme")

    assert board == "smartrecruiters:Acme"
    assert postings[0]["location"] == "Toronto, ON, ca"
    assert ats.enrich_pay(postings) == 1
    assert (postings[0]["pay"]["min"], postings[0]["pay"]["max"]) == (
        120000,
        150000,
    )
    assert postings[0]["pay"]["currency"] == "CAD"
