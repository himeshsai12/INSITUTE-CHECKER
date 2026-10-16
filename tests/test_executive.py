from datetime import date

import pytest
from pydantic import ValidationError

from iip.analytics import recent_records, admission_summary, money
from iip.executive import OpportunityCriteria, authority_status, current_authorities, executive_trends, partnership_opportunity
from iip.models import Admission, Course, Institution, Promoter, Recruiter
from iip.reports import executive_brief, printable_brief
from iip.sample_data import demo_institutions


def test_five_year_window_uses_elapsed_years_and_keeps_gaps(real_profile):
    data = real_profile.model_dump()
    data["admissions"] = [Admission(year=f"{year}-{str(year+1)[-2:]}", intake=1200, registered=count, intake_evidence_id="E1", registration_evidence_id="E1").model_dump() for year, count in [(2018, 1100), (2022, 400), (2024, 600), (2026, 800)]]
    profile = Institution.model_validate(data)
    assert [r.year for r in recent_records(profile.admissions)] == ["2022-23", "2024-25", "2026-27"]
    assert admission_summary(profile)["cagr"] == pytest.approx((2 ** .25 - 1) * 100)
    trends = executive_trends(profile)
    assert trends["Admissions"]["direction"] == "Rising"
    assert "2022-23 → 2026-27" in trends["Admissions"]["detail"]
    assert trends["Placements"]["direction"] == "Unavailable"
    assert trends["Infrastructure"]["direction"] == "Unavailable"


def test_opportunity_missing_inputs_never_becomes_a_positive_assessment(real_profile):
    result = partnership_opportunity(real_profile)
    assert result["label"] == "Insufficient data"
    assert all(c["meets"] is None for c in result["checks"])
    assert result["decision"] == "Requires diligence"


@pytest.mark.parametrize("criteria, expected", [
    (OpportunityCriteria(), "High"),
    (OpportunityCriteria(minimum_seats=1000), "Medium"),
    (OpportunityCriteria(minimum_seats=1000, minimum_fee=999999, minimum_collection=100), "Low"),
])
def test_commercial_classification_exposes_criteria_and_sources(criteria, expected):
    profile = demo_institutions()[0]
    result = partnership_opportunity(profile, criteria)
    assert result["label"] == expected
    assert result["demo"] is True
    assert result["checks"][0]["value"] == 380  # Annual headroom, not 1,680 total campus spaces.
    assert result["checks"][0]["evidence_ids"] == ("intake-2025", "registration-2025")
    assert {e["id"] for e in result["evidence"]} == {"intake-2025", "registration-2025", "finance"}
    assert all(e["status"] == "Demo" and e["observed_on"] for e in result["evidence"])
    assert result["decision"] == "Requires diligence"  # Critical findings cannot become approval.
    for brief in [executive_brief(profile, criteria), printable_brief(profile, criteria)]:
        assert "CEO view" in brief
        assert "Commercial potential" in brief
        assert expected in brief
        assert money(criteria.minimum_fee) in brief


def test_criteria_reject_invalid_and_nonfinite_inputs():
    for values in [{"minimum_seats": 0}, {"minimum_collection": 101}, {"minimum_fee": float("inf")}]:
        with pytest.raises(ValidationError):
            OpportunityCriteria(**values)


def test_reviewed_expired_or_adverse_authorities_are_not_green(real_profile):
    data = real_profile.model_dump()
    data["evidence"][0].update(status="Verified", reviewer="Analyst", reviewed_on=date(2026, 10, 1), review_note="Reviewed the authority document.")
    data["accreditations"] = [
        {"body": "AICTE", "outcome": "Approved", "year": 2021, "valid_until": "2022-01-01", "evidence_id": "E1"},
        {"body": "AICTE", "outcome": "Approved", "year": 2026, "valid_until": "2099-01-01", "evidence_id": "E1"},
        {"body": "NAAC", "outcome": "A", "year": 2021, "valid_until": "2022-01-01", "evidence_id": "E1"},
        {"body": "Affiliation", "outcome": "Suspended", "year": 2026, "evidence_id": "E1"},
    ]
    profile = Institution.model_validate(data)
    records = {r.body: r for r in current_authorities(profile)}
    assert len(records) == 3
    assert authority_status(profile, records["AICTE"]) == "Verified"
    assert authority_status(profile, records["NAAC"]) == "Expired — renewal needed"
    assert authority_status(profile, records["Affiliation"]) == "Adverse outcome — review"


def test_course_history_and_employer_geography_remain_explicit(real_profile):
    old_course = Course(name="Computer science", level="UG", intake=120, evidence_id="E1")
    assert old_course.year is None
    with pytest.raises(ValidationError):
        Course(name="Computer science", level="UG", year="2025-25", intake=120, evidence_id="E1")
    recruiter = Recruiter(name="Employer", sector="IT", offers=10, evidence_id="E1")
    assert recruiter.year is None and recruiter.international is None
    with pytest.raises(ValidationError):
        Promoter(previous_institutions=["Previous College"])
    data = real_profile.model_dump()
    data["courses"] = [old_course.model_dump(), old_course.model_dump()]
    with pytest.raises(ValidationError, match="Duplicate course"):
        Institution.model_validate(data)


def test_printable_promoter_history_escapes_imported_content(real_profile):
    data = real_profile.model_dump()
    data["promoter"] = {"previous_institutions": ["<script>bad()</script>"], "evidence_id": "E1"}
    html = printable_brief(Institution.model_validate(data))
    assert "<script>" not in html
    assert "&lt;script&gt;bad()&lt;/script&gt;" in html
