import pandas as pd
import streamlit as st

from iip.analytics import risk_indicators
from iip.executive import current_authorities, authority_status
from iip.ui import heading, cards, evidence_popover, risk_card, note_form, data_gap


def promoters(i):
    heading(i, "Promoter & public records", "Entity identity, associations and procedural status")
    promoter = i.promoter
    with st.container(border=True):
        st.subheader(promoter.organisation)
        st.caption(f"Established: {promoter.established or 'Not disclosed'}")
        evidence_popover(i, [promoter.evidence_id], "Promoter identity evidence")
        left, right = st.columns(2)
        with left:
            st.markdown("**Promoter / director names**")
            st.write("\n\n".join(promoter.names) or "Not disclosed")
            st.markdown("**Board and key management**")
            st.write("\n\n".join(promoter.board) or "Not disclosed")
        with right:
            st.markdown("**Other educational institutions**")
            st.write("\n\n".join(promoter.other_institutions) or "Not established")
            st.markdown("**Previous educational institutions**")
            st.write("\n\n".join(promoter.previous_institutions) or "Not established")
            st.markdown("**Other associated businesses**")
            st.write("\n\n".join(promoter.businesses) or "Not established")
    st.subheader("Public record register")
    st.caption("A complaint, FIR, charge, prosecution, conviction, acquittal and civil dispute are different procedural stages. A name match alone does not establish identity.")
    if not promoter.records:
        data_gap("No public records have been supplied. This does not establish that the promoter has no litigation or regulatory history.")
    for record in promoter.records:
        with st.container(border=True):
            st.markdown(f"**{record.title}**")
            st.badge(record.stage, color="violet")
            st.caption(f"Reference: {record.reference} · Recorded date: {record.date}")
            st.write(record.description)
            st.caption("No other legal outcome or culpability is inferred from this record.")
            evidence_popover(i, [record.evidence_id], "Public record source")
    note_form(i)


def risks(i):
    heading(i, "Risk & red-flag centre", "Explainable screening with evidence and next actions")
    all_risks = risk_indicators(i)
    institution_risks = [r for r in all_risks if r.category == "Institution"]
    cards([
        {"label": "Critical indicators", "value": sum(r.severity == "Critical" for r in institution_risks)},
        {"label": "Attention indicators", "value": sum(r.severity == "Attention" for r in institution_risks)},
        {"label": "Data gaps", "value": sum(r.severity == "Data gap" for r in institution_risks)},
        {"label": "Promoter records to review", "value": sum(r.category == "Promoter" for r in all_risks)},
    ])
    st.caption("Counts describe screening triggers, not a college rating. Thresholds and evidence are visible; leadership makes the partnership decision.")
    reviewed = [r for r in current_authorities(i) if authority_status(i, r) == "Verified"]
    with st.expander("Verified regulatory evidence", expanded=bool(reviewed), icon=":material/fact_check:"):
        if reviewed:
            for row in reviewed:
                source = i.source(row.evidence_id)
                st.badge(f"{row.body} · {row.category} · {row.outcome}", color="green")
                st.caption(f"Reviewed {source.reviewed_on} by {source.reviewer} · Recorded validity: {row.valid_until or 'Not supplied; current validity needs confirmation'}")
            evidence_popover(i, [r.evidence_id for r in reviewed], "Reviewed regulatory sources")
        else:
            st.caption("No current recorded authority outcome has independently reviewed evidence. Government origin alone does not establish verification.")
    categories = st.segmented_control("Diligence area", ["Institution", "Promoter"], default="Institution") or "Institution"
    levels = st.pills("Show severity", ["Critical", "Attention", "Data gap", "Review"], default=["Critical", "Attention", "Data gap", "Review"], selection_mode="multi")
    selected = [r for r in all_risks if r.category == categories and r.severity in (levels or [])]
    if not selected:
        st.info("No indicators match this filter. This does not certify that no risks exist.", icon=":material/filter_alt:")
    for risk in selected:
        risk_card(i, risk)
    with st.expander("Screening rules", icon=":material/rule:"):
        st.dataframe(pd.DataFrame([
            {"Indicator": "Admission discrepancy", "Trigger": "Absolute variance ≥ 10% of the college claim", "Severity": "Critical"},
            {"Indicator": "Student strength conflict", "Trigger": "Primary and disclosure counts differ; periods or scopes may differ", "Severity": "Attention"},
            {"Indicator": "Registrations exceed intake", "Trigger": "Latest registered students exceed approved annual intake", "Severity": "Critical"},
            {"Indicator": "Admission decline", "Trigger": "Admission CAGR < 0%", "Severity": "Attention"},
            {"Indicator": "Low intake utilisation", "Trigger": "Latest registrations ÷ approved intake < 60%", "Severity": "Attention"},
            {"Indicator": "Placement claim discrepancy", "Trigger": "Absolute claim gap ≥ 10 percentage points", "Severity": "Attention"},
            {"Indicator": "Placement decline", "Trigger": "Latest eligible-student rate > 5 percentage points below earliest", "Severity": "Attention"},
            {"Indicator": "Expired validity", "Trigger": "Recorded validity before today's IST date", "Severity": "Attention"},
            {"Indicator": "Adverse authority outcome", "Trigger": "Withdrawn, not approved, suspended or cancelled", "Severity": "Critical"},
            {"Indicator": "Fee collection", "Trigger": "Collection efficiency < 85%", "Severity": "Attention"},
            {"Indicator": "Faculty attrition", "Trigger": "Faculty attrition > 20%", "Severity": "Attention"},
        ]), hide_index=True)
    note_form(i)
