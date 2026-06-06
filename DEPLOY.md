# Deploying Tearsheet — Frontend on Netlify, Backend on Render (free)

Two services: a **Next.js frontend** (Netlify) and a **FastAPI backend** (Render free tier).
Visitors only ever see the Netlify URL; the frontend calls the backend over HTTPS. The public
build is **research-only** — no broker/trading/execution routes are mounted (guarded by
`ENABLE_TRADING`, off by default).

> **Heads-up on free hosting:** Render free sleeps after ~15 min idle, so the first request after
> idle takes ~30–60s to wake — the UI shows an intentional "Waking the server…" banner for this.
>
> **Prices in the cloud (don't scrape Yahoo):** `yfinance` is blocked from datacenter IPs. The
> production path is a **keyed API + cache + pre-fetch**, not a scraper — see *Resilience* below.

---

## 1. Backend → Render

1. Push the repo to GitHub.
2. Render → **New → Web Service** → connect the repo (or use the included `render.yaml` via
   **New → Blueprint**).
3. Settings:
   - **Root Directory:** `backend`
   - **Runtime:** Python 3 (pinned by `backend/.python-version` = 3.11.9)
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:**
     ```
     uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
     (A `backend/Procfile` with the same line is included as a fallback.)
   - **Health Check Path:** `/health`
4. **Environment variables** (Dashboard → Environment):

   | Key | Value | Required |
   |---|---|---|
   | `SEC_USER_AGENT` | `Tearsheet/1.0 (you@example.com)` | ✅ |
   | `FRONTEND_ORIGIN` | your Netlify URL, e.g. `https://your-site.netlify.app` | ✅ (CORS lock) |
   | `DATA_PROVIDER` | `hybrid` | ✅ |
   | `DATA_SOURCE` | `alpaca` (keyed, cloud-safe) — **prod**; or `twelvedata` | ✅ |
   | `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` | free Alpaca keys (or `TWELVEDATA_API_KEY`) | ★ for prices |
   | `SERVE_FROM_CACHE_ONLY` | `true` — request path serves stored data only | ★ resilience |
   | `ENABLE_PREFETCH` | `true` — warm the cache on a schedule | ★ resilience |
   | `PREFETCH_INTERVAL_HOURS` / `PREFETCH_TICKERS` | `6` / configurable list | optional |
   | `ENABLE_TRADING` | `false` | ✅ (keep off) |
   | `FRED_API_KEY` | free FRED key (else 4.3% fallback) | optional |
   | `ANTHROPIC_API_KEY` | enables AI narrative (else clean "disabled" note) | optional |

5. Deploy. Confirm `https://<your-api>.onrender.com/health` returns `{"status":"ok"}`.

---

## 2. Frontend → Netlify

1. Netlify → **Add new site → Import from Git** → same repo.
2. Build settings (also in `netlify.toml`):
   - **Base directory:** `frontend`
   - **Build command:** `npm run build`
   - **Publish directory:** `frontend/.next` (Netlify auto-installs the Next.js runtime)
3. **Environment variable:**

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | your Render backend URL, e.g. `https://tearsheet-api.onrender.com` |

   > This is **Next.js**, so the prefix is `NEXT_PUBLIC_` (Vite's `VITE_` does not apply).
4. Deploy. Then set Render's `FRONTEND_ORIGIN` to the final Netlify URL and redeploy the backend.

> **Simpler alt:** **Vercel** also hosts the Next.js frontend with the same `NEXT_PUBLIC_API_URL`
> var — use whichever you prefer; the backend setup is identical.

---

## 3. Recommended public config

| Goal | `DATA_PROVIDER` | Visitors see |
|---|---|---|
| **Every section populated, bulletproof** (best for a CV demo) | `fixture` | A baked basket of real companies — all sections incl. price/charts, instant, no cold-data gaps |
| Any-ticker live | `hybrid` | Any US/foreign filer's fundamentals + scores + DCF live; price/multiples best-effort (cloud Yahoo block) |

Bake the offline basket (run locally where Yahoo isn't blocked), then commit:
```bash
cd backend && source .venv/bin/activate && python -m scripts.snapshot
git add app/providers/fixtures && git commit -m "Refresh snapshot basket"
```

---

## Resilience — keyed API + cache + pre-fetch (no Yahoo scraping)

The production path never depends on live Yahoo. Three layers:

**1. Pluggable, keyed market source (`DATA_SOURCE`).** EDGAR (fundamentals) + FRED (macro) aren't
IP-blocked and stay as-is. The *price* source is swappable behind the `DataProvider` interface:
- `DATA_SOURCE=alpaca` — **production.** Alpaca market data is keyed (header auth), so it works from
  a shared cloud IP. Free IEX feed gives quotes, ~2y daily bars (charts/risk/move), and news.
  Market cap = price × EDGAR shares; all multiples computed in code.
- `DATA_SOURCE=twelvedata` — alternative keyed API (`TWELVEDATA_API_KEY`).
- `DATA_SOURCE=yfinance` — **local dev only** (routed through a curl_cffi browser session + backoff
  as a fallback — never the production path).

**2. TTL cache (mandatory).** Every external fetch is cached on disk: **prices ~5 min, EDGAR
fundamentals ~12h**. So it's **one upstream call per ticker per window, shared by all visitors** —
not one per visitor.

**3. Pre-fetch + cache-only.** Set `SERVE_FROM_CACHE_ONLY=true` and `ENABLE_PREFETCH=true`. The
in-process scheduler warms the cache for `PREFETCH_TICKERS` (~25 popular names, configurable) every
`PREFETCH_INTERVAL_HOURS`, and the **request path then serves ONLY stored data — it never calls
upstream live.** Only the pre-fetch job (`live_fetch()`) is permitted to hit the API.

> **Confirmed:** with `SERVE_FROM_CACHE_ONLY=true`, a request for a not-yet-fetched ticker returns
> empty (no upstream call); after the pre-fetch job runs, the same request is served from stored
> data — still no live call. (See `tests/test_resilience.py`.)

Run the pre-fetch on a schedule one of three ways:
- **In-process scheduler** (default, free) — `ENABLE_PREFETCH=true`; runs on the Render instance.
- **Render Cron Job** (if you upgrade) — command `python -m scripts.prefetch` (root `backend`).
- **GitHub Actions cron** — run `python -m scripts.prefetch` against a checkout, or curl a
  token-protected trigger; commit the warmed snapshots if you want them in git.

Extra resilience: keep `DATA_PROVIDER`'s snapshot fallback on — if the cache is cold for a ticker
that has a baked snapshot, it serves that instead of n/a.

---

## CORS (what's configured)

`backend/app/main.py` locks CORS to `settings.allowed_origins`, which is **`FRONTEND_ORIGIN`** when
set (production) — exact origin only, never `*` — falling back to `CORS_ORIGINS` for local dev.
Methods are GET-only; credentials are off (public data, no auth/cookies).

---

## Deploy checklist

- [ ] Repo pushed to GitHub; `.env` is **not** committed (gitignored)
- [ ] Render web service: root `backend`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- [ ] Render env: `SEC_USER_AGENT`, `FRONTEND_ORIGIN` (= Netlify URL), `DATA_PROVIDER`, `ENABLE_TRADING=false`
- [ ] `https://<api>.onrender.com/health` → `{"status":"ok"}`
- [ ] Netlify site: base `frontend`, env `NEXT_PUBLIC_API_URL` (= Render URL)
- [ ] Re-set `FRONTEND_ORIGIN` to the final Netlify URL; redeploy backend
- [ ] Open the Netlify URL → first load shows the "Waking the server…" banner, then the terminal loads
- [ ] (Optional) `python -m scripts.snapshot` locally + commit for a fully-populated `fixture` build
