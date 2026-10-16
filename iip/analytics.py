from dataclasses import dataclass
import math
import unicodedata

from iip.config import today
from iip.models import Institution, Status


def percent(numerator, denominator):
    return numerator / denominator * 100 if numerator is not None and denominator not in (None, 0) else None


def cagr(first, last, intervals):
    if first is None or last is None or first <= 0 or last < 0 or intervals <= 0:
        return None
    return ((last / first) ** (1 / intervals) - 1) * 100


def fmt(value, suffix="", digits=0):
    return "—" if value is None else f"{value:,.{digits}f}{suffix}"


def money(value):
    if value is None:
        return "—"
    if abs(value) >= 10000000:
        return f"₹{value / 10000000:,.2f} Cr"
    if abs(value) >= 100000:
        return f"₹{value / 100000:,.2f} L"
    return f"₹{value:,.0f}"


def search_institutions(institutions, query):
    normalize = lambda s: unicodedata.normalize("NFKC", s).casefold()
    tokens = normalize(query).split()
    return [i for i in institutions if all(token in normalize(" ".join([i.name, i.city, i.state, i.university, i.aishe_code or "", i.promoter.organisation, *i.promoter.names])) for token in tokens)]


def recent_records(records):
    """Latest five calendar/academic years, preserving missing years as missing."""
    if not records:
        return []
    year = lambda r: int(str(r.year)[:4])
    cutoff = max(year(r) for r in records) - 4
    return sorted((r for r in records if year(r) >= cutoff), key=year)


def admission_summary(i):
    rows = recent_records(i.admissions)
    usable = [r for r in rows if r.registered is not None]
    latest = i.latest_admission
    rates = [percent(r.registered, r.intake) for r in usable if r.intake]
    growth = None
    if len(usable) > 1:
        intervals = int(usable[-1].year[:4]) - int(usable[0].year[:4])
        growth = cagr(usable[0].registered, usable[-1].registered, intervals)
    variance = latest.claimed - latest.registered if latest and latest.claimed is not None and latest.registered is not None else None
    return {"utilisation": percent(latest.registered, latest.intake) if latest else None, "average_utilisation": sum(rates)/len(rates) if rates else None, "cagr": growth, "variance": variance, "variance_percent": percent(variance, latest.claimed) if latest else None, "free_annual_seats": max(0, latest.intake-latest.registered) if latest and latest.registered is not None else None, "years": len(usable)}


def snapshot(i):
    a = admission_summary(i)
    p = i.latest_placement
    students, capacity = i.value("campus", "students"), i.value("campus", "capacity")
    fee = i.value("commercial", "average_fee")
    latest = i.latest_admission
    return {**a, "students": students, "capacity": capacity, "campus_utilisation": percent(students, capacity), "campus_headroom": max(0, capacity-students) if capacity is not None and students is not None else None, "placement_percent": percent(p.placed, p.eligible) if p else None, "fee": fee, "annual_cohort_revenue": latest.registered*fee if latest and latest.registered is not None and fee is not None else None}


@dataclass(frozen=True)
class Risk:
    severity: str
    title: str
    detail: str
    action: str
    evidence_ids: tuple[str, ...] = ()
    category: str = "Institution"


def risk_indicators(i):
    risks = []
    a = admission_summary(i)
    latest = i.latest_admission
    primary_students = i.value("campus", "students")
    disclosure_students = i.value("campus", "students_disclosure")
    if primary_students is not None and disclosure_students is not None and primary_students != disclosure_students:
        risks.append(Risk("Attention", "Student strength sources disagree", f"The primary source reports {fmt(primary_students)} students and the disclosure reports {fmt(disclosure_students)}. The figures may use different reporting periods or scopes.", "Reconcile source dates and programme coverage; do not treat either count as current until confirmed.", (i.campus["students"].evidence_id, i.campus["students_disclosure"].evidence_id)))
    if latest and latest.registered is not None and latest.registered > latest.intake:
        risks.append(Risk("Critical", "Registrations exceed approved annual intake", f"{latest.registered:,} registrations are recorded against {latest.intake:,} approved seats.", "Check course scope, approved intake amendments and admission permissions.", (latest.intake_evidence_id, latest.registration_evidence_id)))
    if a["variance_percent"] is not None and abs(a["variance_percent"]) >= 10:
        risks.append(Risk("Critical", "Admission claim discrepancy", f"Claimed admissions differ from registration data by {fmt(a['variance'])} students ({fmt(a['variance_percent'], '%', 1)} of the claim).", "Reconcile student-level registrations with the university, including reporting dates.", tuple(filter(None, [latest.registration_evidence_id, latest.claim_evidence_id]))))
    if a["cagr"] is not None and a["cagr"] < 0:
        risks.append(Risk("Attention", "Admissions are declining", f"Admission CAGR is {fmt(a['cagr'], '%', 1)} across {a['years']} available years.", "Investigate course demand, competition and admission channels.", tuple(r.registration_evidence_id for r in i.admissions if r.registration_evidence_id)))
    if a["utilisation"] is not None and a["utilisation"] < 60:
        risks.append(Risk("Attention", "Low annual intake utilisation", f"Only {fmt(a['utilisation'], '%', 1)} of approved annual intake is occupied.", "Validate course-level demand before projecting additional admissions.", (latest.intake_evidence_id, latest.registration_evidence_id)))
    p = i.latest_placement
    if p and p.claimed_percent is not None and percent(p.placed, p.eligible) is not None:
        gap = p.claimed_percent-percent(p.placed, p.eligible)
        if abs(gap) >= 10:
            risks.append(Risk("Attention", "Placement claim needs reconciliation", f"Advertised rate differs by {fmt(gap, ' percentage points', 1)} from the sourced eligible-student rate.", "Check unique students placed, eligibility rules, batch coverage and reporting periods.", (p.evidence_id, p.claim_evidence_id)))
    placements = recent_records(i.placements)
    if len(placements) > 1:
        first = percent(placements[0].placed, placements[0].eligible)
        last = percent(placements[-1].placed, placements[-1].eligible)
        if first is not None and last is not None and last < first-5:
            risks.append(Risk("Attention", "Placement outcomes are declining", f"Placement rate fell by {fmt(first-last, ' percentage points', 1)} over the available series.", "Request placement and employer retention evidence.", (placements[-1].evidence_id,)))
    current_authority_records = {}
    for record in sorted(i.accreditations, key=lambda r: r.year):
        if record.body != "NIRF":
            current_authority_records[(record.body, record.category)] = record
    for record in current_authority_records.values():
        if record.body == "NIRF":
            continue
        if record.valid_until and record.valid_until < today():
            risks.append(Risk("Attention", f"{record.body} validity expired", f"Recorded validity ended {record.valid_until:%d %b %Y}; current renewal is not established.", "Obtain the current regulator or affiliation document.", (record.evidence_id,)))
        if record.outcome.casefold() in {"withdrawn", "not approved", "suspended", "cancelled"}:
            risks.append(Risk("Critical", f"{record.body} adverse status", f"Recorded outcome: {record.outcome}.", "Validate scope and effective dates directly with the issuing authority.", (record.evidence_id,)))
    for key, threshold, title, detail, action in [
        ("collection_percent", 85, "Fee collection below threshold", "commercial", "Review ageing of receivables and scholarship settlement."),
        ("faculty_attrition_percent", 20, "High faculty attrition", "campus", "Review faculty retention and staffing continuity."),
    ]:
        value = i.value(detail, key)
        if value is not None and ((value < threshold) if key == "collection_percent" else (value > threshold)):
            risks.append(Risk("Attention", title, f"Recorded rate: {fmt(value, '%', 1)}. Screening threshold: {threshold}%.", action, (getattr(i, detail)[key].evidence_id,)))
    if not i.evidence or not any(e.status == Status.VERIFIED for e in i.evidence):
        risks.append(Risk("Data gap", "Evidence awaits independent review", "No evidence in this profile has been independently marked verified." if not i.demo else "All evidence is illustrative demo data; verification coverage is 0%.", "Collect current primary documents and record a named review."))
    if not i.admissions:
        risks.append(Risk("Data gap", "Admission history unavailable", "No sourced admission records have been supplied.", "Obtain five academic years of intake and university registrations."))
    if not i.placements:
        risks.append(Risk("Data gap", "Placement history unavailable", "No sourced placement records have been supplied.", "Obtain eligible, placed and batch counts for each year."))
    if not current_authority_records:
        risks.append(Risk("Data gap", "Regulatory documents unavailable", "No recognition, affiliation or accreditation documents have been supplied.", "Establish which regulators apply and collect current recognition and affiliation records."))
    if not any(i.value("campus", key) is not None for key in ["land_acres", "built_up_sqft", "classrooms", "labs", "library_books"]):
        risks.append(Risk("Data gap", "Infrastructure baseline unavailable", "No sourced land, building, classroom, laboratory or library measurements have been supplied.", "Collect the relevant campus disclosure and record a dated site visit; missing data does not establish a physical deficiency."))
    # Promoter matters remain separate from institution operating indicators.
    for record in i.promoter.records:
        risks.append(Risk("Review", f"Promoter record: {record.stage}", f"{record.title}. Procedural stage: {record.stage}; no other outcome is inferred.", "Review the primary record, entity identity and current procedural status.", (record.evidence_id,), "Promoter"))
    priority = {"Critical": 0, "Attention": 1, "Data gap": 2, "Review": 3}
    return sorted(risks, key=lambda r: priority[r.severity])


def scenario(annual_intake, current_admissions, target_percent, fee, collection_percent, scholarship_percent, discount_percent, refund_percent, share_percent):
    values = [annual_intake, current_admissions, target_percent, fee, collection_percent, scholarship_percent, discount_percent, refund_percent, share_percent]
    if any(v is None or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("Scenario inputs must be finite, nonnegative numbers.")
    if any(v > 100 for v in [target_percent, collection_percent, scholarship_percent, discount_percent, refund_percent, share_percent]):
        raise ValueError("Scenario percentages must be between 0 and 100.")
    target = int(annual_intake * target_percent/100)
    incremental = max(0, target-current_admissions)
    gross = target * fee
    net = gross * (1-scholarship_percent/100) * (1-discount_percent/100) * collection_percent/100 * (1-refund_percent/100)
    return {"target_admissions": target, "incremental_admissions": incremental, "gross": gross, "net": net, "partner_revenue": net*share_percent/100, "incremental_gross": incremental*fee}
