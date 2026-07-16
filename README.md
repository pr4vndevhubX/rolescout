# rolescout 🦅

> An agentic personal assistant that scouts roles for you, every day.

An **agentic AI personal assistant** for your job hunt. Upload your resume once, tell it what roles you want ("Machine Learning Engineer", "GenAI Engineer"...), and it works for you every day:

**scouts live job boards → matches jobs against your resume → truthfully tailors your resume for near-miss JDs → prepares application packages (tailored content + cover letter + apply link) → emails you a daily digest.**

You stay in control: the agent **prepares**, you **approve and apply** with one click, it **tracks** what you applied to.

---

## Architecture — one Orchestrator, five specialists

Built with **LangGraph** (agent state machine) + **LangChain** (tools), on **FastAPI** + **Neon Postgres/pgvector** + a **React** dashboard.

```
                          you (chat / daily cron / Run-now button)
                                          │
                              ┌───────────▼───────────┐
                              │   ORCHESTRATOR agent  │  LangGraph ReAct graph,
                              │  (app/agent/)         │  every step audit-logged
                              └───────────┬───────────┘
        ┌──────────────┬──────────────────┼───────────────────┬──────────────┐
        ▼              ▼                  ▼                   ▼              ▼
   ┌─────────┐   ┌───────────┐   ┌───────────────┐   ┌──────────────┐   ┌──────────┐
   │  SCOUT  │   │ EVALUATOR │   │    TAILOR     │   │ APPLICATION  │   │ NOTIFIER │
   │ 3 job   │   │ pgvector +│   │ truthful      │   │ MANAGER      │   │ email    │
   │ boards, │   │ skill-gap │   │ resume        │   │ package +    │   │ digest,  │
   │ dedup,  │   │ + ATS     │   │ adaptation,   │   │ approve →    │   │ no-dup   │
   │ embed   │   │ scoring   │   │ cover letters │   │ applied      │   │ ledger   │
   └─────────┘   └───────────┘   └───────────────┘   └──────────────┘   └──────────┘
```

Two execution paths, one audit trail:
- **Chat path** (`POST /assistant/chat`): the LLM decides which tools to call — "find me GenAI jobs in Chennai", "tailor my resume for the best match", "what did you do today?"
- **Daily path** (cron / `POST /assistant/run`): a deterministic pipeline (same steps every morning, LLM spend only where it matters). Cheap, predictable, auditable.

Every tool call lands in `agent_runs` / `agent_actions` — the dashboard's activity feed shows exactly *what* the assistant did and *why*.

## No paid API key required 💸

Every LLM call goes through a **multi-provider router with automatic failover**. Configure ANY ONE of:

| Provider | Cost | Setup |
|---|---|---|
| **Groq** | free tier (Llama 3.3 70B) | [console.groq.com](https://console.groq.com) |
| **Google Gemini** | free tier | [aistudio.google.com](https://aistudio.google.com/apikey) |
| **Ollama** | 100% free, local | [ollama.com](https://ollama.com) → `ollama pull llama3.1` |
| OpenRouter | some free models | [openrouter.ai](https://openrouter.ai) |
| OpenAI | paid | [platform.openai.com](https://platform.openai.com) |

If a provider rate-limits or fails, the next configured one takes over automatically — the assistant keeps running 24/7 on free tiers. Tasks declare a **tier**, not a model: `fast` (resume parsing, job analysis) and `smart` (tailoring, cover letters, agent planning); each provider maps tiers to its own models (overridable in `.env`).

Embeddings are always local and free (`sentence-transformers/all-MiniLM-L6-v2`, 384-dim, stored in pgvector with an HNSW index). Job sources: **Remotive** and **Arbeitnow** need no keys; **Adzuna** (optional free key) adds country-specific listings and salary data.

## The truthfulness contract ✋

The Tailor never fabricates. Its prompts enforce: use only facts present in the resume; a skill may be surfaced **only with cited evidence**; requirements you genuinely lack go to **"honest gaps"** (with learning suggestions), never woven into rewrites. Auto-apply that stuffs forms behind your back, and LinkedIn scraping/automation, are deliberately **not** included — LinkedIn has no public API for this and automating it violates their ToS. Instead you get a prepared package and a one-click apply link.

## Quick start

```bash
git clone git@github.com:pr4vndevhubX/rolescout.git && cd rolescout

# Backend
python -m venv venv && source venv/bin/activate   # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env                              # fill in: 1 LLM key + Neon DATABASE_URL + JWT_SECRET
uvicorn app.main:app --reload                     # tables/pgvector/indexes auto-created

# Frontend (second terminal)
cd frontend && npm install && npm run dev         # http://localhost:5173
```

Minimum `.env` (everything else optional): `DATABASE_URL` ([neon.tech](https://neon.tech) free tier), `JWT_SECRET`, one LLM key (e.g. `GROQ_API_KEY`). Add SMTP settings for real email digests and `ASSISTANT_ENABLED=true` for the daily cron — see `.env.example` for the full annotated list.

**First run:** sign up in the UI → upload resume (auto-extracts) → Parse → Embed → set your desired roles in *Assistant Preferences* → hit **"Run daily cycle now"** (or just chat: *"find me AI/ML jobs"*).

## API overview

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/signup`, `POST /auth/login`, `GET /auth/me` |
| Resume pipeline | `POST /resumes/upload` → `/{id}/extract` → `/{id}/parse` → `/{id}/embed` |
| Jobs | `GET /jobs/sources`, `POST /jobs/ingest`, `POST /jobs/embed-pending` |
| Matching | `POST /resumes/{id}/matches/generate`, `GET /resumes/{id}/matches`, `PATCH /resumes/matches/{id}/status` (saved/dismissed/applied) |
| Tailoring | `POST /resumes/matches/{id}/tailor`, `POST /resumes/matches/{id}/cover-letter` |
| **Assistant** | `POST /assistant/chat`, `POST /assistant/run`, `GET /assistant/runs` |
| Preferences | `GET /preferences`, `PUT /preferences` |
| Applications | `GET /applications`, `PATCH /applications/{id}` (approved/applied/discarded) |

Interactive docs: `http://localhost:8000/docs`.

## How a daily cycle works

1. **Scout** — every desired role is searched on all sources; listings are validated, cross-source deduplicated (`sha1(title|company)`), "X+ years" requirements parsed, new jobs embedded.
2. **Evaluate** — one pgvector query retrieves the top-40 semantically similar jobs; hard filters (location / salary / years of experience) trim the pool; the LLM analyzes fit for the top 15 (5 in parallel); blended score = `0.6 × vector similarity + 0.4 × skill overlap`, plus ATS keyword/format scores.
3. **Classify** — `blended ≥ your threshold` → **strong fit**; below threshold but semantically close → **near miss**.
4. **Tailor** — near-misses (max 3/run, cost guard) get truthful tailoring suggestions.
5. **Prepare** — strong fits + tailored near-misses become application packages (dedup: one package per job, ever).
6. **Notify** — one digest email; the `notification_log` guarantees a job is never notified twice.

## Engineering notes

- **Layered**: routes → repositories → services → models; agent tools wrap the same services the REST API uses, so agent and API behavior can't drift.
- **Cost-aware**: LLM only on hard-filtered finalists; embeddings local & cached; stored matches read without recompute; step budget per agent run; tailoring capped per cycle.
- **Resilient**: per-provider retry + cross-provider failover; one failing job source never aborts ingestion; failing tools return errors to the agent instead of killing the run; failed cycles never kill the scheduler.
- **Extraction quality**: column-aware PDF parsing, OCR fallback for scanned PDFs (optional Tesseract), DOCX tables in document order, unicode/bullet/hyphenation cleanup, near-empty guardrails.
- **Tested + CI**: `pytest` suite (router failover, agent graph with a scripted fake LLM, daily-cycle classification, tailoring guardrails, digest rendering, connectors, skill gap, hard filters, text cleaning); GitHub Actions runs tests + frontend build on every push.
- **Security**: JWT auth (PBKDF2 passwords), per-user ownership checks on every resource, rate limiting, no stack-trace leaks, uploads validated by magic bytes, `storage/` (real resumes = PII) is git-ignored.

## Roadmap

- Browser-assisted apply for specific ATS families (Greenhouse/Lever) as an explicit opt-in.
- More sources (Jooble, JSearch, Naukri) — one connector file + one registry line each.
- S3-compatible resume storage for cloud deployment; Telegram as a second notification channel.
