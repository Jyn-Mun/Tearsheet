# Tearsheet — AI equity-research terminal

A "mini Capital IQ" research terminal. Enter a ticker → get a sourced, structured equity-research
brief — fundamentals, valuation, a transparent DCF, peers, news, and an AI bull/bear thesis — built
on **free data only**, with a Python evaluation harness that scores its own factual accuracy,
citation validity, and hallucinations.

> **Research tool, not financial advice.** No buy/sell/hold calls, no price targets. Intrinsic
> value and upside/downside are shown as *model outputs with stated assumptions* — never a
> recommendation. This is enforced at runtime and in the eval suite.

It doesn't just *retrieve and compute* — it *reasons and interprets*: it explains what each signal
means, where the signals agree or conflict, why a price moved, and how a stock behaves around
earnings — while stopping precisely at the line before advice.

---

## Architecture

```
            ┌────────────────────────── DataProvider (the swap point) ──────────────────────────┐
            │  FreeProvider (live yfinance)   ·   FixtureProvider (recorded sample, offline)     │
            │  → one normalized, provenance-tagged CompanyPayload                                │
            └───────────────────────────────────────┬───────────────────────────────────────────┘
                                                     │
   ┌─────────────────────────────────────────────── services ───────────────────────────────────────────┐
   │ financials · valuation (+peers) · dcf_engine (+reverse-DCF) · event_analytics · interpretation ·     │
   │ move attribution · Synthesizer [Anthropic | grounded mock]  ← Investor Reasoning Layer + grounding    │
   └─────────────────────────────────────────────────┬──────────────────────────────────────────────────┘
                                                      │ FastAPI (10 endpoints, clean JSON + provenance)
                                                      │
                         Next.js App Router + TanStack Query  →  "analyst terminal" UI
                                                      │
                                       eval/run_eval.py  (scores the agent)
```

### The swap point (the FDE story)
Everything that touches the outside world lives behind
[`backend/app/providers/base.py`](backend/app/providers/base.py)`::DataProvider`. The v1
implementation is `FreeProvider` (yfinance). **Swapping the data/retrieval layer onto any other
web-data API — a commercial search/retrieval API, or SEC EDGAR — is one new class implementing the
same interface.** `FixtureProvider` (recorded synthetic samples) is a second implementation used
for offline dev, deterministic tests, and the eval harness — proof the seam is real.

> **Note on data in this build:** SEC EDGAR is intentionally deferred (it requires a descriptive
> contact `User-Agent`); v1 uses Yahoo Finance via `yfinance` only — no API key, no personal info.
> If Yahoo rate-limits, the app transparently falls back to clearly-labelled **sample** data so it
> stays usable; sample data is never passed off as live.

---

## Endpoints

| Endpoint | What it returns |
|---|---|
| `GET /company/{ticker}`       | profile, price, sparkline, key metrics |
| `GET /financials/{ticker}`    | income / balance / cash-flow, 3–5y, YoY |
| `GET /valuation/{ticker}`     | multiples (+ derived ROIC / FCF-yield) + sector-approx peers |
| `GET /dcf/{ticker}`           | transparent DCF: assumptions, projection, intrinsic value, sensitivity, guardrails |
| `GET /news/{ticker}`          | headlines + AI summary + sentiment |
| `GET /analysis/{ticker}`      | grounded, **falsifiable**, two-sided thesis + pre-mortem |
| `GET /events/{ticker}`        | earnings-behaviour stats (n + dispersion) — separates *beats* from *up* |
| `GET /interpret/{ticker}`     | per-signal meaning + reverse-DCF "what's priced in" + coherence map |
| `GET /explain-move/{ticker}`  | market / sector / idiosyncratic attribution + transient/structural + thesis impact |

### What makes it senior, not a demo
- **Grounding contract.** Numbers only from retrieved data; every claim carries a real source URL;
  "n/a" over guessing. Enforced by prompt design *and* the eval harness.
- **Investor Reasoning Layer.** Every bull/bear point ships a **falsifier** (the metric/event that
  would break it) plus a pre-mortem — analysis, not narrative.
- **Transparent DCF.** Explicit CAPM WACC, growth fade, Gordon terminal value with a `WACC > g`
  guard, a WACC×g sensitivity matrix, and unreliability flags (unprofitable / financial-sector /
  negative-FCF). Plus a **reverse-DCF** that solves for the growth the *current price* implies.
- **Interpretation over retrieval.** A coherence map that **names conflicts** instead of averaging
  them, and a move-attribution engine that answers "is it the company, or is it everything?".
- **No-advice invariant**, negation-aware (passes legitimate disclaimers, catches real advice),
  enforced across every synthesised endpoint and gated in the eval.

---

## Evaluation harness

```bash
python eval/run_eval.py
```
Prints a single summary line, e.g.:
```
Accuracy: 100% (4/4) · Citation validity: 100% (4/4) · Hallucinations: 0/2 ·
DCF checks: 2/2 · No-advice gate: PASS · Falsifiers: 4/4 · Attribution/conflict: 2/2
```
It scores factual accuracy, citation validity (domains must resolve to expected real domains),
hallucinations (any number not in the retrieved payload — with a negative-control case proving the
detector fires), DCF numeric correctness (independent recompute + the `WACC>g` guard), and the
addendum gates: no-advice (hard), falsifiers, the *beats ≠ up* bias correction, broad-selloff
attribution, and conflict surfacing. Runs **in-process against the fixture provider** — no network,
no API key — so it's deterministic; the same checks run unchanged against the live provider.

---

## Run it

**Prereqs:** Python 3.11, Node 20.

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # no keys required for v1
uvicorn app.main:app --reload --port 8000
#   Offline/deterministic demo (recommended if Yahoo rate-limits you):
#   DATA_PROVIDER=fixture uvicorn app.main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
cp .env.local.example .env.local
npm install
npm run dev                               # http://localhost:3000

# 3. Eval (optional)
python eval/run_eval.py

# 4. Tests
cd backend && pytest -q
```

### Optional keys (`.env`, backend-only, never committed)
- `ANTHROPIC_API_KEY` — enables real LLM synthesis (News + Analysis). **Without it the app runs a
  deterministic, grounded mock synthesizer** — every endpoint works, the mock honours the grounding
  and no-advice contracts; it's just less insightful. Model: `claude-opus-4-8` (adaptive thinking,
  JSON-schema structured output).
- `FRED_API_KEY` — uses the 10y Treasury (DGS10) as the DCF risk-free rate; otherwise a documented
  fallback is used.

---

## Deploy (free: Netlify + Render)

Frontend on **Netlify**, FastAPI backend on **Render** free tier. Public build is **research-only**
(no trading routes — `ENABLE_TRADING=false`). Full walkthrough + checklist in
[`DEPLOY.md`](DEPLOY.md).

- **Render start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (root dir `backend`)
- **Netlify env var:** `NEXT_PUBLIC_API_URL` = your Render backend URL
- **CORS:** locked to `FRONTEND_ORIGIN` (your Netlify URL) — never `*`

### Environment variables (backend, all via env — never committed)
| Var | Purpose |
|---|---|
| `SEC_USER_AGENT` | descriptive contact for SEC EDGAR (required, sent on every request) |
| `TWELVEDATA_API_KEY` | free key (twelvedata.com) for cloud-reliable prices/history; else yfinance (blocked on cloud IPs) |
| `FRONTEND_ORIGIN` | exact Netlify origin allowed by CORS (production) |
| `DATA_PROVIDER` | `hybrid` / `edgar` / `free` / `fixture` |
| `ENABLE_TRADING` | research-only guard — keep `false` in production |
| `FRED_API_KEY` | optional — 10y Treasury for the DCF risk-free rate |
| `ANTHROPIC_API_KEY` | optional — enables AI narrative (else a clean "disabled" note) |
| `OLLAMA_MODEL` | optional — free local-LLM narrative fallback |

The site degrades gracefully with **zero paid services**: no Anthropic key → clean "AI narrative
disabled" note + all numeric sections work; no FRED key → documented risk-free fallback. Free-tier
cold starts show an intentional "Waking the server…" banner on first load.

## Design

The UI is a deliberate **analyst-terminal** aesthetic — dark, data-dense, hairline-bordered
modules, one amber accent, green/red for deltas only, industrial-grotesque headings (Mona Sans),
and **tabular monospace numerals everywhere** (JetBrains Mono). The full spec — the single source of
truth, loaded every session — is [`frontend/DESIGN.md`](frontend/DESIGN.md). Grounding and
architecture rules live in [`CLAUDE.md`](CLAUDE.md).

## Repo layout
```
backend/   FastAPI · providers (swap point) · services (DCF, synthesis, reasoning modules) · tests
frontend/  Next.js App Router · components (terminal modules) · DESIGN.md
eval/      testset.json + run_eval.py
```

## Status & scope
v1 covers the data layer, financials/valuation, the DCF engine, grounded synthesis with the Investor
Reasoning Layer, and the four interpretation modules (events, interpretation, move explanation), the
terminal UI, and the eval harness. Out of scope for v1: live trading, accounts, intraday streaming,
ML price prediction, and coverage guarantees for micro-caps / ADRs / non-US listings (degrade
gracefully). **Not financial advice.**
