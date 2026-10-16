import json
from datetime import date

import pytest
from pydantic import ValidationError

from iip.analytics import admission_summary, snapshot, cagr, percent, scenario, risk_indicators, search_institutions
from iip.models import Institution, Evidence, Admission, Placement, Metric
from iip.sample_data import demo_institutions
from iip.importing import parse_profiles
from iip.reports import executive_brief, printable_brief


def test_missing_data_and_zero_denominators_are_not_fabricated(real_profile):
    s = snapshot(real_profile)
    assert s["students"] is None and s["placement_percent"] is None and s["annual_cohort_revenue"] is None
    assert percent(0, 100) == 0
    assert percent(0, 0) is None
    assert cagr(0, 100, 4) is None


def test_admission_variance_denominator_and_elapsed_year_cagr(real_profile):
    data = real_profile.model_dump()
    data["admissions"] = [
        {"year": "2021-22", "intake": 1000, "registered": 500, "intake_evidence_id": "E1", "registration_evidence_id": "E1"},
        {"year": "2025-26", "intake": 1200, "registered": 812, "claimed": 950, "intake_evidence_id": "E1", "registration_evidence_id": "E1", "claim_evidence_id": "E1"},
    ]
    result = admission_summary(Institution.model_validate(data))
    assert result["variance"] == 138
    assert result["variance_percent"] == pytest.approx(138/950*100)
    assert result["cagr"] == pytest.approx(((812/500)**.25-1)*100)
    assert result["free_annual_seats"] == 388


def test_campus_and_annual_capacity_are_separate():
    s = snapshot(demo_institutions()[0])
    assert s["campus_utilisation"] == 65
    assert s["utilisation"] == pytest.approx(820/1200*100)
    assert s["campus_headroom"] == 1680
    assert s["free_annual_seats"] == 380


def test_scenario_math():
    s = scenario(1200, 820, 85, 250000, 93, 12, 5, 2, 30)
    assert s["target_admissions"] == 1020
    assert s["incremental_admissions"] == 200
    assert s["gross"] == 255000000
    assert s["net"] == pytest.approx(255000000*.88*.95*.93*.98)
    assert s["partner_revenue"] == pytest.approx(s["net"]*.3)


@pytest.mark.parametrize("invalid", [-1, 101, float("inf"), float("nan")])
def test_scenario_rejects_invalid_percentages(invalid):
    with pytest.raises(ValueError):
        scenario(100, 50, invalid, 100000, 90, 10, 5, 2, 30)


def test_populated_metrics_require_evidence():
    with pytest.raises(ValidationError):
        Metric(value=812)


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_metrics_reject_nonfinite_values(value):
    with pytest.raises(ValidationError):
        Metric(value=value, evidence_id="E1")


def test_placement_rejects_inconsistent_student_counts():
    with pytest.raises(ValidationError):
        Placement(year=2025, eligible=100, placed=110, evidence_id="E1")
    with pytest.raises(ValidationError):
        Placement(year=2025, eligible=100, placed=90, batch_size=80, evidence_id="E1")


def test_academic_years_span_consecutive_years():
    with pytest.raises(ValidationError):
        Admission(year="2025-25", intake=120, intake_evidence_id="E1")


def test_missing_reference_and_duplicate_years_rejected(real_profile):
    data = real_profile.model_dump()
    data["campus"] = {"students": {"value": 500, "evidence_id": "missing"}}
    with pytest.raises(ValidationError, match="Missing evidence"):
        Institution.model_validate(data)
    data["campus"] = {}
    row = {"year": "2025-26", "intake": 100, "intake_evidence_id": "E1"}
    data["admissions"] = [row, row]
    with pytest.raises(ValidationError, match="Duplicate academic"):
        Institution.model_validate(data)


def test_verified_evidence_requires_review_metadata():
    with pytest.raises(ValidationError, match="reviewer"):
        Evidence(id="e", title="report", status="Verified", observed_on=date(2026, 1, 1))


def test_demo_evidence_cannot_be_mixed_into_real_profiles():
    data = demo_institutions()[0].model_dump()
    data["demo"] = False
    with pytest.raises(ValidationError, match="Demo evidence"):
        Institution.model_validate(data)


def test_renewed_accreditation_does_not_flag_historical_expiry(real_profile):
    data = real_profile.model_dump()
    data["accreditations"] = [
        {"body": "NAAC", "outcome": "A", "year": 2020, "valid_until": "2024-01-01", "evidence_id": "E1"},
        {"body": "NAAC", "outcome": "A+", "year": 2025, "valid_until": "2099-01-01", "evidence_id": "E1"},
    ]
    assert not any("validity expired" in r.title for r in risk_indicators(Institution.model_validate(data)))


def test_over_intake_is_explainable_critical_risk(real_profile):
    data = real_profile.model_dump()
    data["admissions"] = [{"year": "2025-26", "intake": 100, "registered": 110, "intake_evidence_id": "E1", "registration_evidence_id": "E1"}]
    i = Institution.model_validate(data)
    assert snapshot(i)["free_annual_seats"] == 0
    assert any(r.severity == "Critical" and "exceed" in r.title for r in risk_indicators(i))


def test_search_accepts_city_code_university_and_promoter():
    profiles = demo_institutions()
    for query in ["ASTER", "Hyderabad", "DEMO-C-12000", "Hyderabad Academic", "Aster Education Trust"]:
        assert profiles[0] in search_institutions(profiles, query)
    assert search_institutions(profiles, "no such campus") == []


def test_import_all_or_nothing_validation(real_profile):
    payload = json.dumps({"institutions": [real_profile.model_dump(mode="json")] }).encode()
    assert parse_profiles(payload)[0].id == real_profile.id
    with pytest.raises(ValueError, match="duplicate"):
        parse_profiles(json.dumps([real_profile.model_dump(mode="json")]*2).encode())


def test_brief_sources_and_html_escaping(real_profile):
    brief = executive_brief(demo_institutions()[0])
    assert "ILLUSTRATIVE DEMO" in brief and "[registration-2025] Demo" in brief
    data = real_profile.model_dump()
    data["name"] = '<script>alert("test")</script>'
    html = printable_brief(Institution.model_validate(data))
    assert "<script>" not in html and "&lt;script&gt;" in html
