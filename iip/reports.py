"""Portable executive briefs with source references and explicit data limitations."""
import html
import re

from iip.analytics import snapshot, fmt, money, risk_indicators, percent
from iip.config import now_iso
from iip.executive import executive_trends, partnership_opportunity, opportunity_rows


def executive_brief(i, criteria=None):
    s = snapshot(i)
    def source_tag(*ids):
        sources = [i.source(sid) for sid in ids if sid]
        return "; ".join(f"[{e.id}] {e.status}" for e in sources if e) or "No source / unavailable"
    a, p = i.latest_admission, i.latest_placement
    students = i.campus.get("students")
    fee = i.commercial.get("average_fee")
    lines = [f"# {i.name} — executive brief", f"Generated: {now_iso()}", "", "**ILLUSTRATIVE DEMO: all names, records and figures are fictional.**" if i.demo else "**Evidence-based screening. Findings require current document review.**", "", f"{i.city}, {i.state} · {i.ownership} · {i.university}", f"AISHE code: {i.aishe_code or 'Not supplied'} · Established: {i.established or 'Not supplied'}", f"Identity source: {source_tag(i.identity_evidence_id)}", "", "## Executive snapshot", "", "| Measure | Value | Evidence |", "| --- | --- | --- |", f"| Students | {fmt(s['students'])} | {source_tag(students.evidence_id if students else None)} |", f"| Annual intake utilisation | {fmt(s['utilisation'], '%', 1)} | {source_tag(a.intake_evidence_id, a.registration_evidence_id) if a else 'Unavailable'} |", f"| Placement / eligible students | {fmt(s['placement_percent'], '%', 1)} | {source_tag(p.evidence_id) if p else 'Unavailable'} |", f"| Average annual fee | {money(s['fee'])} | {source_tag(fee.evidence_id if fee else None)} |", f"| Annual cohort gross at stated fee | {money(s['annual_cohort_revenue'])} | Calculated from registered admissions × fee; before deductions |", f"| Available annual seats | {fmt(s['free_annual_seats'])} | Calculated from latest intake minus registrations |", f"| Admission CAGR | {fmt(s['cagr'], '%', 1)} | Calculated across {s['years']} available years |", "", "## Admission history", "", "| Academic year | Intake | Registered | College claim | Utilisation | Sources |", "| --- | --- | --- | --- | --- | --- |"]
    for row in sorted(i.admissions, key=lambda r: r.year):
        lines.append(f"| {row.year} | {fmt(row.intake)} | {fmt(row.registered)} | {fmt(row.claimed)} | {fmt(percent(row.registered, row.intake), '%', 1)} | {source_tag(row.intake_evidence_id, row.registration_evidence_id, row.claim_evidence_id)} |")
    if not i.admissions:
        lines.append("Admission history unavailable.")
    lines.extend(["", "## Placement history", "", "| Year | Eligible | Placed | Placement rate | Average LPA | Median LPA | Sources |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for row in sorted(i.placements, key=lambda r: r.year):
        lines.append(f"| {row.year} | {fmt(row.eligible)} | {fmt(row.placed)} | {fmt(percent(row.placed, row.eligible), '%', 1)} | {fmt(row.average_lpa, '', 1)} | {fmt(row.median_lpa, '', 1)} | {source_tag(row.evidence_id)} |")
    if not i.placements:
        lines.append("Placement history unavailable.")
    lines.extend(["", "## Regulatory and accreditation records", ""])
    for row in sorted(i.accreditations, key=lambda r: (r.body, -r.year)):
        lines.append(f"- {row.body} · {row.category} · {row.year}: {row.outcome}; validity: {row.valid_until or 'Not supplied'}; {source_tag(row.evidence_id)}")
    lines.extend(["", "## CEO view", ""])
    for label, trend in executive_trends(i).items():
        lines.append(f"- {label}: {trend['direction']}. {trend['detail']} Sources: {source_tag(*trend['evidence_ids'])}")
    opportunity = partnership_opportunity(i, criteria)
    lines.extend(["", f"Commercial potential: **{opportunity['label']}**. Partnership decision: **Requires diligence**.", "Business criteria are editable assumptions, not regulator thresholds or a college score. High: all three criteria met; Medium: one or two; Low: none; missing inputs: Insufficient data.", "", "| Business criterion | Recorded | Minimum | Result | Evidence |", "| --- | --- | --- | --- | --- |"])
    for row in opportunity_rows(opportunity):
        lines.append("| " + " | ".join(row.values()) + " |")
    lines.extend(["", "## Risk indicators and follow-up", ""])
    for risk in risk_indicators(i):
        lines.append(f"- **{risk.severity} / {risk.category}: {risk.title}.** {risk.detail} Next action: {risk.action} Sources: {source_tag(*risk.evidence_ids)}")
    lines.extend(["", "## Promoter diligence", "", f"Organisation: {i.promoter.organisation}. Source: {source_tag(i.promoter.evidence_id)}.", "Promoter records are reviewed separately. No institution score or inference of guilt is produced.", ""])
    promoter_lines = [f"- {label}: {', '.join(values) or 'Not supplied'}. {source_tag(i.promoter.evidence_id)}" for label, values in [("Promoters / directors", i.promoter.names), ("Board / key management", i.promoter.board), ("Other institutions", i.promoter.other_institutions), ("Previous institutions", i.promoter.previous_institutions), ("Associated businesses", i.promoter.businesses)]]
    lines.extend(promoter_lines + ["", "## Evidence register", ""])
    for e in i.evidence:
        lines.extend([f"- **[{e.id}] {e.title}** — {e.source_type}; {e.status}; period: {e.period}; observed: {e.observed_on}; publication: {e.published_on or 'Not supplied'}."])
        if e.url:
            lines.append(f"  Source: <{e.url}>")
        if e.reviewer:
            lines.append(f"  Review: {e.reviewer}, {e.reviewed_on}; {e.review_note}")
    lines.extend(["", "## Interpretation notes", "", "Annual intake utilisation and total campus capacity utilisation use different denominators. Placement rate uses unique students placed divided by eligible students. Search results and institution submissions are not independent verification. Missing fields remain unavailable. Commercial figures are scenarios rather than forecasts. No composite college score is generated."])
    return "\n".join(lines)


def printable_brief(i, criteria=None):
    # Escape every imported value before embedding; profile content cannot execute HTML.
    esc = lambda value: html.escape(str(value))
    def refs(*ids):
        return " ".join(f'<a href="#source-{esc(sid)}">[{esc(sid)}]</a>' for sid in dict.fromkeys(filter(None, ids))) or "Unavailable"
    def table(headers, rows):
        head = "".join(f"<th>{esc(h)}</th>" for h in headers)
        body = "".join("<tr>"+"".join(f"<td>{cell}</td>" for cell in row)+"</tr>" for row in rows)
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    s = snapshot(i)
    opportunity = partnership_opportunity(i, criteria)
    trends = table(["CEO view", "Direction", "Interpretation", "Evidence"], [[esc(label), esc(t["direction"]), esc(t["detail"]), refs(*t["evidence_ids"])] for label, t in executive_trends(i).items()])
    business_rows = opportunity_rows(opportunity)
    business = table(list(business_rows[0]), [[esc(value) for value in row.values()] for row in business_rows])
    summary = f'<h2>CEO view</h2>{trends}<h2>Commercial potential: {esc(opportunity["label"])}</h2><p>Partnership decision: requires diligence. Editable business criteria, not regulator thresholds or a college score. High: all three met; Medium: one or two; Low: none. Missing inputs: Insufficient data.</p>{business}'
    promoter_details = table(["Promoter detail", "Recorded value"], [[esc(label), esc(", ".join(values) or "Not supplied")] for label, values in [("Promoters / directors", i.promoter.names), ("Board / key management", i.promoter.board), ("Other institutions", i.promoter.other_institutions), ("Previous institutions", i.promoter.previous_institutions), ("Associated businesses", i.promoter.businesses)]])
    a, p = i.latest_admission, i.latest_placement
    cards = "".join(f'<article><small>{esc(label)}</small><strong>{esc(value)}</strong><span>{evidence}</span></article>' for label, value, evidence in [
        ("Annual intake utilisation", fmt(s["utilisation"], "%", 1), refs(a.intake_evidence_id, a.registration_evidence_id) if a else "Unavailable"),
        ("Placement / eligible", fmt(s["placement_percent"], "%", 1), refs(p.evidence_id) if p else "Unavailable"),
        ("Available annual seats", fmt(s["free_annual_seats"]), "Calculated from annual intake and registrations"),
        ("Annual cohort gross", money(s["annual_cohort_revenue"]), "Admissions × stated average annual fee; before deductions"),
    ])
    identity = table(["Identity field", "Recorded value"], [[esc(k), esc(v)] for k, v in [("Location", f"{i.city}, {i.state}"), ("University", i.university), ("Ownership", i.ownership), ("Established", i.established or "Not supplied"), ("AISHE", i.aishe_code or "Not supplied"), ("Campus status", i.campus_status)]])
    admissions = table(["Year", "Intake", "Registered", "Claimed", "Utilisation", "Evidence"], [[esc(r.year), esc(fmt(r.intake)), esc(fmt(r.registered)), esc(fmt(r.claimed)), esc(fmt(percent(r.registered, r.intake), "%", 1)), refs(r.intake_evidence_id, r.registration_evidence_id, r.claim_evidence_id)] for r in sorted(i.admissions, key=lambda r: r.year)]) if i.admissions else "<p>Admission history unavailable.</p>"
    placements = table(["Year", "Eligible", "Placed", "Rate", "Avg LPA", "Median LPA", "Evidence"], [[esc(r.year), esc(r.eligible), esc(r.placed), esc(fmt(percent(r.placed, r.eligible), "%", 1)), esc(fmt(r.average_lpa, digits=1)), esc(fmt(r.median_lpa, digits=1)), refs(r.evidence_id)] for r in sorted(i.placements, key=lambda r: r.year)]) if i.placements else "<p>Placement history unavailable.</p>"
    regulation = table(["Authority", "Scope", "Year", "Outcome", "Valid until", "Evidence"], [[esc(r.body), esc(r.category), esc(r.year), esc(r.outcome), esc(r.valid_until or "Not supplied"), refs(r.evidence_id)] for r in i.accreditations]) if i.accreditations else "<p>Regulatory records unavailable.</p>"
    risks = "".join(f'<section class="risk"><strong>{esc(r.severity)} / {esc(r.category)} · {esc(r.title)}</strong><p>{esc(r.detail)}</p><p class="muted">Next action: {esc(r.action)} {refs(*r.evidence_ids)}</p></section>' for r in risk_indicators(i))
    evidence_rows = []
    for e in i.evidence:
        link = f'<a href="{esc(e.url)}">Open original source</a>' if e.url else "Internal / illustrative reference"
        review = f"Reviewed: {e.reviewer}, {e.reviewed_on}. {e.review_note}" if e.reviewer else "Independent review pending"
        evidence_rows.append(f'<section class="source" id="source-{esc(e.id)}"><strong>[{esc(e.id)}] {esc(e.title)}</strong><p>{esc(e.source_type)} · <b>{esc(e.status)}</b> · period {esc(e.period)} · observed {esc(e.observed_on)}</p><p>{link} · {esc(review)}</p></section>')
    disclaimer = "ILLUSTRATIVE DEMO — All institution names, people, records and figures are fictional." if i.demo else "Evidence screening — Confirm current source documents before making a partnership decision."
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(i.name)} — Executive brief</title><style>
    body{{max-width:1050px;margin:40px auto;padding:0 24px;font:14px/1.6 system-ui;color:#172d35}}header{{border-bottom:3px solid #0d806b;padding-bottom:20px}}h1{{font-size:30px;line-height:1.2}}h2{{margin-top:32px;font-size:20px}}p{{margin:7px 0}}a{{color:#0d806b}}.muted,small{{color:#61757c}}.notice{{background:#f0eef9;padding:12px 16px;border-radius:8px;margin:20px 0}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}article{{border:1px solid #dfe7e7;border-radius:8px;padding:16px}}article strong{{display:block;font-size:26px}}article span{{display:block;font-size:10px;margin-top:8px}}table{{border-collapse:collapse;width:100%;font-size:12px;margin:16px 0}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #dfe7e7;vertical-align:top}}th{{background:#f4f7f7}}.risk{{border-left:3px solid #e3a850;padding:12px 16px;background:#fbfaf7;margin:12px 0}}.source{{font-size:11px;margin:14px 0;overflow-wrap:anywhere}}@media(max-width:600px){{.cards{{grid-template-columns:repeat(2,1fr)}}table{{font-size:10px}}}}@media print{{body{{margin:0;font-size:11px}}h2{{break-after:avoid}}article,.risk,.source,tr{{break-inside:avoid}}a{{text-decoration:none}}th{{background:#f4f7f7}}}}
    </style></head><body><header><strong>INSTITUTION INTELLIGENCE</strong><p class="muted">Executive diligence brief · {esc(now_iso())}</p><h1>{esc(i.name)}</h1><p>{esc(i.city)}, {esc(i.state)} · {esc(i.ownership)}</p></header><p class="notice">{esc(disclaimer)}</p><div class="cards">{cards}</div>{summary}<h2>Institution identity</h2>{identity}<p class="muted">Identity evidence: {refs(i.identity_evidence_id)}</p><h2>Admission history</h2>{admissions}<h2>Placement history</h2>{placements}<h2>Ranking & accreditation</h2>{regulation}<h2>Risk indicators and follow-up</h2>{risks}<h2>Promoter diligence</h2><p>{esc(i.promoter.organisation)} · {refs(i.promoter.evidence_id)}</p>{promoter_details}<p>Promoter records remain separate. A procedural record does not establish culpability or an institution rating.</p><h2>Interpretation notes</h2><p>Annual intake and campus capacity use different denominators. Placement uses unique students placed divided by eligible students. Missing values remain unavailable. Calculated revenue is a scenario before deductions. No composite college score is generated. Every source carries its own review status.</p><h2>Evidence register</h2>{''.join(evidence_rows)}</body></html>"""


def filename(i):
    return re.sub(r"[^a-zA-Z0-9_-]", "-", i.name).strip("-").lower()[:100]
