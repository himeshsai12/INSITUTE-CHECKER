"""Explainable executive summaries and commercial criteria, never a college score."""
from pydantic import Field

from iip.analytics import recent_records, snapshot, percent, fmt, money
from iip.config import today, now_iso
from iip.models import Record


class OpportunityCriteria(Record):
    minimum_seats: int = Field(default=100, ge=1)
    minimum_fee: float = Field(default=100000, ge=0)
    minimum_collection: float = Field(default=85, ge=0, le=100)


def current_authorities(i):
    records = {}
    for row in sorted(i.accreditations, key=lambda r: r.year):
        if row.body != "NIRF":
            records[(row.body, row.category)] = row
    return list(records.values())


def authority_status(i, row):
    source = i.source(row.evidence_id)
    if row.outcome.casefold() in {"withdrawn", "not approved", "suspended", "cancelled"}:
        return "Adverse outcome — review"
    if row.valid_until and row.valid_until < today():
        return "Expired — renewal needed"
    return str(source.status) if source else "Unavailable"


def executive_trends(i):
    admissions = [r for r in recent_records(i.admissions) if r.registered is not None]
    placements = [r for r in recent_records(i.placements) if r.eligible]

    def trend(rows, value, unit):
        if len(rows) < 2:
            return {"direction": "Unavailable", "detail": "At least two sourced years are needed.", "evidence_ids": ()}
        first, last = rows[0], rows[-1]
        delta = value(last) - value(first)
        direction = "Rising" if delta > 0 else "Falling" if delta < 0 else "Stable"
        ids = tuple(dict.fromkeys(sid for row in (first, last) for sid in (
            [row.registration_evidence_id] if hasattr(row, "registered") else [row.evidence_id]
        ) if sid))
        return {"direction": direction, "detail": f"{first.year} → {last.year}: {delta:+,.1f} {unit}. Latest five-year window; missing years are not estimated.", "evidence_ids": ids}

    return {
        "Admissions": trend(admissions, lambda r: r.registered, "students"),
        "Placements": trend(placements, lambda r: percent(r.placed, r.eligible), "percentage points"),
        "Infrastructure": {"direction": "Snapshot only" if i.campus else "Unavailable", "detail": "Repeated comparable infrastructure observations are needed to establish a trend.", "evidence_ids": tuple(dict.fromkeys(m.evidence_id for m in i.campus.values() if m.evidence_id))},
    }


def partnership_opportunity(i, criteria=None):
    criteria = criteria or OpportunityCriteria()
    s = snapshot(i)
    a = i.latest_admission
    fee, collection = i.commercial.get("average_fee"), i.commercial.get("collection_percent")
    checks = [
        {"criterion": "Available annual seats", "value": s["free_annual_seats"], "minimum": criteria.minimum_seats, "evidence_ids": (a.intake_evidence_id, a.registration_evidence_id) if a else ()},
        {"criterion": "Average annual fee", "value": s["fee"], "minimum": criteria.minimum_fee, "evidence_ids": (fee.evidence_id,) if fee else ()},
        {"criterion": "Collection efficiency", "value": i.value("commercial", "collection_percent"), "minimum": criteria.minimum_collection, "evidence_ids": (collection.evidence_id,) if collection else ()},
    ]
    for check in checks:
        check["meets"] = check["value"] >= check["minimum"] if check["value"] is not None else None
    passed = sum(check["meets"] is True for check in checks)
    label = "Insufficient data" if any(c["meets"] is None for c in checks) else "High" if passed == 3 else "Medium" if passed else "Low"
    evidence_ids = {sid for check in checks for sid in check["evidence_ids"] if sid}
    return {"label": label, "criteria": criteria.model_dump(), "checks": checks, "decision": "Requires diligence", "demo": i.demo, "generated_at": now_iso(), "evidence": [e.model_dump(mode="json") for e in i.evidence if e.id in evidence_ids]}


def opportunity_rows(result):
    rows = []
    for c in result["checks"]:
        if c["criterion"] == "Average annual fee":
            formatter = money
        elif c["criterion"] == "Collection efficiency":
            formatter = lambda value: fmt(value, "%", 1)
        else:
            formatter = fmt
        rows.append({"Business criterion": c["criterion"], "Recorded": formatter(c["value"]), "Minimum": formatter(c["minimum"]), "Result": "Unavailable" if c["meets"] is None else "Meets" if c["meets"] else "Below minimum", "Evidence": ", ".join(filter(None, c["evidence_ids"])) or "Unavailable"})
    return rows
