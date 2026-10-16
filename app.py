"""Streamlit entry point: run with python -m streamlit run app.py."""
import streamlit as st

from iip.analytics import search_institutions
from iip.config import ROOT
from iip.ui import repo, settings

st.set_page_config(page_title="Institution Intelligence", page_icon=":material/account_balance:", layout="wide", initial_sidebar_state="expanded")
st.logo(str(ROOT / "assets" / "iip-logo.svg"), icon_image=str(ROOT / "assets" / "iip-mark.svg"), size="large")
st.session_state.setdefault("selected_id", "aster")
st.session_state.setdefault("search_no_match", False)
if st.session_state.pop("pending_clear_search", False):
    st.session_state["local_search"] = ""
pending = st.session_state.pop("pending_selection", None)
if pending:
    st.session_state["selected_id"] = pending
    st.session_state["profile-picker"] = pending

profiles = repo().institutions()
query = st.text_input("Search college / university", placeholder="Search by college name, AISHE code, university, city or promoter…", key="local_search", icon=":material/search:", max_chars=250)
open_live_research = st.button("Live internet research", icon=":material/travel_explore:", key="open-live-research")
st.caption("The search above filters saved profiles. Live internet research finds current sources for any institution.")
with st.sidebar:
    st.caption("One search. One profile. One executive view.")
    matching = search_institutions(profiles, query)
    st.session_state["search_no_match"] = not bool(matching)
    if matching:
        options = [i.id for i in matching]
        mapping = {i.id: i for i in matching}
        if st.session_state.get("profile-picker") is not None and st.session_state["profile-picker"] not in options:
            st.session_state["profile-picker"] = st.session_state["selected_id"] if st.session_state["selected_id"] in options else options[0]
        selected = st.selectbox("Selected institution", options, index=options.index(st.session_state["selected_id"]) if st.session_state["selected_id"] in options else 0, format_func=lambda sid: mapping[sid].name, key="profile-picker", bind="query-params")
        st.session_state["selected_id"] = selected
        st.caption(f"{mapping[selected].city}, {mapping[selected].state}")
        st.badge("Illustrative demo" if mapping[selected].demo else "Real institution profile", color="violet" if mapping[selected].demo else "blue")
    else:
        st.caption("No local match. Use Sources & research for live discovery.")

navigation = st.navigation({
    "Intelligence": [
        st.Page("app_pages/overview.py", title="Executive overview", icon=":material/dashboard:", default=True),
        st.Page("app_pages/admissions.py", title="Admissions", icon=":material/trending_up:"),
        st.Page("app_pages/placements.py", title="Placements", icon=":material/work:"),
        st.Page("app_pages/accreditation.py", title="Ranking & accreditation", icon=":material/verified:"),
        st.Page("app_pages/campus.py", title="Campus health", icon=":material/school:"),
        st.Page("app_pages/commercial.py", title="Commercial", icon=":material/payments:"),
        st.Page("app_pages/promoters.py", title="Promoter & public records", icon=":material/groups:"),
        st.Page("app_pages/risks.py", title="Risk centre", icon=":material/policy:"),
    ],
    "Workspace": [
        st.Page("app_pages/sources.py", title="Sources & research", icon=":material/travel_explore:"),
        st.Page("app_pages/compare.py", title="Compare campuses", icon=":material/compare_arrows:"),
        st.Page("app_pages/watchlist.py", title="Watchlist", icon=":material/bookmarks:"),
        st.Page("app_pages/settings.py", title="Workspace & API", icon=":material/tune:"),
    ],
}, expanded=True)

with st.sidebar:
    configuration = settings()
    st.caption(":material/cloud: Live research configured" if configuration.research_enabled else ":material/key: Add API keys to enable live research")
    st.caption("Evidence before decisions · Local workspace")

if open_live_research:
    st.session_state["pending_research_query"] = query
    st.session_state["source-workspace-mode"] = "Live research"
    st.switch_page("app_pages/sources.py")

navigation.run()
