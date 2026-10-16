import json
from uuid import uuid4

import pandas as pd
import streamlit as st

from iip.config import today, PROVIDER_LABELS
from iip.importing import parse_profiles
from iip.models import Institution, Evidence, Admission, Placement, Metric, Accreditation, Course, Recruiter, LegalRecord, Promoter, SourceType
from iip.ui import repo, settings, cards, data_gap

CAMPUS_KEYS = ["students", "students_disclosure", "capacity", "faculty", "attendance_percent", "pass_percent", "backlogs", "dropout_percent", "graduation_percent", "progression_percent", "faculty_attrition_percent", "land_acres", "built_up_sqft", "classrooms", "labs", "library_books", "hostel_capacity", "hostel_occupancy", "sports_facilities", "transport_vehicles"]
COMMERCIAL_KEYS = ["average_fee", "revenue_per_student", "collection_percent", "outstanding_fees", "scholarship_percent", "discount_percent", "refund_percent", "addressable_students"]


def api_settings():
    configuration = settings()
    usage = repo().usage()
    cards([
        {"label": "Today's outbound requests", "value": f"{usage['requests']} / {configuration.daily_limit}"},
        {"label": "Cache hits today", "value": usage["cache_hits"]},
        {"label": "AI input tokens", "value": f"{usage['input_tokens']:,}"},
        {"label": "AI output tokens", "value": f"{usage['output_tokens']:,}"},
    ])
    st.caption(f"Usage day: {today()} (IST) · failed attempts: {usage['failed']}. Outbound attempts include one possible retry; cache hits do not consume the quota.")
    with st.container(border=True):
        st.subheader("API connections")
        st.dataframe(pd.DataFrame([
            {"Provider": "Tavily", "Configuration": "Key configured" if configuration.tavily_key else "Key not configured", "Purpose": "Source discovery"},
            *[{"Provider": label, "Configuration": "Key configured" if configuration.provider_key(provider) else "Key not configured", "Purpose": "Cited synthesis or built-in search" if provider in {"openai", "groq"} else "Cited synthesis of Tavily sources"} for provider, label in PROVIDER_LABELS.items()],
        ]), hide_index=True)
        st.caption("Configured means a key is present; validity and account permissions are checked by the provider when research runs.")
        st.markdown("Copy **.env.example** to **.env**, then add your keys locally. On Streamlit hosting, use the secrets manager with the same variable names.")
        st.code("AI_PROVIDER=gemini\nGEMINI_API_KEY=your_gemini_key_here\nTAVILY_API_KEY=your_search_key_here\nGEMINI_MODEL=gemini-3.8-flash\nRESEARCH_CACHE_HOURS=24\nDAILY_API_REQUEST_LIMIT=30", language="bash")
        st.caption("Supported AI_PROVIDER values: auto, openai, gemini, anthropic, groq, openrouter. Use ANTHROPIC_API_KEY, GROQ_API_KEY or OPENROUTER_API_KEY for the respective provider. The Live research provider selector can override the configured default for a search.")
        st.caption("Keys are never displayed or stored in the SQLite database. Local .env and Streamlit secrets files are excluded from version control.")
        st.write(f"Selected AI provider: **{PROVIDER_LABELS.get(configuration.selected_provider, 'Not configured')}** · model: **{configuration.selected_model or 'Not configured'}** · cache TTL: **{configuration.cache_hours}h** · maximum output: **{configuration.max_tokens:,} tokens** · request timeout: **{configuration.timeout}s**")
    with st.container(border=True):
        st.subheader("Cost and performance controls")
        st.write("Local search, calculations, charts, comparison and executive exports use no paid APIs. Research runs on form submission. Tavily uses basic search without automatic depth escalation; synthesis uses bounded snippets and output tokens. Results are persisted in a credential-scoped cache with a maximum of 200 entries.")
        st.caption("The request cap is an outbound HTTP limit, not a currency budget. OpenAI web search can bill tool calls within one request; enforce a monetary budget in your provider account. No dollar cost estimate is invented.")
        if st.button("Clear research cache", icon=":material/cleaning_services:"):
            repo().clear_research_cache()
            st.session_state.pop("research_result", None)
            st.success("Research cache cleared. Institution data and audit history remain available.")
    st.caption("This is a local, single-workspace app bound to 127.0.0.1. SQLite stores profiles, excerpts, notes and research locally. Add authenticated access and a managed database before sharing a hosted diligence workspace.")


def create_profile():
    st.subheader("Start a real institution profile")
    st.caption("A new profile starts with unavailable metrics and an unverified identity record. Add evidence, then enter sourced measurements.")
    with st.form("create-profile"):
        name = st.text_input("Institution name", max_chars=250)
        left, right = st.columns(2)
        with left:
            city = st.text_input("City", max_chars=100)
            university = st.text_input("Affiliated university", max_chars=250)
            established = st.number_input("Established year (optional)", min_value=1800, max_value=today().year, value=None, step=1)
        with right:
            state = st.text_input("State", max_chars=100)
            ownership = st.selectbox("Ownership", ["Not disclosed", "Private educational trust", "Private society", "Private university", "Government", "Government aided", "Deemed university"])
            aishe = st.text_input("AISHE code (if available)", max_chars=50)
        website = st.text_input("Institution website (optional)", placeholder="https://…", max_chars=2000)
        reference = st.text_area("Identity source or internal reference", max_chars=2000)
        if st.form_submit_button("Create profile", type="primary", icon=":material/add:"):
            if len(name.strip()) < 3 or not city.strip() or not state.strip() or not reference.strip():
                st.error("Enter institution name, city, state and an identity reference.")
            else:
                try:
                    identity = Evidence(id="identity", title="Initial institution identity", source_type=SourceType.INTERNAL, observed_on=today(), excerpt=reference.strip(), url=website.strip() or None)
                    i = Institution(id=f"institution-{uuid4().hex[:10]}", name=name.strip(), city=city.strip(), state=state.strip(), university=university.strip() or "Not disclosed", ownership=ownership, established=established, aishe_code=aishe.strip() or None, website=website.strip() or None, identity_evidence_id=identity.id, evidence=[identity])
                    repo().save_many([i], "Institution created")
                    st.session_state["pending_selection"] = i.id
                    st.session_state["pending_clear_search"] = True
                    st.success(f"Created {i.name}. Select it in the sidebar, add evidence in Sources & research, then enter sourced records.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def add_records(i):
    if not i:
        data_gap("Select an institution first.")
        return
    st.subheader(f"Sourced records · {i.name}")
    if i.demo:
        st.info("This is a fictional demo profile. Create a real profile to enter operational data and independent evidence.")
        return
    if not i.evidence:
        data_gap("Add a source document in Sources & research before entering metrics.")
        return
    kind = st.selectbox("Record type", ["Admission year", "Placement year", "Campus metric", "Commercial metric", "Regulatory / ranking record", "Course", "Recruiter / internship", "Institution details", "Promoter profile", "Promoter public record"])
    choices = [e.id for e in i.evidence]
    def source(label, key):
        return st.selectbox(label, choices, format_func=lambda sid: f"[{sid}] {i.source(sid).title} · {i.source(sid).status}", key=key)
    st.caption("A populated value must cite an attached source. Matching admission/placement years, metrics and course name/level/year are replaced. Employer records match by name, year, location and internship/geography scope. Public records are appended.")
    with st.form(f"record-{i.id}-{kind}"):
        data = i.model_dump(mode="json")
        if kind == "Admission year":
            year = st.text_input("Academic year", value="2025-26", max_chars=7)
            intake = st.number_input("Approved intake", min_value=0, value=0, step=1)
            registered = st.number_input("University-registered admissions (optional)", min_value=0, value=None, step=1)
            claimed = st.number_input("College-claimed admissions (optional)", min_value=0, value=None, step=1)
            intake_sid = source("Approved intake evidence", "intake-evidence")
            registered_sid = source("University registration evidence", "registration-evidence")
            claim_sid = source("College claim evidence", "admission-claim-evidence")
        elif kind == "Placement year":
            year = st.number_input("Placement year", min_value=1900, max_value=today().year, value=2025, step=1)
            eligible = st.number_input("Eligible students", min_value=0, value=0, step=1)
            placed = st.number_input("Unique students placed", min_value=0, value=0, step=1)
            batch = st.number_input("Full batch size (optional)", min_value=0, value=None, step=1)
            advertised = st.number_input("Advertised placement % (optional)", min_value=0.0, max_value=100.0, value=None, step=0.1)
            highest = st.number_input("Highest package LPA (optional)", min_value=0.0, value=None)
            average = st.number_input("Average package LPA (optional)", min_value=0.0, value=None)
            median = st.number_input("Median package LPA (optional)", min_value=0.0, value=None)
            sid = source("Placement report evidence", "placement-evidence")
            claim_sid = source("Advertised claim evidence", "placement-claim-evidence")
        elif kind in {"Campus metric", "Commercial metric"}:
            section = "campus" if kind == "Campus metric" else "commercial"
            metric_key = st.selectbox("Metric", CAMPUS_KEYS if section == "campus" else COMMERCIAL_KEYS, format_func=lambda k: k.replace("_", " "))
            value = st.number_input("Recorded value (rupees for fees; 0–100 for percentages)", min_value=0.0, value=None)
            sid = source("Metric evidence", "metric-evidence")
        elif kind == "Regulatory / ranking record":
            body = st.selectbox("Authority", ["UGC", "AICTE", "NAAC", "NBA", "NIRF", "Affiliation", "Autonomous status", "Statutory council"])
            year = st.number_input("Record year", min_value=1900, max_value=2200, value=today().year, step=1)
            category = st.text_input("Scope / category", value="Institution", max_chars=150)
            outcome = st.text_input("Recorded outcome (e.g. A, #75, Approved)", max_chars=200)
            validity = st.date_input("Valid until (optional)", value=None)
            sid = source("Authority document evidence", "authority-evidence")
        elif kind == "Course":
            name = st.text_input("Course name", max_chars=250)
            level = st.selectbox("Level", ["UG", "PG", "Diploma", "Doctoral", "Other"])
            course_year = st.text_input("Course academic year (optional)", placeholder="2025-26", max_chars=7)
            intake = st.number_input("Course-approved intake", min_value=0, value=0, step=1)
            registered = st.number_input("Course admissions (optional)", min_value=0, value=None, step=1)
            fee = st.number_input("Annual fee ₹ (optional)", min_value=0.0, value=None)
            change = st.selectbox("Course status", ["Continuing", "Newly added", "Discontinued"])
            sid = source("Course schedule evidence", "course-evidence")
        elif kind == "Recruiter / internship":
            name = st.text_input("Employer name", max_chars=250)
            sector = st.selectbox("Employer sector", ["IT", "BFSI", "Core", "Services", "Other"])
            recruiter_year = st.number_input("Recruitment year (optional)", min_value=1900, max_value=today().year, value=None, step=1)
            offers = st.number_input("Recorded offers", min_value=0, value=None, step=1)
            repeat = st.checkbox("Repeat recruiter (documented)")
            internship = st.checkbox("Provides internships (documented)")
            location = st.text_input("Placement location", max_chars=250)
            international = st.selectbox("Placement geography", ["Not established", "Domestic", "International"])
            sid = source("Employer / internship evidence", "recruiter-evidence")
        elif kind == "Institution details":
            name = st.text_input("Institution name", value=i.name, max_chars=250)
            city = st.text_input("City", value=i.city, max_chars=100)
            state = st.text_input("State", value=i.state, max_chars=100)
            university = st.text_input("Affiliated university", value=i.university, max_chars=250)
            ownership = st.text_input("Ownership", value=i.ownership, max_chars=150)
            established = st.number_input("Established year (optional)", min_value=1800, max_value=today().year, value=i.established, step=1)
            aishe = st.text_input("AISHE code (if available)", value=i.aishe_code or "", max_chars=50)
            website = st.text_input("Institution website (optional)", value=i.website or "", max_chars=2000)
            campus_status = st.text_input("Recorded campus status", value=i.campus_status, max_chars=150)
            sid = source("Institution identity / status evidence", "identity-status-evidence")
        elif kind == "Promoter profile":
            organisation = st.text_input("Trust / society / organisation", value=i.promoter.organisation, max_chars=250)
            founded = st.number_input("Promoter organisation established year (optional)", min_value=1800, max_value=today().year, value=i.promoter.established, step=1)
            names = st.text_area("Promoters / directors (one per line)", value="\n".join(i.promoter.names), max_chars=4000)
            board = st.text_area("Board / key management (one per line)", value="\n".join(i.promoter.board), max_chars=4000)
            institutions = st.text_area("Other institutions (one per line)", value="\n".join(i.promoter.other_institutions), max_chars=4000)
            previous = st.text_area("Previous institutions (one per line)", value="\n".join(i.promoter.previous_institutions), max_chars=4000)
            businesses = st.text_area("Associated businesses (one per line)", value="\n".join(i.promoter.businesses), max_chars=4000)
            sid = source("Promoter identity evidence", "promoter-evidence")
        else:
            title = st.text_input("Public record title", max_chars=250)
            stage = st.selectbox("Exact procedural stage", ["Complaint", "FIR", "Charge", "Prosecution", "Conviction", "Acquittal", "Civil dispute", "Regulatory notice", "Insolvency proceeding"])
            record_date = st.date_input("Record date", value=today(), max_value=today())
            reference = st.text_input("Primary record reference / case number", max_chars=300)
            description = st.text_area("Factual description, entity identity and current outcome", max_chars=4000)
            sid = source("Primary public record evidence", "legal-evidence")
        submitted = st.form_submit_button("Save sourced record", type="primary", icon=":material/save:")
    if submitted:
        try:
            if kind == "Admission year":
                row = Admission(year=year, intake=intake, registered=registered, claimed=claimed, intake_evidence_id=intake_sid, registration_evidence_id=registered_sid if registered is not None else None, claim_evidence_id=claim_sid if claimed is not None else None)
                data["admissions"] = [r for r in data["admissions"] if r["year"] != year] + [row.model_dump(mode="json")]
            elif kind == "Placement year":
                row = Placement(year=year, eligible=eligible, placed=placed, batch_size=batch, claimed_percent=advertised, highest_lpa=highest, average_lpa=average, median_lpa=median, evidence_id=sid, claim_evidence_id=claim_sid if advertised is not None else None)
                data["placements"] = [r for r in data["placements"] if r["year"] != year] + [row.model_dump(mode="json")]
            elif kind in {"Campus metric", "Commercial metric"}:
                data[section][metric_key] = Metric(value=value, evidence_id=sid).model_dump(mode="json")
            elif kind == "Regulatory / ranking record":
                if not outcome.strip() or not category.strip():
                    raise ValueError("Enter a recorded outcome and scope.")
                row = Accreditation(body=body, outcome=outcome.strip(), category=category.strip(), year=year, valid_until=validity, evidence_id=sid)
                data["accreditations"].append(row.model_dump(mode="json"))
            elif kind == "Course":
                if not name.strip():
                    raise ValueError("Enter a course name.")
                row = Course(name=name.strip(), level=level, year=course_year.strip() or None, intake=intake, admissions=registered, annual_fee=fee, change=change, evidence_id=sid)
                data["courses"] = [c for c in data["courses"] if (c["name"].casefold(), c["level"], c.get("year")) != (row.name.casefold(), row.level, row.year)] + [row.model_dump(mode="json")]
            elif kind == "Recruiter / internship":
                if not name.strip() or offers is None:
                    raise ValueError("Enter an employer name and the recorded offer count.")
                row = Recruiter(name=name.strip(), sector=sector, year=recruiter_year, offers=offers, repeat=repeat, location=location.strip() or "Not disclosed", internship=internship, international={"Not established": None, "Domestic": False, "International": True}[international], evidence_id=sid)
                match = lambda r: (r["name"].casefold(), r.get("year"), r["location"].casefold(), r["internship"], r.get("international"))
                data["recruiters"] = [r for r in data["recruiters"] if match(r) != match(row.model_dump())] + [row.model_dump(mode="json")]
            elif kind == "Institution details":
                if not city.strip() or not state.strip():
                    raise ValueError("Enter a city and state.")
                data.update(name=name.strip(), city=city.strip(), state=state.strip(), university=university.strip() or "Not disclosed", ownership=ownership.strip() or "Not disclosed", established=established, aishe_code=aishe.strip() or None, website=website.strip() or None, campus_status=campus_status.strip() or "Not established", identity_evidence_id=sid)
            elif kind == "Promoter profile":
                split = lambda text: [line.strip() for line in text.splitlines() if line.strip()]
                row = Promoter(organisation=organisation.strip() or "Not disclosed", established=founded, names=split(names), board=split(board), other_institutions=split(institutions), previous_institutions=split(previous), businesses=split(businesses), evidence_id=sid, records=i.promoter.records)
                data["promoter"] = row.model_dump(mode="json")
            else:
                if not title.strip() or not reference.strip() or not description.strip():
                    raise ValueError("Provide a title, primary record reference and factual description.")
                row = LegalRecord(title=title.strip(), stage=stage, date=record_date, reference=reference.strip(), description=description.strip(), evidence_id=sid)
                data["promoter"]["records"].append(row.model_dump(mode="json"))
            updated = Institution.model_validate(data)
            repo().save_many([updated], f"{kind} saved")
            st.success("Record saved with its source reference.")
        except ValueError as exc:
            st.error(str(exc))


def import_export():
    st.subheader("Validated profile import")
    st.caption("Upload one institution JSON, an array of profiles, or an object with an institutions array. Missing source references, invalid counts, duplicate years and mixed real/demo evidence are rejected before saving.")
    upload = st.file_uploader("Institution JSON", type=["json"], max_upload_size=10)
    if upload:
        try:
            institutions = parse_profiles(upload.getvalue())
            st.dataframe(pd.DataFrame([{"ID": i.id, "Institution": i.name, "City": i.city, "Evidence": len(i.evidence), "Demo": i.demo} for i in institutions]), hide_index=True)
            existing = {i.id for i in repo().institutions()}
            replacements = [i.name for i in institutions if i.id in existing]
            if replacements:
                st.warning("Matching profiles will be replaced: "+", ".join(replacements))
            if st.button(f"Import and save {len(institutions)} profile(s)", type="primary", icon=":material/upload:"):
                repo().save_many(institutions)
                st.success("Validated profiles imported atomically. Use the sidebar to select them.")
        except (ValueError, UnicodeDecodeError) as exc:
            st.error(f"Import rejected: {exc}")
    st.download_button("Download JSON schema", json.dumps(Institution.model_json_schema(), indent=2), "institution-schema.json", "application/json", icon=":material/schema:")
    from iip.config import ROOT
    st.download_button("Download starter profile template", (ROOT / "data" / "profile_template.json").read_text(encoding="utf-8"), "profile-template.json", "application/json", icon=":material/description:")
    profiles = repo().institutions()
    st.download_button("Back up all institution profiles", json.dumps({"institutions": [i.model_dump(mode="json") for i in profiles]}, indent=2), "institution-profiles.json", "application/json", icon=":material/download:")
    st.caption("This JSON export includes profile evidence. To back up notes, watchlists, audits and API usage, also back up the local SQLite database while the app is stopped.")


def render():
    st.caption("INSTITUTION INTELLIGENCE / WORKSPACE SETTINGS")
    st.title("Workspace & API")
    st.caption("Connect providers, manage real institutions and control research usage.")
    mode = st.segmented_control("Workspace section", ["API & usage", "Create profile", "Add records", "Import / export"], default="API & usage", key="workspace-section")
    if mode == "Create profile":
        create_profile()
    elif mode == "Add records":
        add_records(repo().get(st.session_state.get("selected_id", "aster")))
    elif mode == "Import / export":
        import_export()
    else:
        api_settings()
