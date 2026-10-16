import pytest
from streamlit.testing.v1 import AppTest

from iip.repository import Repository
from iip.config import ROOT, load_settings


@pytest.fixture
def app_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("IIP_DATABASE_PATH", str(tmp_path / "ui.db"))
    for name in ["OPENAI_API_KEY", "TAVILY_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "AI_PROVIDER"]:
        monkeypatch.delenv(name, raising=False)
    # App tests must never load the user's real local credentials.
    monkeypatch.setattr("iip.ui.load_settings", lambda secrets=None: load_settings(secrets, env_path=tmp_path / ".env"))
    return tmp_path / "ui.db"


def start():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()


def assert_clean(at):
    assert not at.exception, [e.message for e in at.exception]


def button(at, label):
    return next(b for b in at.button if b.label == label)


def text_input(at, label):
    return next(w for w in at.text_input if w.label == label)


def test_all_dashboard_pages_render(app_environment):
    at = start()
    assert_clean(at)
    assert at.title[0].value == "Aster Institute of Technology"
    for page in ["admissions", "placements", "accreditation", "campus", "commercial", "promoters", "risks", "sources", "compare", "watchlist", "settings"]:
        at.switch_page(f"app_pages/{page}.py").run()
        assert_clean(at)
        assert len(at.title) > 0
    assert Repository(app_environment).usage()["requests"] == 0


def test_search_changes_profile_and_handles_unknown_institution(app_environment):
    at = start()
    at.text_input(key="local_search").set_value("Pune").run()
    assert_clean(at)
    assert at.title[0].value == "Meridian School of Management"
    at.text_input(key="local_search").set_value("Unknown University xyz").run()
    assert_clean(at)
    assert at.title[0].value == "Find an institution"
    at.switch_page("app_pages/sources.py").run()
    at.button_group(key="source-workspace-mode").set_value("Live research").run()
    assert_clean(at)
    assert button(at, "Research institution").disabled
    assert Repository(app_environment).usage()["requests"] == 0


def test_scenario_and_watchlist_flow(app_environment):
    at = start()
    button(at, "Add to watchlist").click().run()
    assert "aster" in Repository(app_environment).watched()
    at.switch_page("app_pages/commercial.py").run()
    button(at, "Calculate scenario").click().run()
    assert_clean(at)
    assert at.session_state["scenario-result-aster"]["result"]["incremental_admissions"] == 200
    at.switch_page("app_pages/watchlist.py").run()
    assert_clean(at)
    assert any(h.value == "Aster Institute of Technology" for h in at.subheader)


def test_create_real_profile_without_fabricated_statistics(app_environment):
    at = start()
    at.switch_page("app_pages/settings.py").run()
    at.button_group(key="workspace-section").set_value("Create profile").run()
    assert_clean(at)
    for label, value in [("Institution name", "New Test College"), ("City", "Delhi"), ("State", "Delhi")]:
        text_input(at, label).set_value(value)
    next(w for w in at.text_area if w.label == "Identity source or internal reference").set_value("Management-provided identity sheet.")
    button(at, "Create profile").click().run()
    assert_clean(at)
    i = next(i for i in Repository(app_environment).institutions() if i.name == "New Test College")
    assert not i.demo and not i.admissions and not i.placements
    assert at.session_state["selected_id"] == i.id
    at.switch_page("app_pages/overview.py").run()
    assert_clean(at)
    assert all(m.value == "—" for m in at.metric[:4])


def test_workspace_import_view_and_evidence_log_render(app_environment):
    at = start()
    at.switch_page("app_pages/settings.py").run()
    at.button_group(key="workspace-section").set_value("Import / export").run()
    assert_clean(at)
    at.switch_page("app_pages/sources.py").run()
    at.button_group(key="source-workspace-mode").set_value("Review log").run()
    assert_clean(at)


def test_real_profile_entry_and_named_review(app_environment, real_profile):
    Repository(app_environment).save_many([real_profile])
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.session_state["selected_id"] = real_profile.id
    at.run()
    assert_clean(at)
    at.switch_page("app_pages/settings.py").run()
    at.button_group(key="workspace-section").set_value("Add records").run()
    assert_clean(at)
    numbers = {w.label: w for w in at.number_input}
    numbers["Approved intake"].set_value(1200)
    numbers["University-registered admissions (optional)"].set_value(812)
    numbers["College-claimed admissions (optional)"].set_value(950)
    button(at, "Save sourced record").click().run()
    assert_clean(at)
    assert Repository(app_environment).get(real_profile.id).latest_admission.registered == 812
    at.switch_page("app_pages/sources.py").run()
    at.button_group(key="source-workspace-mode").set_value("Evidence register").run()
    next(w for w in at.selectbox if w.label == "Review outcome").select("Verified")
    text_input(at, "Reviewer name").set_value("Analyst")
    next(w for w in at.text_area if w.label == "Review note and document reference").set_value("Reviewed exact identity and academic period against supplied extract.")
    button(at, "Save review").click().run()
    assert_clean(at)
    assert Repository(app_environment).get(real_profile.id).evidence[0].status == "Verified"
    at.switch_page("app_pages/admissions.py").run()
    assert_clean(at)
    assert at.dataframe[0].value["University portal verified"].iloc[0] == "Yes"


def test_non_openai_provider_selector_and_search_requirements(app_environment, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    at = start()
    at.switch_page("app_pages/sources.py").run()
    at.button_group(key="source-workspace-mode").set_value("Live research").run()
    assert_clean(at)
    assert at.selectbox(key="research-provider").value == "gemini"
    assert button(at, "Research institution").disabled
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    at.run()
    assert_clean(at)
    assert not button(at, "Research institution").disabled
    assert Repository(app_environment).usage()["requests"] == 0


def test_live_search_shortcut_prefills_query_and_fetches_fresh(app_environment, monkeypatch):
    from iip.config import now_iso
    from iip.research import ResearchResult, ResearchSource

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    calls = []
    def search(service, query, *options, **kwargs):
        calls.append((query, kwargs))
        return ResearchResult(
            query=query, focus="Executive diligence", provider="Test live provider", observed_at=now_iso(),
            sources=[ResearchSource(id="S1", title="Institution report", url="https://example.com/report")],
            summary="Source discovered; review pending.",
        )
    monkeypatch.setattr("iip.views.sources.ResearchService.search", search)
    at = start()
    at.text_input(key="local_search").set_value("IIT Hyderabad, Telangana").run()
    at.button(key="open-live-research").click().run()
    assert_clean(at)
    assert at.title[0].value == "Sources & research"
    assert at.button_group(key="source-workspace-mode").value == "Live research"
    assert text_input(at, "Institution to research").value == "IIT Hyderabad, Telangana"
    assert not calls and Repository(app_environment).usage()["requests"] == 0
    # AppTest needs the new page set explicitly for reruns after st.switch_page.
    at.switch_page("app_pages/sources.py")
    button(at, "Research institution").click().run()
    assert_clean(at)
    assert calls == [("IIT Hyderabad, Telangana", {"force_refresh": True})]
    assert at.session_state["research_result"]["sources"][0]["url"] == "https://example.com/report"
    next(w for w in at.checkbox if w.label == "Fetch latest sources now").uncheck()
    button(at, "Research institution").click().run()
    assert_clean(at)
    assert calls[-1][1] == {"force_refresh": False}


def test_live_provider_selection_persists_across_pages(app_environment, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    at = start()
    at.switch_page("app_pages/sources.py").run()
    at.selectbox(key="research-provider").select("groq").run()
    at.switch_page("app_pages/overview.py").run()
    at.switch_page("app_pages/sources.py").run()
    assert_clean(at)
    assert at.selectbox(key="research-provider").value == "groq"
    assert Repository(app_environment).usage()["requests"] == 0


def test_business_criteria_update_assessment_and_follow_profile_navigation(app_environment):
    at = start()
    at.switch_page("app_pages/commercial.py").run()
    next(w for w in at.number_input if w.label == "Minimum available annual seats").set_value(1000)
    button(at, "Apply business criteria").click().run()
    assert_clean(at)
    criteria_table = next(df.value for df in at.dataframe if "Business criterion" in df.value.columns)
    assert criteria_table.loc[0, "Result"] == "Below minimum"
    assert criteria_table.loc[0, "Recorded"] == "380"
    assert at.session_state["opportunity-criteria"]["minimum_seats"] == 1000
    at.switch_page("app_pages/overview.py").run()
    assert_clean(at)
    assert any(m.label == "Admissions" and m.value == "Rising" for m in at.metric)
    at.selectbox(key="profile-picker").select("cedar").run()
    assert_clean(at)
    assert any(m.label == "Admissions" and m.value == "Falling" for m in at.metric)
    at.switch_page("app_pages/commercial.py").run()
    assert_clean(at)
    assert next(w for w in at.number_input if w.label == "Minimum available annual seats").value == 1000
    assert Repository(app_environment).usage()["requests"] == 0


def test_recruiter_entry_shows_without_inventing_placement_totals(app_environment, real_profile):
    Repository(app_environment).save_many([real_profile])
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.session_state["selected_id"] = real_profile.id
    at.run()
    at.switch_page("app_pages/settings.py").run()
    at.button_group(key="workspace-section").set_value("Add records").run()
    next(w for w in at.selectbox if w.label == "Record type").select("Recruiter / internship").run()
    text_input(at, "Employer name").set_value("Supplied employer")
    next(w for w in at.number_input if w.label == "Recorded offers").set_value(17)
    next(w for w in at.number_input if w.label == "Recruitment year (optional)").set_value(2025)
    next(w for w in at.selectbox if w.label == "Placement geography").select("International")
    next(w for w in at.checkbox if w.label == "Provides internships (documented)").check()
    button(at, "Save sourced record").click().run()
    assert_clean(at)
    saved = Repository(app_environment).get(real_profile.id)
    assert saved.recruiters[0].international is True
    assert saved.recruiters[0].year == 2025
    assert not saved.placements
    button(at, "Save sourced record").click().run()
    assert_clean(at)
    assert len(Repository(app_environment).get(real_profile.id).recruiters) == 1
    at.switch_page("app_pages/placements.py").run()
    assert_clean(at)
    assert next(m for m in at.metric if m.label == "International offer records").value == "17"
    assert not any(m.label == "Placement / eligible" for m in at.metric)
    next(w for w in at.selectbox if w.label == "Employer reporting year").select("Year not specified").run()
    assert_clean(at)
    assert any("No employer records" in c.value for c in at.caption)


def test_course_history_upserts_and_renders_without_admission_totals(app_environment, real_profile):
    Repository(app_environment).save_many([real_profile])
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.session_state["selected_id"] = real_profile.id
    at.run()
    at.switch_page("app_pages/settings.py").run()
    at.button_group(key="workspace-section").set_value("Add records").run()
    next(w for w in at.selectbox if w.label == "Record type").select("Course").run()
    text_input(at, "Course name").set_value("Computer science")
    text_input(at, "Course academic year (optional)").set_value("2025-26")
    next(w for w in at.number_input if w.label == "Course-approved intake").set_value(120)
    button(at, "Save sourced record").click().run()
    assert_clean(at)
    next(w for w in at.number_input if w.label == "Course-approved intake").set_value(180)
    button(at, "Save sourced record").click().run()
    assert_clean(at)
    saved = Repository(app_environment).get(real_profile.id)
    assert len(saved.courses) == 1 and saved.courses[0].intake == 180
    assert not saved.admissions
    at.switch_page("app_pages/admissions.py").run()
    assert_clean(at)
    assert at.dataframe[0].value.loc[0, "Academic year"] == "2025-26"
    assert at.dataframe[0].value.loc[0, "Approved intake"] == 180


def test_nirf_category_switch_keeps_unavailable_years_distinct(app_environment, real_profile):
    from iip.models import Institution
    data = real_profile.model_dump()
    data["accreditations"] = [
        {"body": "NIRF", "category": "Engineering", "year": 2024, "outcome": "#50", "evidence_id": "E1"},
        {"body": "NIRF", "category": "Engineering", "year": 2026, "outcome": "Not ranked", "evidence_id": "E1"},
        {"body": "NIRF", "category": "Overall", "year": 2026, "outcome": "#150", "evidence_id": "E1"},
    ]
    Repository(app_environment).save_many([Institution.model_validate(data)])
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.session_state["selected_id"] = real_profile.id
    at.run()
    at.switch_page("app_pages/accreditation.py").run()
    assert_clean(at)
    assert {m.label: m.value for m in at.metric} == {"2022": "Unavailable", "2023": "Unavailable", "2024": "#50", "2025": "Unavailable", "2026": "Not ranked"}
    next(w for w in at.selectbox if w.label == "NIRF category").select("Overall").run()
    assert_clean(at)
    assert next(m for m in at.metric if m.label == "2026").value == "#150"
    assert next(m for m in at.metric if m.label == "2024").value == "Unavailable"
