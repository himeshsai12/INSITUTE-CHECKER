import altair as alt
import pandas as pd
import streamlit as st

from iip.analytics import snapshot, risk_indicators, fmt, money
from iip.ui import repo, cards, chart_frame, source_help


def compare():
    st.caption("INSTITUTION INTELLIGENCE / CAMPUS COMPARISON")
    st.title("Compare campuses")
    st.caption("Compare operating indicators and evidence coverage across up to four institutions.")
    profiles = repo().institutions()
    mapping = {i.id: i for i in profiles}
    default = [sid for sid in [st.session_state.get("selected_id", "aster"), "meridian"] if sid in mapping]
    ids = st.multiselect("Institutions", list(mapping), default=list(dict.fromkeys(default)), max_selections=4, format_func=lambda sid: f"{mapping[sid].name} · {mapping[sid].city} {'(demo)' if mapping[sid].demo else ''}")
    if not ids:
        st.caption("Select one to four campuses.")
        return
    selected = [mapping[sid] for sid in ids]
    if any(i.demo for i in selected):
        st.caption(":violet-badge[Contains illustrative demo profiles] Demo institutions and figures are fictional.")
    rows = []
    for i in selected:
        s = snapshot(i)
        rows.append({"Institution": i.name, "City": i.city, "Students": s["students"], "Annual intake utilisation %": s["utilisation"], "Placement / eligible %": s["placement_percent"], "Admission CAGR %": s["cagr"], "Annual fee": money(s["fee"]), "Annual free seats": s["free_annual_seats"], "Verified sources": sum(e.status == "Verified" for e in i.evidence), "Total sources": len(i.evidence), "Evidence mode": "Demo" if i.demo else "Real profile"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={k: st.column_config.NumberColumn(format="%.1f%%") for k in ["Annual intake utilisation %", "Placement / eligible %", "Admission CAGR %"]})
    mode = st.segmented_control("Compare measure", ["Annual intake utilisation", "Placement / eligible", "Admission CAGR"], default="Annual intake utilisation") or "Annual intake utilisation"
    keys = {"Annual intake utilisation": "utilisation", "Placement / eligible": "placement_percent", "Admission CAGR": "cagr"}
    values = pd.DataFrame([{"Institution": i.name, "Value": snapshot(i)[keys[mode]]} for i in selected]).dropna(subset=["Value"])
    if not values.empty:
        with st.container(border=True):
            chart_frame(alt.Chart(values).mark_bar(cornerRadiusEnd=5).encode(x=alt.X("Value:Q", title=f"{mode} (%)"), y=alt.Y("Institution:N", title=None), color=alt.Color("Institution:N", legend=None), tooltip=["Institution:N", alt.Tooltip("Value:Q", format=".1f")]), 240)
    st.caption("Indicators retain their original periods and definitions. Different reporting years or eligibility rules can limit comparability; review each campus source before deciding.")
    for i in selected:
        with st.expander(f"Evidence and reporting periods · {i.name}"):
            a, p = i.latest_admission, i.latest_placement
            st.caption(f"Admission period: {a.year if a else 'Unavailable'} · placement period: {p.year if p else 'Unavailable'}")
            st.write(source_help(i, a.intake_evidence_id if a else None, a.registration_evidence_id if a else None, p.evidence_id if p else None))


def watchlist():
    st.caption("INSTITUTION INTELLIGENCE / SAVED CAMPUSES")
    st.title("Your watchlist")
    st.caption("A persistent shortlist with diligence indicators and internal notes.")
    watched = repo().watched()
    profiles = [i for i in repo().institutions() if i.id in watched]
    cards([
        {"label": "Saved campuses", "value": len(profiles)},
        {"label": "Critical institution indicators", "value": sum(r.severity == "Critical" and r.category == "Institution" for i in profiles for r in risk_indicators(i))},
        {"label": "Available annual seats", "value": fmt(sum(snapshot(i)["free_annual_seats"] or 0 for i in profiles)) if profiles else "—", "help": "Sum of available recorded annual seats. Campuses without admission data do not contribute."},
    ])
    if not profiles:
        st.info("Use Add to watchlist on any institution page to build your shortlist.", icon=":material/bookmark_add:")
    for i in profiles:
        s = snapshot(i)
        with st.container(border=True):
            with st.container(horizontal=True, horizontal_alignment="distribute"):
                st.subheader(i.name)
                if st.button("Remove", key=f"remove-{i.id}", icon=":material/bookmark_remove:", type="tertiary"):
                    repo().toggle_watch(i.id)
                    st.rerun()
            st.caption(f"{i.city}, {i.state} · {'Fictional demo' if i.demo else 'Real profile'} · admissions utilisation {fmt(s['utilisation'], '%', 1)} · placements {fmt(s['placement_percent'], '%', 1)}")
            st.caption("Underlying source dates and statuses are available in the institution profile and source register.")
            for risk in [r for r in risk_indicators(i) if r.category == "Institution"][:2]:
                st.markdown(f":orange-badge[{risk.severity}] {risk.title}")
            note = repo().note(i.id)
            if note:
                st.write(note)
            if st.button("Open campus profile", key=f"open-{i.id}", icon=":material/arrow_forward:"):
                st.session_state["pending_selection"] = i.id
                st.session_state["pending_clear_search"] = True
                st.switch_page("app_pages/overview.py")
