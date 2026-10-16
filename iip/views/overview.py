import pandas as pd
import streamlit as st

from iip.analytics import snapshot, risk_indicators, fmt, money
from iip.executive import OpportunityCriteria, current_authorities, authority_status, executive_trends, partnership_opportunity
from iip.reports import executive_brief, printable_brief, filename
from iip.ui import heading, cards, source_help, admission_df, placement_df, line_chart, evidence_popover, note_form, risk_card


@st.fragment
def performance_chart(i):
    with st.container(border=True):
        st.subheader("Five-year performance")
        mode = st.segmented_control("Trend", ["Admissions", "Utilisation", "Placements"], default="Admissions", key=f"overview-trend-{i.id}", label_visibility="collapsed")
        if mode == "Placements" and i.placements:
            line_chart(placement_df(i, latest_five=True), "Year", ["Placement %", "Advertised %"], percent_axis=True)
            st.caption("Placed ÷ eligible students. Advertised rate may use a different definition.")
            evidence_popover(i, [r.evidence_id for r in i.placements])
        elif mode != "Placements" and i.admissions:
            line_chart(admission_df(i, latest_five=True), "Academic year", ["Utilisation %"] if mode == "Utilisation" else ["Approved intake", "Registered admissions"], percent_axis=mode == "Utilisation")
            st.caption("Annual intake and registrations; full campus capacity is a separate measure.")
            evidence_popover(i, [sid for r in i.admissions for sid in (r.intake_evidence_id, r.registration_evidence_id)])
        else:
            st.caption("No sourced history is available for this view.")


def render(i):
    heading(i, i.name, "Executive profile")
    s = snapshot(i)
    a, p = i.latest_admission, i.latest_placement
    student_metric = i.campus.get("students")
    fee_metric = i.commercial.get("average_fee")
    criteria = OpportunityCriteria.model_validate(st.session_state.get("opportunity-criteria", {}))
    opportunity = partnership_opportunity(i, criteria)
    st.caption(f"{i.university} · {i.ownership} · Established {i.established or 'unavailable'} · AISHE {i.aishe_code or 'unavailable'} · {i.campus_status}")
    cards([
        {"label": "Latest approved annual intake", "value": fmt(a.intake if a else None), "icon": ":material/domain:", "help": source_help(i, a.intake_evidence_id) if a else "No intake supplied."},
        {"label": "Latest registered admissions", "value": fmt(a.registered if a else None), "icon": ":material/groups:", "help": source_help(i, a.registration_evidence_id) if a else "No admissions supplied."},
        {"label": "Annual intake utilisation", "value": fmt(s["utilisation"], "%", 1), "icon": ":material/donut_large:", "delta": f"{s['cagr']:+.1f}% admission CAGR" if s["cagr"] is not None else None, "help": source_help(i, a.intake_evidence_id, a.registration_evidence_id) if a else "No admissions supplied."},
        {"label": "Placement / eligible", "value": fmt(s["placement_percent"], "%", 1), "icon": ":material/work:", "help": source_help(i, p.evidence_id) if p else "Placement data unavailable."},
    ])
    st.caption(f"Admission year: {a.year if a else 'unavailable'} · Placement year: {p.year if p else 'unavailable'} · Total campus students: {fmt(s['students'])} · Campus capacity: {fmt(s['capacity'])} · Average annual fee: {money(s['fee'])}")
    with st.container(border=True):
        st.subheader("CEO view", icon=":material/space_dashboard:")
        trends = executive_trends(i)
        with st.container(horizontal=True):
            for label, trend in trends.items():
                st.metric(label, trend["direction"], width="stretch", help=trend["detail"] + "\n" + source_help(i, *trend["evidence_ids"]))
        institution_risks = [r for r in risk_indicators(i) if r.category == "Institution"]
        critical = sum(r.severity == "Critical" for r in institution_risks)
        attention = sum(r.severity == "Attention" for r in institution_risks)
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(f"{critical} critical indicators", color="red" if critical else "gray")
            st.badge(f"{attention} attention indicators", color="orange" if attention else "gray")
            st.badge(f"Commercial potential: {opportunity['label']}", color="violet" if i.demo else "blue")
        st.caption("Commercial potential uses the visible business criteria in Commercial. Partnership decision: requires diligence. Infrastructure trend is unavailable without comparable historical observations.")
        with st.container(horizontal=True):
            for row in current_authorities(i):
                status = authority_status(i, row)
                st.badge(f"{row.body} · {row.outcome} · {status}", color="green" if status == "Verified" else "violet" if i.demo else "orange")
        rankings = [r for r in i.accreditations if r.body == "NIRF"]
        if rankings:
            year = max(r.year for r in rankings)
            st.caption("Latest NIRF: " + " · ".join(f"{r.category}: {r.outcome} ({r.year}) · {i.source(r.evidence_id).status}" for r in rankings if r.year == year))
        else:
            st.caption("NIRF: unavailable; no ranking outcome is inferred.")
        executive_sources = [i.identity_evidence_id, *(m.evidence_id for m in i.campus.values()), *(m.evidence_id for m in i.commercial.values()), *(r.evidence_id for r in current_authorities(i)), *(r.evidence_id for r in rankings)]
        evidence_popover(i, executive_sources, "Executive snapshot evidence")
    if not i.demo:
        metric_sources = [student_metric.evidence_id if student_metric else None, a.intake_evidence_id if a else None, a.registration_evidence_id if a else None, p.evidence_id if p else None]
        periods = list(dict.fromkeys(i.source(sid).period for sid in metric_sources if sid and i.source(sid)))
        if periods:
            st.caption("Source reporting periods: " + " · ".join(periods) + ". Observation date does not establish that a count is current.")
    left, right = st.columns([1.65, 1], gap="large")
    with left:
        performance_chart(i)
    with right:
        with st.container(border=True):
            st.subheader("Partnership headroom")
            st.metric("Available annual intake seats", fmt(s["free_annual_seats"]), help="Latest approved annual intake minus recorded annual registrations, floored at zero.")
            st.metric("Available campus capacity", fmt(s["campus_headroom"]), help="Total campus capacity minus total students; this is not annual intake.")
            st.metric("Annual cohort gross", money(s["annual_cohort_revenue"]), help="Latest registered admissions × average annual fee, before deductions.\n" + source_help(i, a.registration_evidence_id if a else None, fee_metric.evidence_id if fee_metric else None))
            st.caption(f"Campus utilisation: {fmt(s['campus_utilisation'], '%', 1)} · Average annual fee: {money(s['fee'])}")
            st.badge("Opportunity requires diligence", icon=":material/travel_explore:", color="blue")
            st.caption("Model admission targets, fee realisation and your revenue share in Commercial.")
    left, right = st.columns([1.65, 1], gap="large")
    with left:
        with st.container(border=True):
            st.subheader("Institution at a glance")
            st.dataframe(pd.DataFrame({"Field": ["Location", "Established", "Ownership", "Affiliated university", "AISHE code", "Campus status"], "Profile": [f"{i.city}, {i.state}", str(i.established or "Not supplied"), i.ownership, i.university, i.aishe_code or "Not supplied", i.campus_status]}), hide_index=True, height="auto")
            evidence_popover(i, [i.identity_evidence_id], "Profile evidence")
        with st.container(border=True):
            st.subheader("Regulatory snapshot")
            records = current_authorities(i)
            if records:
                st.dataframe(pd.DataFrame([{"Authority": r.body, "Scope": r.category, "Recorded outcome": r.outcome, "Validity": str(r.valid_until or "Not supplied"), "Evidence status": authority_status(i, r), "Evidence": r.evidence_id} for r in records]), hide_index=True)
            else:
                st.caption("Recognition, affiliation and accreditation have not been established.")
            st.caption("Listing, institutional accreditation and programme accreditation each have their own scope.")
    with right:
        st.subheader("Priority follow-up")
        risks = [r for r in risk_indicators(i) if r.category == "Institution"]
        for risk in risks[:3]:
            risk_card(i, risk)
        st.caption("Open Risk centre for all indicators and promoter follow-up. There is no composite college score.")
    with st.container(horizontal=True):
        with st.popover("Export executive brief", icon=":material/download:"):
            st.download_button("Markdown brief", executive_brief(i, criteria), f"{filename(i)}-brief.md", "text/markdown", icon=":material/description:")
            st.download_button("Printable HTML brief", printable_brief(i, criteria), f"{filename(i)}-brief.html", "text/html", icon=":material/print:")
            st.download_button("Full profile JSON", i.model_dump_json(indent=2), f"{filename(i)}.json", "application/json", icon=":material/data_object:")
            st.caption("Open the HTML brief in your browser and use Print → Save as PDF.")
    note_form(i)
