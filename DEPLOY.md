# Deploying Tearsheet (for a public CV / portfolio site)

This app is **two services**: a Next.js frontend and a Python/FastAPI backend. Netlify hosts the
frontend; the backend needs a Python host (Render's free tier works well). They talk over HTTPS.

> **Why not "run locally"?** A visitor to your site is on their own computer — they can't reach
> your laptop's `localhost`. A public site must have both services hosted. "Run locally" is only
> for *you* developing.

> **Data strategy for a public site.** Free live data does not scale to public traffic (Yahoo
> blocks cloud IPs; FMP free is 250 calls/day shared across *all* visitors). So deploy with
> **Offline mode as the reliable default**, backed by **real snapshots** (always works, no limits),
> and keep **Live** as a flagged, best-effort option. The UI's Live/Offline toggle already does
> exactly this.

---

## 0. Before you deploy — bake the snapshot data

Offline mode serves `backend/app/providers/fixtures/*.json`. Fill it with real data once (needs your
FMP key + an unspent daily quota):

```bash
cd backend && source .venv/bin/activate
python -m scripts.snapshot            # ~15 stocks + ~13 ETFs, real data
git add app/providers/fixtures && git commit -m "Refresh snapshot dataset"
```
These JSON files ship with the backend, so the deployed site has real (point-in-time) data for the
whole basket with zero runtime API calls. Re-run occasionally to refresh.

---

## 1. Backend → Render (free web service)

1. Push this repo to GitHub.
2. Render → **New → Web Service** → connect the repo.
3. Settings:
   - **Root Directory:** `backend`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. **Environment variables:**
   | Key | Value |
   |---|---|
   | `DATA_PROVIDER` | `fmp` (Live works, limited) — or `fixture` for a pure snapshot site |
   | `FMP_API_KEY` | your free FMP key (only if `DATA_PROVIDER=fmp`) |
   | `CORS_ORIGINS` | your Netlify URL, e.g. `https://tearsheet.netlify.app` |
   | `ANTHROPIC_API_KEY` | optional — real thesis instead of the mock |
   | `ANTHROPIC_MODEL` | optional — e.g. `claude-haiku-4-5` to cut cost |

   A [`render.yaml`](render.yaml) is included so you can also use Render's **Blueprint** flow.
5. Deploy. Note the URL, e.g. `https://tearsheet-api.onrender.com`. Test `…/health`.

> Render free tier sleeps after ~15 min idle → the first request after idle takes ~30–50s (cold
> start). Fine for a portfolio; mention it or add a tiny "waking up…" state if you like.

---

## 2. Frontend → Netlify

1. Netlify → **Add new site → Import from Git** → same repo.
2. Settings:
   - **Base directory:** `frontend`
   - **Build command:** `npm run build`
   - **Publish directory:** `frontend/.next` (Netlify auto-installs the Next.js runtime)
3. **Environment variable:**
   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE` | your Render backend URL, e.g. `https://tearsheet-api.onrender.com` |
4. Deploy. Set `CORS_ORIGINS` on Render to the final Netlify URL and redeploy the backend.

> **Simpler alternative:** deploy the frontend on **Vercel** instead (native Next.js, zero config) —
> same `NEXT_PUBLIC_API_BASE` env var. Use whichever you prefer; the backend setup is identical.

---

## 3. Recommended public config

| Goal | DATA_PROVIDER | Notes |
|---|---|---|
| **Bulletproof CV demo** (recommended) | `fixture` | Offline-only, real snapshots, never breaks, $0, no keys. Toggle still shows but both sides serve snapshots. |
| **Demo + best-effort live** | `fmp` | Live works until the 250/day shared quota is spent, then auto-falls-back to snapshots (flagged). Offline always works. |
| **Fully live** | `fmp` + paid plan | Real data for all visitors; costs money. |

For interviews, the **story** is the value: the `DataProvider` swap point, the DCF + reasoning
modules, and the eval harness — not whether a quote is live. Point recruiters at the README and
`python eval/run_eval.py`.

---

## Checklist
- [ ] `python -m scripts.snapshot` run; fixtures committed
- [ ] Backend on Render; `/health` returns ok
- [ ] `CORS_ORIGINS` = the Netlify URL
- [ ] Frontend on Netlify with `NEXT_PUBLIC_API_BASE` = the Render URL
- [ ] `.env` is NOT in git (it's gitignored); keys are set as host env vars
- [ ] Toggle works; badge shows LIVE / OFFLINE SNAPSHOT correctly
