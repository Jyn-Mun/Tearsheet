"""Generate clearly-labelled SYNTHETIC fixture payloads for offline dev / tests / eval.

These are NOT real market data. They are seeded, reproducible, and engineered to exercise
specific behaviours from the PRD addendum:
  - NVDA: a serial earnings beater whose stock often falls post-print (beats != up), and a
    2026-06-05 session that decomposes into mostly MARKET + SECTOR (a broad selloff).
  - SPY / SMH: index + semis-sector ETFs.

Crucially, the three series share a common market factor (m) and sector factor (s) so that a
beta regression recovers a realistic beta (~1.5) and the move-attribution engine decomposes the
final session into market/sector rather than idiosyncratic. Returns are generated from the
factor model, then cumulated into prices.

Run:  python -m scripts.build_fixtures   (from backend/, venv active)
Output: app/providers/fixtures/*.json  (source label = "fixture (recorded sample)").
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "providers" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)

START = date(2024, 6, 5)
END = date(2026, 6, 5)
SOURCE = "fixture (recorded sample)"
AS_OF = "2026-06-05T21:00:00+00:00"

# Factor loadings for NVDA (the subject): exposure to market and sector factors + small idio.
NVDA_BETA_M = 1.5
NVDA_BETA_S = 1.2


def trading_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def cumulate(returns: list[float], start_px: float) -> list[float]:
    px, out = start_px, []
    for r in returns:
        px *= (1 + r)
        out.append(round(px, 2))
    return out


def warp_post_earnings(closes: list[float], idx: int, target_post5: float) -> None:
    """Reshape closes[idx+1 .. idx+5] to a cumulative `target_post5` return vs closes[idx],
    then scale the remainder to stay continuous. Engineers beat!=up patterns."""
    if idx + 5 >= len(closes):
        return
    base = closes[idx]
    old_anchor = closes[idx + 5]
    for k in range(1, 6):
        closes[idx + k] = round(base * (1 + target_post5 * (k / 5.0)), 2)
    new_anchor = closes[idx + 5]
    ratio = new_anchor / old_anchor if old_anchor else 1.0
    for j in range(idx + 6, len(closes)):
        closes[j] = round(closes[j] * ratio, 2)


def history_payload(days, closes) -> list[dict]:
    return [{"date": d.isoformat(), "close": c} for d, c in zip(days, closes)]


def _synthetic_financials(base_rev: float, growth: list[float], margin: float) -> dict:
    years = [2025, 2024, 2023, 2022]
    revs = [base_rev]
    for g in growth[1:]:
        revs.append(revs[-1] / (1 + g))
    income, balance, cashflow = [], [], []
    for i, yr in enumerate(years):
        rev = round(revs[i]); ebit = round(rev * margin); ni = round(ebit * 0.86)
        da = round(rev * 0.03); capex = -round(rev * 0.04); cwc = -round(rev * 0.02)
        income.append({"fiscal_year": yr, "period_end": f"{yr}-01-26", "revenue": rev,
                       "cost_of_revenue": round(rev * 0.26), "gross_profit": round(rev * 0.74),
                       "operating_income": ebit, "ebitda": ebit + da, "pretax_income": round(ebit * 1.02),
                       "tax_provision": round(ebit * 0.14), "net_income": ni, "interest_expense": round(rev * 0.002)})
        balance.append({"fiscal_year": yr, "period_end": f"{yr}-01-26", "total_assets": round(rev * 1.4),
                        "total_liabilities": round(rev * 0.4), "cash_and_equivalents": round(rev * 0.29),
                        "total_debt": round(rev * 0.07), "stockholders_equity": round(rev * 1.0),
                        "current_assets": round(rev * 0.8), "current_liabilities": round(rev * 0.22),
                        "working_capital": round(rev * 0.58)})
        cashflow.append({"fiscal_year": yr, "period_end": f"{yr}-01-26", "operating_cash_flow": round(ni + da - cwc),
                         "capital_expenditure": capex, "free_cash_flow": round(ni + da - cwc + capex),
                         "depreciation_amortization": da, "change_in_working_capital": cwc})
    return {"income": income, "balance": balance, "cashflow": cashflow}


def _etf_payload(ticker, name, days, closes) -> dict:
    cur, prev = closes[-1], closes[-2]
    return {
        "ticker": ticker, "as_of": AS_OF, "source": SOURCE,
        "profile": {"name": name, "sector": "Index/ETF", "summary": "[SYNTHETIC SAMPLE] reference series."},
        "price": {"current": cur, "previous_close": prev, "change_abs": round(cur - prev, 2),
                  "change_pct": round((cur - prev) / prev, 4), "market_cap": None, "beta": 1.0,
                  "history": history_payload(days, closes)},
        "key_metrics": {}, "financials": {"income": [], "balance": [], "cashflow": []},
        "earnings": [], "news": [],
        "provenance": {"price": {"source": SOURCE, "source_url": None, "retrieved_at": AS_OF}},
        "warnings": ["Synthetic recorded-sample data — not real market figures."],
    }


def main() -> None:
    days = trading_days(START, END)
    n = len(days)
    rng_m = random.Random(7)
    rng_s = random.Random(9)
    rng_e = random.Random(42)

    # Daily factor returns.
    m = [0.0004 + 0.009 * rng_m.gauss(0, 1) for _ in range(n)]            # market
    s = [0.012 * rng_s.gauss(0, 1) for _ in range(n)]                     # sector (indep. of market)
    e = [0.006 * rng_e.gauss(0, 1) for _ in range(n)]                     # NVDA idiosyncratic

    # Engineer the FINAL session (2026-06-05) as a broad selloff:
    #   SPY -1.9%, SMH -4.1% (sector factor s = SMH - market = -2.2%), NVDA via factor model.
    m[-1] = -0.019
    s[-1] = -0.022
    e[-1] = -0.006

    spy_ret = m[:]                                # SPY = market factor
    smh_ret = [m[i] + s[i] for i in range(n)]     # SMH = market + sector
    nvda_ret = [0.0011 + NVDA_BETA_M * m[i] + NVDA_BETA_S * s[i] + e[i] for i in range(n)]

    spy = cumulate(spy_ret, 520.0)
    smh = cumulate(smh_ret, 240.0)
    nvda = cumulate(nvda_ret, 95.0)

    # Engineer quarterly earnings: almost always beats, post-move frequently negative (beat!=up).
    idx_by_date = {d: i for i, d in enumerate(days)}
    events = [
        (date(2024, 8, 28), 0.64, 0.68, -0.061), (date(2024, 11, 20), 0.75, 0.81, +0.018),
        (date(2025, 2, 26), 0.84, 0.89, -0.042), (date(2025, 5, 28), 0.88, 0.96, -0.085),
        (date(2025, 8, 27), 0.95, 1.05, +0.031), (date(2025, 11, 19), 1.02, 1.13, -0.037),
        (date(2026, 2, 25), 1.10, 1.20, -0.029), (date(2026, 5, 27), 1.18, 1.31, +0.044),
    ]
    earnings = []
    for ed, est, act, post5 in events:
        snap = ed
        while snap not in idx_by_date and snap <= END:
            snap += timedelta(days=1)
        if snap in idx_by_date and idx_by_date[snap] + 5 < n - 2:
            warp_post_earnings(nvda, idx_by_date[snap], post5)
        earnings.append({"date": ed.isoformat(), "eps_estimate": est, "eps_actual": act,
                         "surprise_pct": round((act - est) / est * 100, 1)})

    # Re-pin the final selloff after any warps so the worked example is exact.
    spy[-1] = round(spy[-2] * (1 + m[-1]), 2)
    smh[-1] = round(smh[-2] * (1 + smh_ret[-1]), 2)
    nvda[-1] = round(nvda[-2] * (1 + nvda_ret[-1]), 2)

    cur, prev = nvda[-1], nvda[-2]
    nvda_payload = {
        "ticker": "NVDA", "as_of": AS_OF, "source": SOURCE,
        "profile": {"name": "NVIDIA Corporation", "exchange": "NMS", "sector": "Technology",
                    "industry": "Semiconductors", "country": "United States",
                    "summary": "[SYNTHETIC SAMPLE] Designs accelerated-computing GPUs and platforms for "
                    "data centre, gaming, and AI workloads. Figures here are illustrative, not real.",
                    "employees": 29600, "currency": "USD"},
        "price": {"current": cur, "previous_close": prev, "change_abs": round(cur - prev, 2),
                  "change_pct": round((cur - prev) / prev, 4),
                  "fifty_two_week_high": round(max(nvda[-252:]), 2),
                  "fifty_two_week_low": round(min(nvda[-252:]), 2),
                  "market_cap": round(cur * 24.3e9), "beta": 1.55, "history": history_payload(days, nvda)},
        "key_metrics": {"pe_ttm": 41.5, "forward_pe": 30.2, "ev_ebitda": 35.1, "ps": 22.4, "pb": 38.0,
                        "dividend_yield": 0.0003, "gross_margin": 0.749, "operating_margin": 0.622,
                        "net_margin": 0.553, "roe": 0.915, "roic": None, "fcf_yield": None,
                        "shares_outstanding": 24.3e9, "total_debt": 9.5e9, "total_cash": 38.0e9, "ebitda": 88.0e9},
        "financials": _synthetic_financials(130.5e9, [0.0, 0.262, 1.262, 0.61], 0.62),
        "earnings": earnings,
        "news": [
            {"title": "[SAMPLE] Chip stocks slide as hot jobs report lifts rate expectations",
             "publisher": "Sample Newswire", "url": "https://finance.yahoo.com/news/sample-chips-rates",
             "published": "2026-06-05T13:40:00+00:00",
             "summary": "Stronger-than-expected May payrolls pushed Treasury yields higher, pressuring "
             "long-duration and high-multiple technology shares broadly."},
            {"title": "[SAMPLE] NVIDIA reaffirms data-centre demand outlook at investor event",
             "publisher": "Sample Markets", "url": "https://finance.yahoo.com/news/sample-nvda-demand",
             "published": "2026-06-04T15:10:00+00:00",
             "summary": "Management pointed to a sustained order book and capacity expansion; no change to guidance."},
        ],
        "provenance": {k: {"source": SOURCE, "source_url": "https://finance.yahoo.com/quote/NVDA",
                           "retrieved_at": AS_OF}
                       for k in ["profile", "price", "key_metrics", "financials", "earnings", "news"]},
        "warnings": ["Synthetic recorded-sample data — not real market figures."],
    }

    fixtures = {
        "NVDA": nvda_payload,
        "SPY": _etf_payload("SPY", "S&P 500 ETF (sample)", days, spy),
        "SMH": _etf_payload("SMH", "Semiconductor ETF (sample)", days, smh),
    }
    for tk, payload in fixtures.items():
        (OUT / f"{tk}.json").write_text(json.dumps(payload, indent=2))
        print(f"wrote {tk}.json ({len(payload['price']['history'])} pts, last={payload['price']['current']})")


if __name__ == "__main__":
    main()
