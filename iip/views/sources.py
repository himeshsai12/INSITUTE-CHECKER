from datetime import datetime
from dataclasses import replace
from uuid import uuid4
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from iip.config import today, PROVIDER_LABELS
from iip.models import Evidence, Status, SourceType
from iip.research import ResearchService, ResearchResult, ResearchError, FOCUS, REGISTRY
from iip.repository import LimitReached
from iip.ui import repo, settings, COLORS, data_gap


def evidence_register(i):
    if not i:
        data_gap("Create or select a local institution profile first.")
        return
    st.caption(f"Evidence attached to {i.name}")
    if i.demo:
        st.caption(":violet-badge[Illustrative demo] Demo sources cannot be promoted to real verification. Create a real profile to collect and review evidence.")
    types = sorted({str(e.source_type) for e in i.evidence})
    left, right = st.columns(2)
    with left:
        statuses = st.multiselect("Verification status", [str(s) for s in Status], default=[str(s) for s in Status])
    with right:
        selected_types = st.multiselect("Source layer", types, default=types)
    filtered = [e for e in i.evidence if e.status in statuses and e.source_type in selected_types]
    if filtered:
        st.dataframe(pd.DataFrame([{"ID": e.id, "Source": e.title, "Layer": str(e.source_type), "Status": str(e.status), "Period": e.period, "Observed": str(e.observed_on), "Published": str(e.published_on or "Not supplied"), "Source URL": e.url, "Reviewer": e.reviewer or "Pending", "Reviewed on": str(e.reviewed_on) if e.reviewed_on else "Pending"} for e in filtered]), hide_index=True, column_config={"Source URL": st.column_config.LinkColumn("Source URL", display_text="Open source")})
        chosen_id = st.selectbox("Inspect source", [e.id for e in filtered], format_func=lambda sid: next(e.title for e in filtered if e.id == sid))
        e = i.source(chosen_id)
        with st.container(border=True):
            st.subheader(e.title)
            st.badge(str(e.status), color=COLORS[str(e.status)])
            st.caption(f"Observed {e.observed_on} · period {e.period} · {e.source_type}")
            if e.url:
                st.link_button("Open original source", e.url, icon=":material/open_in_new:")
            st.write(e.excerpt or "No supporting excerpt supplied.")
            if e.reviewer:
                st.caption(f"Reviewed by {e.reviewer} on {e.reviewed_on}: {e.review_note}")
        if not i.demo:
            with st.expander("Record an evidence review", icon=":material/fact_check:"):
                st.caption("Review the original document, exact institution identity, reporting period and the specific claim before marking it verified.")
                with st.form(f"review-{i.id}-{e.id}"):
                    status = st.selectbox("Review outcome", [str(Status.UNVERIFIED), str(Status.SELF_REPORTED), str(Status.VERIFIED)], index=0)
                    reviewer = st.text_input("Reviewer name", max_chars=150)
                    note = st.text_area("Review note and document reference", max_chars=4000)
                    if st.form_submit_button("Save review", type="primary", icon=":material/save:"):
                        if not reviewer.strip() or not note.strip():
                            st.error("Enter a reviewer name and review note.")
                        else:
                            repo().review_evidence(i.id, e.id, status, reviewer.strip(), note.strip())
                            st.success("Evidence review recorded in the audit log.")
                            st.rerun()
    else:
        st.caption("No evidence matches these filters.")
    if not i.demo:
        with st.expander("Add a source document", icon=":material/add_link:"):
            with st.form(f"source-add-{i.id}"):
                title = st.text_input("Document title", max_chars=300)
                source_type = st.selectbox("Source layer", [str(t) for t in SourceType])
                url = st.text_input("Source URL (optional for an internal document)", max_chars=2000)
                left, right = st.columns(2)
                with left:
                    period = st.text_input("Reporting period", placeholder="2025-26", max_chars=80)
                    observed = st.date_input("Date observed", value=today(), max_value=today())
                with right:
                    published = st.date_input("Publication date (if known)", value=None, max_value=today())
                    status = st.selectbox("Initial status", [str(Status.UNVERIFIED), str(Status.SELF_REPORTED)])
                excerpt = st.text_area("Supporting excerpt or internal reference", max_chars=6000)
                if st.form_submit_button("Add evidence", type="primary"):
                    if not title.strip() or not excerpt.strip():
                        st.error("Provide a title and supporting excerpt or internal reference.")
                    else:
                        try:
                            evidence = Evidence(id=f"E-{uuid4().hex[:10]}", title=title.strip(), source_type=source_type, status=status, url=url.strip() or None, observed_on=observed, published_on=published, period=period.strip() or "Not specified", excerpt=excerpt.strip())
                            repo().add_evidence(i.id, evidence)
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))


def live_research(i):
    configuration = settings()
    choices = ["auto", *PROVIDER_LABELS]
    selected_provider = st.selectbox("AI provider for this research", choices, index=choices.index(configuration.provider) if configuration.provider in choices else 0, format_func=lambda provider: "Auto — first configured provider" if provider == "auto" else f"{PROVIDER_LABELS[provider]} · {'key configured' if configuration.provider_key(provider) else 'key not configured'}", key="research-provider", persist_state="session")
    configuration = replace(configuration, provider=selected_provider)
    if not configuration.research_enabled:
        st.info("Add TAVILY_API_KEY for source discovery, or use OpenAI or Groq GPT-OSS with built-in search. Configure keys in .env or Streamlit secrets; the demo works without keys.", icon=":material/key:")
    st.caption("OpenAI and Groq GPT-OSS can discover sources with their built-in search. Tavily can supply sources to any supported AI provider; Gemini, Claude and OpenRouter use that workflow. Searches run only on submission.")
    if configuration.synthesis_enabled:
        st.caption(f"AI synthesis: {PROVIDER_LABELS[configuration.selected_provider]} · {configuration.selected_model}")
    else:
        st.caption("AI synthesis is disabled until a key for the selected provider is configured. Tavily source discovery can still run on its own.")
    with st.form("live-research"):
        default_query = st.session_state.get("local_search", "") or (f"{i.name}, {i.city}" if i and not i.demo else "")
        incoming_query = st.session_state.pop("pending_research_query", None)
        if incoming_query is not None:
            st.session_state["research-query"] = incoming_query
        st.session_state.setdefault("research-query", default_query)
        query = st.text_input("Institution to research", key="research-query", persist_state="session", placeholder="College name, city or AISHE code", max_chars=250)
        focus = st.selectbox("Research focus", list(FOCUS))
        left, right = st.columns(2)
        with left:
            official = st.checkbox("Restrict discovery to known regulator domains", value=False)
            synthesise = st.checkbox("Summarise discovered source documents", value=configuration.synthesis_enabled, disabled=not configuration.synthesis_enabled)
            fresh = st.checkbox("Fetch latest sources now", value=True, help="Search the internet even if this institution has a saved result. Uses the normal daily request allowance.")
        with right:
            limit = st.slider("Requested source count", 3, 10, 6)
        submitted = st.form_submit_button("Research institution", type="primary", icon=":material/travel_explore:", disabled=not configuration.research_enabled)
    st.caption(f"Fresh search is selected by default. Turn it off to reuse results saved within {configuration.cache_hours} hours. Daily outbound request cap: {configuration.daily_limit}.")
    if submitted:
        with st.status("Researching institution…", expanded=True) as status:
            st.write("Retrieving current sources from the internet." if fresh else "Checking saved research, then retrieving cited sources if needed.")
            try:
                result = ResearchService(configuration, repo()).search(query, focus, official, limit, synthesise, force_refresh=fresh)
                st.session_state["research_result"] = result.model_dump(mode="json")
                status.update(label="Research ready — evidence review pending", state="complete", expanded=False)
            except (ResearchError, LimitReached) as exc:
                # Do not leave a previous institution's result visible after a failed search.
                st.session_state.pop("research_result", None)
                status.update(label="Research could not complete", state="error", expanded=False)
                st.error(str(exc))
    saved = st.session_state.get("research_result")
    if saved:
        result = ResearchResult.model_validate(saved)
        st.subheader(f"Research: {result.query}")
        st.caption(f"{result.provider} · {result.focus} · retrieved {result.observed_at} · {'cache hit' if result.cached else 'live retrieval'}")
        st.badge("Unverified research findings", color="orange", icon=":material/pending:")
        st.markdown(result.summary)
        source_map = {s.id: s for s in result.sources}
        for claim in result.claims:
            with st.container(border=True):
                st.markdown(f"**{claim.topic}**")
                st.write(claim.statement)
                st.caption(claim.caveat)
                with st.container(horizontal=True):
                    for sid in claim.source_ids:
                        source = source_map[sid]
                        st.link_button(f"[{sid}] Source", source.url, icon=":material/open_in_new:")
        if result.missing_information:
            with st.expander("Missing evidence and limitations", expanded=True):
                for gap in result.missing_information:
                    st.write(f"• {gap}")
        st.subheader("Discovered sources")
        for source in result.sources:
            with st.container(border=True):
                st.markdown(f"**[{source.id}] {source.title}**")
                st.caption(f"{urlparse(source.url).hostname} · {source.source_type} · Unverified")
                if source.snippet:
                    st.write(source.snippet)
                st.link_button("Open source", source.url, icon=":material/open_in_new:")
        st.download_button("Export research JSON", result.model_dump_json(indent=2), "institution-research.json", "application/json", icon=":material/download:")
        if i and not i.demo and result.sources:
            with st.expander(f"Attach a discovered source to {i.name}", icon=":material/add_link:"):
                with st.form("attach-research"):
                    sid = st.selectbox("Source to attach", [s.id for s in result.sources], format_func=lambda value: source_map[value].title)
                    identity_checked = st.checkbox("I checked that this source refers to the selected institution")
                    period = st.text_input("Document reporting period", max_chars=80)
                    if st.form_submit_button("Attach as unverified evidence"):
                        if not identity_checked:
                            st.error("Check institution identity before attaching evidence.")
                        else:
                            source = source_map[sid]
                            evidence = Evidence(id=f"E-{uuid4().hex[:10]}", title=source.title, url=source.url, source_type=source.source_type, observed_on=datetime.fromisoformat(result.observed_at).date(), period=period.strip() or "Not specified", excerpt=source.snippet or "Discovered by live research. Review the original document for specific claims.")
                            repo().add_evidence(i.id, evidence)
                            st.success("Source attached as unverified evidence. Metrics must be entered separately with this reference.")
    with st.expander("Primary source directories", icon=":material/account_balance:"):
        for name, description, url in REGISTRY:
            st.link_button(f"{name} · {description}", url)
        st.caption("These are public directories. University registration portals and some regulator records may need authorised access or manual document collection; this app does not bypass access controls.")


def render():
    st.caption("INSTITUTION INTELLIGENCE / EVIDENCE WORKSPACE")
    st.title("Sources & research")
    st.caption("Source → reporting period → observation date → review status")
    i = None if st.session_state.get("search_no_match") else repo().get(st.session_state.get("selected_id", "aster"))
    st.session_state.setdefault("source-workspace-mode", "Live research")
    mode = st.segmented_control("Evidence workspace", ["Evidence register", "Live research", "Review log"], key="source-workspace-mode")
    if mode == "Live research":
        live_research(i)
    elif mode == "Review log":
        entries = repo().audit(i.id) if i else []
        st.caption("Local audit trail of profile imports, evidence reviews and saved notes. This workspace uses reviewer attribution, without authenticated multi-user approval.")
        if entries:
            st.dataframe(pd.DataFrame(entries).rename(columns={"action": "Action", "detail": "Detail", "created_at": "Time (IST)"}), hide_index=True)
        else:
            st.caption("No review events yet.")
    else:
        evidence_register(i)
