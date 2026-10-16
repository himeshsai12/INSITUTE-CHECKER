import altair as alt
import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from iip.analytics import fmt, recent_records
from iip.config import load_settings
from iip.models import Status
from iip.repository import Repository

COLORS = {"Critical": "red", "Attention": "orange", "Data gap": "gray", "Review": "violet", "Verified": "green", "Unverified": "orange", "Self-reported": "blue", "Demo": "violet"}


def settings():
    try:
        secrets = st.secrets.to_dict()
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        secrets = {}
    return load_settings(secrets)


@st.cache_resource(max_entries=4)
def repository(path):
    repo = Repository(path)
    repo.seed_demo()
    return repo


def repo():
    return repository(str(settings().database))


def current():
    if st.session_state.get("search_no_match"):
        st.title("Find an institution")
        st.info("No local profile matches your search. Open Sources & research for live discovery, or create a real profile in Workspace & API.", icon=":material/search:")
        if st.button("Research this institution", type="primary", icon=":material/travel_explore:"):
            st.session_state["pending_research_query"] = st.session_state.get("local_search", "")
            st.session_state["source-workspace-mode"] = "Live research"
            st.switch_page("app_pages/sources.py")
        st.stop()
    institution = repo().get(st.session_state.get("selected_id", "aster"))
    if not institution:
        st.error("Select an institution in the sidebar.")
        st.stop()
    return institution


def source_help(i, *ids):
    lines = []
    for sid in dict.fromkeys(filter(None, ids)):
        e = i.source(sid)
        if e:
            lines.append(f"[{e.id}] {e.title} · {e.source_type} · {e.status} · observed {e.observed_on} · period {e.period}")
            if e.reviewed_on:
                lines.append(f"Reviewed {e.reviewed_on} by {e.reviewer}: {e.review_note}")
    return "\n\n".join(lines) or "Source not supplied."


def heading(i, title, subtitle):
    st.caption(":material/hub: INSTITUTION INTELLIGENCE / DILIGENCE WORKSPACE")
    st.title(title, anchor=False)
    st.caption(f"{i.name} · {i.city}, {i.state} · {subtitle}")
    if i.demo:
        st.caption(":violet-badge[Illustrative demo] All names, records and figures in this profile are fictional.")
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
        verified = sum(e.status == Status.VERIFIED for e in i.evidence)
        st.badge(f"{verified} / {len(i.evidence)} sources reviewed as verified", icon=":material/fact_check:", color="green" if verified else "gray")
        watched = i.id in repo().watched()
        if st.button("Saved to watchlist" if watched else "Add to watchlist", icon=":material/bookmark:" if watched else ":material/bookmark_add:", key=f"watch-{i.id}", type="tertiary"):
            added = repo().toggle_watch(i.id)
            st.toast("Added to watchlist" if added else "Removed from watchlist")
            st.rerun()


def evidence_popover(i, ids=None, label="View underlying evidence"):
    selected = [e for e in i.evidence if ids is None or e.id in ids]
    with st.popover(label, icon=":material/receipt_long:"):
        if not selected:
            st.caption("Evidence not supplied.")
        for e in selected:
            st.markdown(f"**{e.title}**")
            st.badge(str(e.status), color=COLORS[str(e.status)])
            st.caption(f"[{e.id}] · {e.source_type} · {e.period} · observed {e.observed_on}")
            if e.url:
                st.link_button("Open source", e.url, icon=":material/open_in_new:")
            if e.excerpt:
                st.caption(e.excerpt)
            if e.reviewed_on:
                st.caption(f"Reviewed {e.reviewed_on} by {e.reviewer} · {e.review_note}")


def cards(items):
    with st.container(horizontal=True):
        for item in items:
            st.metric(border=True, width="stretch", **item)


def chart_frame(chart, height=280):
    st.altair_chart(
        chart.properties(height=height, background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(gridColor="#22344F", gridOpacity=0.7, gridDash=[3, 5], domainColor="#334968", tickColor="#334968", labelColor="#ACBED5", titleColor="#ACBED5", labelFontSize=11)
        .configure_legend(orient="bottom", title=None, labelColor="#C4D4E9", symbolStrokeWidth=3)
    )


def admission_df(i, latest_five=False):
    from iip.analytics import percent
    records = recent_records(i.admissions) if latest_five else sorted(i.admissions, key=lambda r: r.year)
    return pd.DataFrame([{"Academic year": r.year, "Approved intake": r.intake, "Registered admissions": r.registered, "College claim": r.claimed, "Utilisation %": percent(r.registered, r.intake), "Intake evidence": r.intake_evidence_id, "Registration evidence": r.registration_evidence_id, "Registration status": str(i.source(r.registration_evidence_id).status) if i.source(r.registration_evidence_id) else "Unavailable", "Claim evidence": r.claim_evidence_id} for r in records])


def placement_df(i, latest_five=False):
    from iip.analytics import percent
    records = recent_records(i.placements) if latest_five else sorted(i.placements, key=lambda r: r.year)
    return pd.DataFrame([{"Year": str(r.year), "Batch size": r.batch_size, "Eligible": r.eligible, "Placed": r.placed, "Placement %": percent(r.placed, r.eligible), "Advertised %": r.claimed_percent, "Highest LPA": r.highest_lpa, "Average LPA": r.average_lpa, "Median LPA": r.median_lpa, "Evidence": r.evidence_id, "Status": str(i.source(r.evidence_id).status)} for r in records])


def line_chart(data, x, ys, percent_axis=False, height=280):
    long = data.melt(id_vars=[x], value_vars=ys, var_name="Measure", value_name="Value").dropna(subset=["Value"])
    chart = alt.Chart(long).mark_line(point=alt.OverlayMarkDef(size=60), strokeWidth=3).encode(
        x=alt.X(f"{x}:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Value:Q", title="Percent" if percent_axis else None, scale=alt.Scale(domain=[0, 100]) if percent_axis else alt.Scale(zero=True)),
        color=alt.Color("Measure:N", scale=alt.Scale(range=["#67E8F9", "#A78BFA", "#60A5FA", "#FBBF24"])),
        tooltip=[alt.Tooltip(f"{x}:O"), "Measure:N", alt.Tooltip("Value:Q", format=",.1f")],
    )
    chart_frame(chart, height)


def risk_card(i, risk):
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(risk.severity, color=COLORS[risk.severity])
            st.markdown(f"**{risk.title}**")
        st.write(risk.detail)
        st.caption(f"Next action: {risk.action}")
        if risk.evidence_ids:
            evidence_popover(i, risk.evidence_ids, "Risk evidence")


def data_gap(message):
    st.info(message, icon=":material/database:")


def note_form(i):
    with st.expander("Internal diligence notes", icon=":material/edit_note:"):
        with st.form(f"note-form-{i.id}"):
            note = st.text_area("Management discussion, campus visit or next action", value=repo().note(i.id), height=140, max_chars=20000, key=f"note-{i.id}")
            if st.form_submit_button("Save note", icon=":material/save:"):
                repo().save_note(i.id, note)
                st.success("Note saved in your local workspace.")
