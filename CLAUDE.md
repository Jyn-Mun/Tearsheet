# Tearsheet — Agent guide (read every session)

A "mini Capital IQ" equity-research terminal: enter a ticker → get a sourced, structured
research brief (fundamentals, valuation, DCF, peers, news, AI thesis), built on **free data
only**, with a Python eval harness that scores its own factual accuracy and citation validity.

## Non-negotiable rules

### Grounding contract (the most important rule)
- **Numbers only from retrieved data.** The synthesis/UI layers may only use figures present in
  the retrieved payload. Never invent, estimate, or "fill in" a number.
- **If a fact is absent, return `null` / "n/a" — never guess.**
- **Cite every qualitative claim** with a real `source_url` taken from the retrieved payload, plus
  a retrieval timestamp. No invented URLs, ever.
- This is enforced twice: by prompt design (synthesis) and by the eval harness (hallucination +
  citation checks).

### No financial advice
- Outputs are **model results with stated assumptions**, never buy/sell/hold recommendations or
  price targets-as-advice. The "not financial advice" disclaimer must stay visible in the UI.

### Free data only / no secrets in the repo
- No paid data sources. All keys live in `backend/.env` (gitignored); ship `.env.example` only.
- **v1 data source is `yfinance` (Yahoo Finance) only** — no key, no personal info required.
  SEC EDGAR is intentionally deferred and stubbed behind the `DataProvider` interface
  (`providers/edgar_provider.py`) as a documented future swap. Do **not** wire EDGAR or add a
  `SEC_USER_AGENT` without an explicit instruction.

### The swap point (architecture)
- Everything that touches the outside world lives behind `backend/app/providers/base.py::DataProvider`.
- Swapping the data/retrieval layer onto another web-data API is **one new class** implementing the
  same interface. Keep it that way.

## UI work
- **Before any frontend/UI work, read [`frontend/DESIGN.md`](frontend/DESIGN.md) in full** and follow
  it exactly (colour tokens, fonts, layout, the forbidden "AI-slop" list). It is the single source of
  truth for the look. When available, use the `frontend-design` skill for UI phases.

## Stack
- Backend: Python 3.11 + FastAPI (`backend/`), `venv` + `pip` + pinned `requirements.txt`.
- Frontend: Next.js App Router + TanStack Query (`frontend/`), npm with committed lockfile, deps pinned.
- Data: `yfinance` only for v1, behind `DataProvider`.
- LLM: Anthropic API for synthesis (deferred until a key exists; built behind a `Synthesizer`
  interface with a deterministic mock default).
- Eval: `eval/run_eval.py`.

## Run (dev)
- Backend: `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000`
- Frontend: `cd frontend && npm install && npm run dev` (http://localhost:3000)
- Backend base URL the frontend calls: `http://localhost:8000` (via `NEXT_PUBLIC_API_BASE`).

## Repo map
```
backend/app/
  main.py            FastAPI entry, CORS, router include
  config.py          settings (pydantic-settings, reads .env)
  routes/            one module per endpoint group (health, company, financials, ...)
  services/          edgar (stub), yahoo, dcf_engine, news, analysis
  providers/         base.py (interface) + free_provider.py (yfinance impl) + edgar_provider.py (stub)
  models/            pydantic schemas (normalized financials, provenance)
  utils/             financial_math.py, cache.py (on-disk TTL cache)
frontend/            Next.js App Router; DESIGN.md = UI source of truth
eval/                testset.json + run_eval.py
```
