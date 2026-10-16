"""Deterministic, fictional data. No sample is represented as a real institution."""
from iip.models import Institution


def demo_institutions():
    specs = [
        ("aster", "Aster Institute of Technology", "Hyderabad", "Telangana", "Engineering", [540, 610, 690, 760, 820], 1200, 250000, 3120, [50, 58, 64, 68, 73], "A", 148),
        ("meridian", "Meridian School of Management", "Pune", "Maharashtra", "Management", [300, 345, 390, 430, 470], 600, 320000, 1080, [65, 71, 77, 81, 86], "A+", 76),
        ("northstar", "Northstar University", "Bengaluru", "Karnataka", "University", [1600, 1780, 1930, 2160, 2400], 3000, 290000, 8400, [70, 73, 78, 80, 82], "A++", 58),
        ("cedar", "Cedar College of Engineering", "Coimbatore", "Tamil Nadu", "Engineering", [680, 640, 590, 520, 440], 960, 180000, 2200, [75, 72, 67, 61, 55], "B++", None),
        ("aravalli", "Aravalli Institute of Management", "Jaipur", "Rajasthan", "Management", [210, 240, 278, 310, 330], 480, 220000, 790, [50, 56, 62, 67, 70], "B+", None),
        ("bluehaven", "Bluehaven Institute of Technology", "Kochi", "Kerala", "Engineering", [460, 500, 555, 620, 700], 900, 240000, 2520, [61, 65, 71, 77, 81], "A", 132),
    ]
    result = []
    for index, (slug, name, city, state, category, admissions, intake, fee, students, placement_rates, grade, rank) in enumerate(specs):
        evidence = []
        def source(source_id, title, kind, period="2025-26", excerpt=""):
            evidence.append({"id": source_id, "title": f"Illustrative {title}", "source_type": kind, "status": "Demo", "observed_on": "2026-09-23", "period": period, "excerpt": excerpt or "Synthetic data for product demonstration. No real institution or document is represented."})
            return source_id
        identity = source("identity", "institution profile", "Institution")
        annual = source("annual", "campus annual report", "Institution")
        finance = source("finance", "management financial statement", "Internal diligence")
        promoter = source("promoter", "trust and management register", "Internal diligence")
        course_source = source("courses", "course intake and fee schedule", "Institution")
        rows, placements, accreditations = [], [], []
        for offset, year in enumerate(range(2021, 2026)):
            period = f"{year}-{str(year+1)[-2:]}"
            approved = intake if offset >= 3 else int(intake * 0.9)
            intake_id = source(f"intake-{year}", f"approved intake {period}", "University", period)
            registration_id = source(f"registration-{year}", f"registration extract {period}", "University", period)
            claim_id = source(f"claim-{year}", f"college admission statement {period}", "Institution", period)
            claimed = int(admissions[offset] * (1.16 if slug in {"aster", "cedar"} else 1.03))
            rows.append({"year": period, "intake": approved, "registered": admissions[offset], "claimed": claimed, "intake_evidence_id": intake_id, "registration_evidence_id": registration_id, "claim_evidence_id": claim_id})
            eligible = int(intake * (0.34 + offset * 0.008))
            placed = round(eligible * placement_rates[offset] / 100)
            placement_id = source(f"placement-{year}", f"placement report {year}", "Institution", str(year))
            advertised_id = source(f"placement-claim-{year}", f"placement brochure {year}", "Institution", str(year))
            placements.append({"year": year, "eligible": eligible, "placed": placed, "batch_size": int(eligible * 1.15), "claimed_percent": min(99, placement_rates[offset] + (19 if slug == "aster" else 4)), "highest_lpa": round(11 + offset * 1.75 + index * 1.2, 1), "average_lpa": round(3.4 + offset * .45 + index * .3, 1), "median_lpa": round(3.0 + offset * .4 + index * .25, 1), "evidence_id": placement_id, "claim_evidence_id": advertised_id})
            nirf_id = source(f"nirf-{year+1}", f"ranking submission {year+1}", "Government / regulator", str(year+1))
            accreditations.append({"body": "NIRF", "outcome": f"#{rank + (4-offset)*8}" if rank and offset > 0 else "Not ranked", "category": category, "year": year+1, "evidence_id": nirf_id})
        for body, outcome in [("AICTE", "Approved"), ("UGC", "Listed / recognised"), ("Affiliation", "Affiliated"), ("NAAC", grade), ("NBA", "2 programmes accredited")]:
            sid = source(body.lower(), f"{body} record", "University" if body == "Affiliation" else "Government / regulator")
            accreditations.append({"body": body, "outcome": outcome, "category": "Programme" if body == "NBA" else "Institution", "year": 2025, "valid_until": "2026-06-30" if slug == "cedar" and body == "NAAC" else "2028-06-30", "evidence_id": sid})
        names = ["B.Tech · Computer science", "B.Tech · Electronics", "B.Tech · Mechanical", "MBA"] if category == "Engineering" else ["MBA · General", "MBA · Business analytics", "BBA", "B.Com"]
        weights = [.4, .25, .2, .15]
        courses = []
        allocated = 0
        for j, (course_name, weight) in enumerate(zip(names, weights)):
            count = round(admissions[-1] * weight) if j < 3 else admissions[-1] - allocated
            allocated += count
            courses.append({"name": course_name, "level": "PG" if "MBA" in course_name else "UG", "intake": round(intake * weight), "admissions": count, "annual_fee": int(fee * (1.05 if j == 0 else .95)), "change": "Added in 2024" if j == 1 else "Continuing", "evidence_id": course_source})
        recruiters = [{"name": label, "sector": sector, "offers": offers, "repeat": repeat, "location": location, "internship": internship, "evidence_id": "placement-2025"} for label, sector, offers, repeat, location, internship in [
            ("Sample technology employer A", "IT", 90, True, "Hyderabad", True),
            ("Sample financial employer B", "BFSI", 62, True, "Bengaluru", True),
            ("Sample engineering employer C", "Core", 46, True, "Chennai", False),
            ("Sample consulting employer D", "Services", 58, False, "Pune", True),
            ("Sample international employer E", "IT", 12, False, "Singapore", False),
        ]]
        campus_values = {"students": students, "capacity": intake*4, "faculty": max(40, round(students/17)), "attendance_percent": 84, "pass_percent": 87 if slug != "cedar" else 71, "graduation_percent": 83, "dropout_percent": 4.5, "faculty_attrition_percent": 24 if slug == "cedar" else 8, "backlogs": 130, "progression_percent": 78, "land_acres": 24+index*3, "built_up_sqft": 280000+index*22000, "classrooms": 62, "labs": 28, "library_books": 38000, "hostel_capacity": 1000, "hostel_occupancy": 740, "sports_facilities": 6, "transport_vehicles": 18}
        financial_values = {"average_fee": fee, "collection_percent": 76 if slug == "cedar" else 93, "outstanding_fees": 8200000, "scholarship_percent": 12, "discount_percent": 5, "refund_percent": 2, "addressable_students": students}
        legal = []
        if slug in {"aster", "cedar"}:
            legal_id = source("legal", "public record example", "Public record", "2025", "Fictional civil contract dispute, pending review. This example is not an allegation about any real person.")
            legal = [{"title": "Illustrative contractual dispute", "stage": "Civil dispute", "date": "2025-07-11", "reference": "DEMO-CIVIL-001", "description": "Fictional contract dispute included to demonstrate record classification. Outcome not established.", "evidence_id": legal_id}]
        result.append(Institution.model_validate({
            "id": slug, "name": name, "city": city, "state": state, "university": f"Illustrative {city} Academic University", "ownership": "Private educational trust", "established": 2004 + index, "aishe_code": f"DEMO-C-{12000+index}", "campus_status": "Operational (illustrative)", "identity_evidence_id": identity, "demo": True,
            "admissions": rows, "placements": placements, "courses": courses, "accreditations": accreditations, "recruiters": recruiters,
            "campus": {k: {"value": v, "evidence_id": annual} for k, v in campus_values.items()},
            "commercial": {k: {"value": v, "evidence_id": finance} for k, v in financial_values.items()},
            "promoter": {"organisation": f"Illustrative {slug.title()} Education Trust", "established": 1998+index, "names": ["Sample trustee A", "Sample trustee B"], "board": ["Sample chairperson", "Sample academic director"], "other_institutions": [f"Sample {slug.title()} Arts College"], "businesses": ["Not established in the illustrative dataset"], "evidence_id": promoter, "records": legal},
            "evidence": evidence,
        }))
    return result
