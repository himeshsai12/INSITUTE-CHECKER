import altair as alt
import pandas as pd
import streamlit as st

from iip.analytics import admission_summary, fmt, percent, recent_records
from iip.models import Status, SourceType
from iip.ui import heading, cards, source_help, admission_df, placement_df, line_chart, evidence_popover, chart_frame, data_gap


def admissions(i):
    heading(i, "Admission intelligence", "Intake, registrations and claim reconciliation")
    if not i.admissions:
        data_gap("Admission history is unavailable. Import intake and registration records with evidence in Workspace & API.")
        course_capacity(i)
        return
    a = admission_summary(i)
    latest = i.latest_admission
    cards([
        {"label": "Latest registered admissions", "value": fmt(latest.registered), "help": source_help(i, latest.registration_evidence_id)},
        {"label": "Average utilisation", "value": fmt(a["average_utilisation"], "%", 1), "help": f"Simple mean of utilisation across {a['years']} available years. Excludes unavailable registrations and zero intake."},
        {"label": "Admission CAGR", "value": fmt(a["cagr"], "%", 1), "help": "Uses earliest and latest available registrations and elapsed academic years, rather than row count."},
        {"label": "Latest claim variance", "value": fmt(a["variance"]), "delta": fmt(a["variance_percent"], "% of college claim", 1) if a["variance_percent"] is not None else None, "delta_color": "off", "help": "College claim minus university registration count. Positive values mean the claim is higher.\n"+source_help(i, latest.claim_evidence_id, latest.registration_evidence_id)},
    ])
    left, right = st.columns([1.5, 1])
    with left, st.container(border=True):
        st.subheader("Intake versus registered students")
        line_chart(admission_df(i, latest_five=True), "Academic year", ["Approved intake", "Registered admissions", "College claim"])
        evidence_popover(i, [sid for r in i.admissions for sid in (r.intake_evidence_id, r.registration_evidence_id, r.claim_evidence_id)])
    with right, st.container(border=True):
        st.subheader("University portal verification")
        st.metric("College claim", fmt(latest.claimed), help=source_help(i, latest.claim_evidence_id))
        st.metric("Portal registrations", fmt(latest.registered), help=source_help(i, latest.registration_evidence_id))
        evidence = i.source(latest.registration_evidence_id)
        verified = evidence and evidence.source_type == SourceType.UNIVERSITY and evidence.status == Status.VERIFIED
        st.badge("University portal reviewed as verified" if verified else "Demo registrations" if i.demo else "Independent portal verification pending", color="green" if verified else "violet" if i.demo else "orange")
        st.caption("A college admission statement and university registrations are separate records. Align the course scope and cut-off date before interpreting a variance.")
    df = admission_df(i)
    df["University portal verified"] = ["Yes" if i.source(r.registration_evidence_id) and i.source(r.registration_evidence_id).status == Status.VERIFIED and i.source(r.registration_evidence_id).source_type == SourceType.UNIVERSITY else "Demo" if i.demo else "Pending" for r in sorted(i.admissions, key=lambda r: r.year)]
    st.subheader("Academic-year evidence")
    st.dataframe(df, hide_index=True, column_config={"Utilisation %": st.column_config.NumberColumn(format="%.1f%%")})
    if a["years"] < 5:
        st.caption(f"{a['years']} years available. Missing years are not estimated.")
    course_capacity(i)


def course_capacity(i):
    st.subheader("Course-level capacity")
    if i.courses:
        course_years = sorted({c.year for c in i.courses if c.year}, reverse=True)
        period = st.selectbox("Course academic year", ["All supplied periods", *course_years, "Year not specified"])
        selected_courses = [c for c in i.courses if period == "All supplied periods" or c.year == period or (period == "Year not specified" and c.year is None)]
        if not selected_courses:
            st.caption("No course records for this period.")
            return
        courses = pd.DataFrame([{"Course": c.name, "Level": c.level, "Academic year": c.year or "Not specified", "Approved intake": c.intake, "Admissions": c.admissions, "Utilisation %": percent(c.admissions, c.intake), "Annual fee": c.annual_fee, "Change": c.change, "Reporting period": i.source(c.evidence_id).period, "Evidence": c.evidence_id, "Status": str(i.source(c.evidence_id).status)} for c in selected_courses])
        st.dataframe(courses, hide_index=True, column_config={"Annual fee": st.column_config.NumberColumn(format="₹%,d"), "Utilisation %": st.column_config.NumberColumn(format="%.1f%%")})
        st.caption("Course values describe the supplied reporting period and may be historical. Current intake needs a current authority document.")
        evidence_popover(i, [c.evidence_id for c in i.courses], "Course schedule evidence")
    else:
        st.caption("Course-level data unavailable.")


def placements(i):
    heading(i, "Placement intelligence", "Outcomes, compensation and employer continuity")
    if not i.placements:
        data_gap("Placement history is unavailable. Import unique placed students, eligible students and source documents.")
        employer_intelligence(i)
        return
    latest = i.latest_placement
    actual = percent(latest.placed, latest.eligible)
    cards([
        {"label": "Placement / eligible", "value": fmt(actual, "%", 1), "help": f"{latest.placed} unique students placed ÷ {latest.eligible} eligible students.\n"+source_help(i, latest.evidence_id)},
        {"label": "Placement / full batch", "value": fmt(percent(latest.placed, latest.batch_size), "%", 1), "help": "Unique placed students divided by full batch size; unavailable without a batch denominator.\n"+source_help(i, latest.evidence_id)},
        {"label": "Average package", "value": fmt(latest.average_lpa, " LPA", 1), "help": source_help(i, latest.evidence_id)},
        {"label": "Median package", "value": fmt(latest.median_lpa, " LPA", 1), "help": source_help(i, latest.evidence_id)},
    ])
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.subheader("Placement outcomes")
        line_chart(placement_df(i, latest_five=True), "Year", ["Placement %", "Advertised %"], percent_axis=True)
    with right, st.container(border=True):
        st.subheader("Salary trajectory · LPA")
        line_chart(placement_df(i, latest_five=True), "Year", ["Highest LPA", "Average LPA", "Median LPA"])
    if latest.claimed_percent is not None and actual is not None and abs(latest.claimed_percent-actual) >= 10:
        st.warning(f"The advertised placement rate is {latest.claimed_percent:.1f}% versus {actual:.1f}% from placed / eligible. Reconcile definitions and reporting periods before accepting the claim.", icon=":material/rule:")
        evidence_popover(i, [latest.evidence_id, latest.claim_evidence_id], "Compare placement sources")
    st.subheader("Placement records")
    st.caption(f"Charts use the latest five-year window. {len(recent_records(i.placements))} years supplied in that window; the table retains all history. Missing years are not estimated.")
    st.dataframe(placement_df(i), hide_index=True, column_config={k: st.column_config.NumberColumn(format="%.1f%%") for k in ["Placement %", "Advertised %"]})
    evidence_popover(i, [r.evidence_id for r in i.placements])
    employer_intelligence(i)


def employer_intelligence(i):
    st.subheader("Employer intelligence")
    if not i.recruiters:
        st.caption("Recruiter, internship and location data unavailable.")
        return
    recruiter_years = sorted({r.year for r in i.recruiters if r.year}, reverse=True)
    period = st.selectbox("Employer reporting year", ["All supplied periods", *recruiter_years, "Year not specified"])
    recruiters = [r for r in i.recruiters if period == "All supplied periods" or r.year == period or (period == "Year not specified" and r.year is None)]
    if not recruiters:
        st.caption("No employer records for this period.")
        return
    cards([
        {"label": "Distinct recruiters", "value": len({r.name.casefold() for r in recruiters})},
        {"label": "Repeat recruiters", "value": len({r.name.casefold() for r in recruiters if r.repeat})},
        {"label": "Internship employers", "value": len({r.name.casefold() for r in recruiters if r.internship})},
        {"label": "International offer records", "value": sum(r.offers for r in recruiters if r.international is True) if any(r.international is not None for r in recruiters) else "Unavailable", "help": "Sourced offers, not a unique-student count. Unknown geography is excluded."},
    ])
    left, right = st.columns([1.5, 1])
    with left:
        recruiter_df = pd.DataFrame([{"Recruiter": r.name, "Year": str(r.year) if r.year else "Not specified", "Sector": r.sector, "Offers": r.offers, "Repeat": r.repeat, "Internships": r.internship, "Placement location": r.location, "Geography": "Not established" if r.international is None else "International" if r.international else "Domestic", "Evidence": r.evidence_id, "Status": str(i.source(r.evidence_id).status), "Source period": i.source(r.evidence_id).period} for r in recruiters])
        st.dataframe(recruiter_df, hide_index=True)
        st.caption("Offers can exceed unique placed students. Employer offer counts must not be summed into a placement rate.")
        evidence_popover(i, [r.evidence_id for r in i.recruiters], "Recruiter evidence")
    with right, st.container(border=True):
        st.markdown("**Offers by sector**")
        sectors = recruiter_df.groupby("Sector", as_index=False)["Offers"].sum()
        chart_frame(alt.Chart(sectors).mark_arc(innerRadius=60).encode(theta="Offers:Q", color="Sector:N", tooltip=["Sector:N", "Offers:Q"]), 210)
        repeat = len({r.name.casefold() for r in recruiters if r.repeat})
        new = len({r.name.casefold() for r in recruiters if not r.repeat})
        st.caption(f"{repeat} distinct repeat recruiters · {new} marked new. Across periods an employer may appear in both groups. Offers can cover different reporting periods; filter by year before comparing.")


def accreditation(i):
    heading(i, "Ranking & accreditation", "Category timelines, programme scope and document validity")
    if not i.accreditations:
        data_gap("Regulatory and ranking records are unavailable. Recognition, affiliation and accreditation are not inferred from a name or website.")
        return
    bodies = sorted({r.body for r in i.accreditations})
    selected = st.pills("Authorities", bodies, default=bodies, selection_mode="multi")
    records = [r for r in i.accreditations if r.body in (selected or [])]
    if not records:
        st.caption("Select an authority to view its records.")
        return
    ranking = [r for r in records if r.body == "NIRF"]
    if ranking:
        with st.container(border=True):
            st.subheader("NIRF timeline")
            category = st.selectbox("NIRF category", sorted({r.category for r in ranking}))
            category_records = [r for r in ranking if r.category == category]
            latest_year = max(r.year for r in category_records)
            for col, year in zip(st.columns(5), range(latest_year - 4, latest_year + 1)):
                with col:
                    annual = [r for r in category_records if r.year == year]
                    st.metric(str(year), " / ".join(r.outcome for r in annual) or "Unavailable", help=source_help(i, *(r.evidence_id for r in annual)))
                    st.caption(category)
            st.caption("Ranks are category-specific. Not ranked and data unavailable have different meanings.")
    st.subheader("Authority and programme register")
    from iip.config import today
    df = pd.DataFrame([{"Authority": r.body, "Year": r.year, "Scope / category": r.category, "Recorded outcome": r.outcome, "Valid until": str(r.valid_until or "Not supplied"), "Validity screening": "Expired — renewal needed" if r.valid_until and r.valid_until < today() else "Within recorded validity" if r.valid_until else "Not supplied", "Evidence": r.evidence_id, "Review status": str(i.source(r.evidence_id).status)} for r in sorted(records, key=lambda r: (r.body, r.year))])
    st.dataframe(df, hide_index=True)
    evidence_popover(i, [r.evidence_id for r in records], "Authority record evidence")
    st.caption("A sourced entry is not automatic independent verification. Programme accreditation, institutional accreditation, recognition and affiliation are reviewed separately.")


def campus(i):
    heading(i, "Campus health", "Academic performance, staffing and physical capacity")
    if not i.campus:
        data_gap("Campus measurements are unavailable. Import the campus report or record observations with their source and date.")
        return
    students, capacity, faculty = (i.value("campus", k) for k in ["students", "capacity", "faculty"])
    cards([
        {"label": "Campus utilisation", "value": fmt(percent(students, capacity), "%", 1), "help": source_help(i, *(i.campus[k].evidence_id for k in ["students", "capacity"] if k in i.campus))},
        {"label": "Students per faculty", "value": fmt(students/faculty if students is not None and faculty else None, ":1", 1), "help": "Total student strength divided by faculty strength.\n"+source_help(i, *(i.campus[k].evidence_id for k in ["students", "faculty"] if k in i.campus))},
        {"label": "Pass percentage", "value": fmt(i.value("campus", "pass_percent"), "%", 1), "help": source_help(i, i.campus.get("pass_percent").evidence_id) if "pass_percent" in i.campus else "Unavailable"},
        {"label": "Hostel occupancy", "value": fmt(percent(i.value("campus", "hostel_occupancy"), i.value("campus", "hostel_capacity")), "%", 1), "help": source_help(i, *(i.campus[k].evidence_id for k in ["hostel_occupancy", "hostel_capacity"] if k in i.campus))},
    ])
    academic = {"students": "Student strength · primary source", "students_disclosure": "Student strength · disclosure", "faculty": "Faculty strength", "attendance_percent": "Attendance %", "pass_percent": "Pass %", "backlogs": "Backlogs", "dropout_percent": "Dropout %", "graduation_percent": "Graduation %", "progression_percent": "Student progression %", "faculty_attrition_percent": "Faculty attrition %"}
    infrastructure = {"capacity": "Campus capacity", "land_acres": "Land · acres", "built_up_sqft": "Built-up area · sq ft", "classrooms": "Classrooms", "labs": "Laboratories", "library_books": "Library books", "hostel_capacity": "Hostel capacity", "hostel_occupancy": "Hostel occupancy", "sports_facilities": "Sports facilities", "transport_vehicles": "Transport vehicles"}
    for column, title, mapping in zip(st.columns(2), ["Academic performance", "Infrastructure"], [academic, infrastructure]):
        with column, st.container(border=True):
            st.subheader(title)
            rows = []
            for key, label in mapping.items():
                m = i.campus.get(key)
                e = i.source(m.evidence_id) if m else None
                rows.append({"Measure": label, "Value": fmt(m.value if m else None, digits=1 if key.endswith("percent") else 0), "Status": str(e.status) if e else "Unavailable", "Reporting period": e.period if e else "—", "Evidence": e.id if e else "—", "Observed": str(e.observed_on) if e else "—"})
            st.dataframe(pd.DataFrame(rows), hide_index=True)
    evidence_popover(i, [m.evidence_id for m in i.campus.values()], "Campus report evidence")
    st.caption("These are individual operational indicators. A composite campus or college score is not assigned.")
