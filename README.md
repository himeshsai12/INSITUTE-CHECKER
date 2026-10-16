# INSITUTE-CHECKER

A Streamlit workspace for institution partnership due diligence: search, five-year performance, source review, commercial scenarios and executive briefs. The default dataset contains six explicitly fictional institutions. No demo figure or public search result is represented as independently verified.

The executive overview includes a CEO view and regulatory screening. Commercial potential uses visible, editable business criteria rather than an institution score; the selected criteria are preserved in executive and opportunity exports. Course academic years, recruiter years, international offer records and previous promoter institutions can be entered with evidence through Workspace & API.

## Run locally

Requires Python 3.11 or newer. From this project folder on Windows:

```powershell
.\run.ps1
```

The launcher creates a project virtual environment and installs dependencies on its first run. Alternatively:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://localhost:8501. No API key is required for the demo, imported data, analysis, scenario modelling or exports.

## Connect live research

```powershell
Copy-Item -LiteralPath .env.example -Destination .env
```

Choose an AI provider with `AI_PROVIDER`: `auto`, `openai`, `gemini`, `anthropic`, `groq` or `openrouter`. Add that provider's key locally in `.env`. OpenAI and supported Groq GPT-OSS models can search the internet without Tavily. Other models/providers also need `TAVILY_API_KEY` for source discovery. API keys are provider-specific: a Gemini or Groq key does not belong in `OPENAI_API_KEY`. The Live research screen includes a provider selector that persists across page navigation and overrides the default for that search.

| AI provider | Key variable | Model variable | Source discovery |
| --- | --- | --- | --- |
| OpenAI | `OPENAI_API_KEY` | `OPENAI_MODEL` | Tavily or built-in web search |
| Google Gemini | `GEMINI_API_KEY` (also accepts `GOOGLE_API_KEY`) | `GEMINI_MODEL` | Tavily |
| Anthropic Claude | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` | Tavily |
| Groq | `GROQ_API_KEY` | `GROQ_MODEL` | Tavily or built-in browser search with supported GPT-OSS models |
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` | Tavily |

For example, research using Gemini without an OpenAI key:

```dotenv
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-3.8-flash
TAVILY_API_KEY=your_tavily_key
```

Use an account-accessible model. Gemini, Anthropic and OpenRouter adapters request structured JSON using provider-native schemas. Groq defaults to `openai/gpt-oss-20b` with strict JSON schema output; other Groq models use JSON object mode followed by the same Pydantic schema validation. Auto selects the first configured provider in this order: OpenAI, Gemini, Anthropic, Groq, OpenRouter. The app never silently switches providers after a failed request. If AI synthesis fails, discovered sources remain available with a visible failure note.

The app reads saved `.env` changes on each rerun without putting file values into the process environment. Save the file and refresh the app to pick up changed or removed keys. Explicit process environment variables take precedence over `.env`; Streamlit secrets take precedence over both. The same precedence applies to keys, provider, models and numeric tuning controls.

| Configuration | Behaviour |
| --- | --- |
| No keys | Complete local demo and analysis; live research disabled |
| Tavily only | Basic search with source snippets and links |
| OpenAI only | Responses API with built-in web search and clickable citations |
| Tavily + any supported AI key | Tavily discovery followed by selected-provider synthesis, when selected |
| Groq GPT-OSS key without Tavily | Built-in browser search; optional source-grounded synthesis |
| Gemini, Anthropic, OpenRouter or other Groq models without Tavily | AI connection configured; live source discovery needs Tavily |

Use **Live internet research** beside the saved-profile search, or open **Sources & research**, which starts on live research. Enter an institution name and city, then select **Research institution**. **Fetch latest sources now** is selected by default so submission retrieves new internet results. Turn it off to reuse a saved result within the cache lifetime. Opening pages or typing a local search does not make API requests. Results include query, scope, provider, retrieval time, sources and missing information. Search findings remain unverified. They are never automatically written into numeric metrics. Attach a source to a real profile only after checking identity; then add a sourced record and review its evidence separately.

## Included views

- Executive profile: identity, regulatory records, KPIs, trends, headroom, follow-up, notes and exports.
- Admissions: five academic years, intake, university registrations, college claims, variance, utilisation, CAGR and course schedules.
- Placements: eligible and full-batch denominators, advertised claims, salary trends, recruiters, sectors, internships and locations.
- Ranking and accreditation: category-specific NIRF timeline, UGC, AICTE, NAAC, NBA, affiliation, validity and source status.
- Campus health: students, faculty, academic outcomes, infrastructure and hostel occupancy.
- Commercial: sourced fee and collection inputs; editable annual cohort scenarios and partner share.
- Promoters and records: management, associations and distinct legal procedural stages, separate from institution indicators.
- Risk centre: explicit screening rules, evidence links and next actions; no composite college score.
- Evidence workspace: source layers, period/date, excerpts, independent review and local audit history.
- Campus comparison, persistent watchlist, internal notes, JSON import/backup, Markdown and printable HTML executive briefs.

## Use real data

1. **Workspace & API → Create profile**. Enter institution identity and a source reference. The new profile starts with empty time series and unavailable metrics.
2. **Sources & research → Evidence register**. Add primary reports, university extracts, regulator records or internal references. New evidence is unverified or self-reported.
3. **Workspace & API → Add records**. Enter admission years, placement years, campus/financial metrics, course schedules, accreditation and promoter records with attached evidence IDs.
4. Review the original documents in the evidence workspace. A verified status requires a reviewer name, date and note. A government URL alone does not establish verification.
5. Analyse and export. Every numeric row retains its evidence references; calculated KPIs expose their inputs and formulas.

For bulk data, download `data/profile_template.json` or the app's schema. Import an institution object, an array of institution objects, or `{"institutions": [...]}`. The whole import is validated before an atomic transaction. Matching IDs replace profiles, with an explicit UI warning. Unknown source references, duplicate evidence IDs, duplicate years, invalid placement counts, non-finite values and invalid percentages are rejected.

### Minimal admission record

Add the referenced evidence objects before importing this record:

```json
{
  "year": "2025-26",
  "intake": 1200,
  "registered": 812,
  "claimed": 950,
  "intake_evidence_id": "university-approval-2025",
  "registration_evidence_id": "university-register-2025",
  "claim_evidence_id": "college-statement-2025"
}
```

`registered` describes the source's university registration count, not an automatic verification status. The separate **University portal verified** field is Yes only when that count cites university evidence reviewed as Verified.

## API optimisation

- No API calls on page load, campus selection, local filters, charts or exports.
- SQLite cache with a configurable 24-hour default TTL and a 200-entry cap; cache keys include query, scope, options, model, token limit and a hash of provider credentials.
- Tavily basic search, 3–10 requested sources, bounded snippet lengths, optional synthesis.
- Configurable output token ceiling and timeout; one retry on rate-limit or selected transient server errors. Timeouts are not retried automatically.
- Transactional daily outbound-request limit across the workspace, including failures and retries. Quota resets by IST calendar day. Cache hits remain available when the limit is reached.
- API activity shows requests, cache hits, failures and reported AI tokens, normalised across providers. Request limits are not monetary budgets: a web-search request can include billed tool calls. Set provider-side spend limits for financial control.
- Streamlit forms batch changes; the overview trend and scenario builder use fragments; the SQLite repository is cached as a shared resource.

Offline provider tests cover request schemas, caching, fresh retrieval, reference filtering, errors, retry counting and quotas. Live OpenAI web research was also tested through the app form with a public IIT Hyderabad query on 17 October 2026. This confirmed retrieval and clickable source display, not the accuracy of every AI-generated statement. Actual network access, model availability and provider billing depend on your accounts.

## Evidence boundaries

UGC, AISHE, AICTE, NAAC, NBA and NIRF links are primary-source starting points. This app does not promise a public API for every dataset. Some records require manual download, university authorisation, authenticated portals or institutional document collection. Those records can be entered/imported with their exact provenance. No access control or CAPTCHA is bypassed.

Institution submissions, including published ranking submissions, are not automatically independent verification. Unknown values are `null` and displayed as unavailable. Campus capacity and annual intake are separate denominators. Salary figures use lakh rupees per annum. Revenue scenarios use annual admissions and annual fee; they are not total-campus or audited revenue forecasts. Scholarship, discount, collection and refund factors are sequential editable assumptions.

This is a local single-workspace application bound to the loopback interface. SQLite stores profiles, notes, evidence excerpts, research and reviewer attribution locally. It has no authenticated multi-user permissions, automatic university portal connector or tamper-proof audit system. Add OIDC, role-based access, a managed database and retention policies before a shared production deployment.

## Project structure

```text
app.py                 shared sidebar and modern Streamlit navigation
app_pages/             page entry points
iip/models.py          Pydantic data contracts and evidence validation
iip/analytics.py       calculations and explainable risk screening
iip/repository.py      SQLite storage, quotas, audit and cache
iip/research.py        Tavily / OpenAI providers and cited synthesis
iip/views/             dashboard modules and record-entry workflows
iip/reports.py         executive brief exports
data/                  starter template and local runtime database
tests/                 domain, persistence, provider and app-flow checks
```

Back up `data/intelligence.db` while the app is stopped for a complete workspace backup. JSON profile exports do not include notes, watchlists or API usage.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## Integration documentation

- [Streamlit documentation](https://docs.streamlit.io/)
- [OpenAI Responses API](https://developers.openai.com/api/docs/guides/responses)
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [Tavily search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Gemini content generation API](https://ai.google.dev/api/generate-content)
- [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Groq API reference](https://console.groq.com/docs/api-reference)
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [AISHE](https://aishe.gov.in/), [NIRF](https://www.nirfindia.org/), [UGC](https://www.ugc.gov.in/)
