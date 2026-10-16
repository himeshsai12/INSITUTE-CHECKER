import pandas as pd
import streamlit as st

from iip.analytics import snapshot, scenario, fmt, money
from iip.executive import OpportunityCriteria, partnership_opportunity, opportunity_rows
from iip.ui import heading, cards, evidence_popover, source_help


def opportunity_assessment(i):
    st.subheader("Partnership opportunity")
    st.caption("Set your business criteria. The starting values are illustrative assumptions; adjust them to your organisation's requirements. They apply across profiles during this session and are included in executive exports.")
    criteria = OpportunityCriteria.model_validate(st.session_state.get("opportunity-criteria", {}))
    with st.form(f"opportunity-criteria-{i.id}"):
        left, middle, right = st.columns(3)
        with left:
            seats = st.number_input("Minimum available annual seats", min_value=1, value=criteria.minimum_seats, step=10)
        with middle:
            fee = st.number_input("Minimum average annual fee (₹)", min_value=0.0, value=float(criteria.minimum_fee), step=10000.0)
        with right:
            collection = st.number_input("Minimum collection efficiency (%)", min_value=0.0, max_value=100.0, value=float(criteria.minimum_collection), step=1.0)
        if st.form_submit_button("Apply business criteria", type="primary", icon=":material/rule:"):
            criteria = OpportunityCriteria(minimum_seats=seats, minimum_fee=fee, minimum_collection=collection)
            st.session_state["opportunity-criteria"] = criteria.model_dump()
    result = partnership_opportunity(i, criteria)
    st.badge(f"Commercial potential: {result['label']}", color="violet" if i.demo else "blue")
    st.dataframe(pd.DataFrame(opportunity_rows(result)), hide_index=True)
    st.caption("High = all three criteria met; Medium = one or two; Low = none. Any missing input gives Insufficient data. This is a commercial screen, not a college rating or partnership approval. Decision: requires diligence; review regulatory, institution and promoter findings separately.")
    evidence_popover(i, [sid for check in result["checks"] for sid in check["evidence_ids"]], "Opportunity input evidence")
    import json
    st.download_button("Export opportunity and criteria", json.dumps(result, indent=2), f"{i.id}-opportunity.json", "application/json", icon=":material/download:")


@st.fragment
def scenario_builder(i):
    latest = i.latest_admission
    st.subheader("Partnership scenario")
    st.caption("These are editable assumptions. Targets use annual intake, and scenarios do not change the underlying profile.")
    if latest:
        st.caption(f"Initial intake assumption uses the latest available record: {latest.year}. Check the current approved intake before using this scenario.")
    with st.form(f"scenario-{i.id}"):
        left, right = st.columns(2)
        with left:
            intake = st.number_input("Annual approved intake", min_value=0, value=latest.intake if latest else 0, step=60)
            current_admissions = st.number_input("Current annual admissions", min_value=0, value=latest.registered if latest and latest.registered is not None else 0, step=10)
            target = st.slider("Target annual intake utilisation (%)", 0, 100, 85)
            fee = st.number_input("Average annual fee (₹)", min_value=0, value=int(i.value("commercial", "average_fee") or 0), step=10000)
        with right:
            collection = st.slider("Collection efficiency (%)", 0, 100, int(i.value("commercial", "collection_percent") or 0))
            scholarship = st.slider("Scholarship reduction (%)", 0, 100, int(i.value("commercial", "scholarship_percent") or 0))
            discount = st.slider("Additional discount (%)", 0, 100, int(i.value("commercial", "discount_percent") or 0))
            refund = st.slider("Refund reduction (%)", 0, 100, int(i.value("commercial", "refund_percent") or 0))
            share = st.slider("Partner revenue share (%)", 0, 100, 30)
        submitted = st.form_submit_button("Calculate scenario", type="primary", icon=":material/calculate:")
    state_key = f"scenario-result-{i.id}"
    if submitted:
        st.session_state[state_key] = {"inputs": {"annual_intake": intake, "current_admissions": current_admissions, "target_percent": target, "fee": fee, "collection_percent": collection, "scholarship_percent": scholarship, "discount_percent": discount, "refund_percent": refund, "share_percent": share}, "result": scenario(intake, current_admissions, target, fee, collection, scholarship, discount, refund, share)}
    saved = st.session_state.get(state_key)
    if not saved:
        st.caption("Submit assumptions to generate an auditable scenario. Supply any missing inputs explicitly.")
        return
    result = saved["result"]
    cards([
        {"label": "Target annual admissions", "value": fmt(result["target_admissions"]), "delta": f"{result['incremental_admissions']:,} incremental", "delta_color": "off"},
        {"label": "Gross annual cohort revenue", "value": money(result["gross"])},
        {"label": "Estimated net collections", "value": money(result["net"])},
        {"label": "Estimated partner revenue", "value": money(result["partner_revenue"])},
    ])
    st.caption("Net = gross × (1 − scholarship) × (1 − discount) × collection × (1 − refund). Partner revenue = net × revenue share. Reductions are sequential assumptions; they do not represent audited accounts.")
    st.caption(f"Incremental gross before deductions: {money(result['incremental_gross'])}. The saved result reflects the last submitted assumptions.")
    import json
    st.download_button("Export scenario and assumptions", json.dumps(saved, indent=2), f"{i.id}-scenario.json", "application/json", icon=":material/download:")


def render(i):
    heading(i, "Commercial intelligence", "Revenue drivers and partnership scenario modelling")
    s = snapshot(i)
    cards([
        {"label": "Addressable students", "value": fmt(i.value("commercial", "addressable_students")), "help": source_help(i, i.commercial["addressable_students"].evidence_id) if "addressable_students" in i.commercial else "Unavailable"},
        {"label": "Average annual fee", "value": money(s["fee"]), "help": source_help(i, i.commercial["average_fee"].evidence_id) if "average_fee" in i.commercial else "Unavailable"},
        {"label": "Collection efficiency", "value": fmt(i.value("commercial", "collection_percent"), "%", 1), "help": source_help(i, i.commercial["collection_percent"].evidence_id) if "collection_percent" in i.commercial else "Unavailable"},
        {"label": "Annual capacity headroom", "value": fmt(s["free_annual_seats"]), "help": "Approved annual intake minus recorded annual admissions.\n"+source_help(i, i.latest_admission.intake_evidence_id, i.latest_admission.registration_evidence_id) if i.latest_admission else "Unavailable"},
    ])
    with st.expander("Financial evidence and fee schedule", expanded=True, icon=":material/payments:"):
        labels = {"average_fee": "Average annual fee", "revenue_per_student": "Recorded revenue per student", "collection_percent": "Collection efficiency %", "outstanding_fees": "Outstanding fees", "scholarship_percent": "Scholarship %", "discount_percent": "Discount %", "refund_percent": "Refund %", "addressable_students": "Addressable students"}
        rows = []
        for key, label in labels.items():
            m = i.commercial.get(key)
            e = i.source(m.evidence_id) if m else None
            rows.append({"Parameter": label, "Recorded value": money(m.value) if m and key in {"average_fee", "revenue_per_student", "outstanding_fees"} else fmt(m.value if m else None, digits=1 if key.endswith("percent") else 0), "Evidence": e.id if e else "—", "Status": str(e.status) if e else "Unavailable", "Period": e.period if e else "—"})
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        evidence_popover(i, [m.evidence_id for m in i.commercial.values()], "Financial source evidence")
        if i.courses:
            st.dataframe(pd.DataFrame([{"Course": c.name, "Academic year": c.year or "Not specified", "Annual fee": money(c.annual_fee), "Registered admissions": c.admissions, "Reporting period": i.source(c.evidence_id).period, "Evidence": c.evidence_id} for c in i.courses]), hide_index=True)
    opportunity_assessment(i)
    scenario_builder(i)
