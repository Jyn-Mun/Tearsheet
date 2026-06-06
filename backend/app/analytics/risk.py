"""Price / risk metrics — pure functions over a daily close series (numpy). Every metric carries
its sample size. Returns None (not a crash) when there isn't enough history.

Definitions:
  daily returns r_t = close_t/close_{t-1} − 1
  annualized vol = std(r) · √252
  Sharpe  = (mean(r)·252 − rf) / (std(r)·√252)
  Sortino = (mean(r)·252 − rf) / (std(downside r)·√252)
  max drawdown = min_t (close_t / running_max_t − 1)
  beta = cov(r_stock, r_index) / var(r_index)
  12-1 momentum = close_{−21} / close_{−252} − 1   (skip the most recent month)
  RSI(14) = 100 − 100/(1 + avg gain / avg loss)
"""

from __future__ import annotations

import numpy as np

_TRADING_DAYS = 252


def _returns(closes: list[float]) -> np.ndarray:
    a = np.asarray([c for c in closes if c is not None], dtype=float)
    if a.size < 2:
        return np.array([])
    return a[1:] / a[:-1] - 1.0


def annualized_vol(closes: list[float]) -> dict:
    r = _returns(closes)
    if r.size < 20:
        return {"value": None, "n": int(r.size), "reason": "need ≥20 daily returns"}
    return {"value": float(r.std(ddof=1) * np.sqrt(_TRADING_DAYS)), "n": int(r.size)}


def sharpe(closes: list[float], rf: float = 0.0) -> dict:
    r = _returns(closes)
    if r.size < 20 or r.std() == 0:
        return {"value": None, "n": int(r.size)}
    ann_ret = r.mean() * _TRADING_DAYS
    ann_vol = r.std(ddof=1) * np.sqrt(_TRADING_DAYS)
    return {"value": float((ann_ret - rf) / ann_vol), "n": int(r.size), "rf": rf}


def sortino(closes: list[float], rf: float = 0.0) -> dict:
    r = _returns(closes)
    downside = r[r < 0]
    if r.size < 20 or downside.size == 0 or downside.std() == 0:
        return {"value": None, "n": int(r.size)}
    ann_ret = r.mean() * _TRADING_DAYS
    dd = downside.std(ddof=1) * np.sqrt(_TRADING_DAYS)
    return {"value": float((ann_ret - rf) / dd), "n": int(r.size), "rf": rf}


def max_drawdown(closes: list[float]) -> dict:
    a = np.asarray([c for c in closes if c is not None], dtype=float)
    if a.size < 2:
        return {"value": None, "n": int(a.size)}
    peak = np.maximum.accumulate(a)
    dd = a / peak - 1.0
    return {"value": float(dd.min()), "n": int(a.size)}


def beta_corr(stock_closes: list[float], index_closes: list[float]) -> dict:
    s, m = _returns(stock_closes), _returns(index_closes)
    n = min(s.size, m.size)
    if n < 30:
        return {"beta": None, "correlation": None, "n": int(n), "reason": "need ≥30 aligned returns"}
    s, m = s[-n:], m[-n:]
    var = m.var()
    beta = float(np.cov(s, m)[0, 1] / var) if var else None
    corr = float(np.corrcoef(s, m)[0, 1]) if (s.std() and m.std()) else None
    return {"beta": beta, "correlation": corr, "n": int(n)}


def momentum_12_1(closes: list[float]) -> dict:
    a = [c for c in closes if c is not None]
    if len(a) < _TRADING_DAYS + 1:
        return {"value": None, "n": len(a), "reason": "need ~1y of history"}
    return {"value": float(a[-21] / a[-_TRADING_DAYS] - 1.0), "n": len(a),
            "detail": "return from ~12 months ago to ~1 month ago"}


def rsi(closes: list[float], period: int = 14) -> dict:
    a = np.asarray([c for c in closes if c is not None], dtype=float)
    if a.size < period + 1:
        return {"value": None, "n": int(a.size)}
    diff = np.diff(a)
    gain = np.where(diff > 0, diff, 0.0)
    loss = np.where(diff < 0, -diff, 0.0)
    avg_gain = gain[-period:].mean()
    avg_loss = loss[-period:].mean()
    if avg_loss == 0:
        return {"value": 100.0, "n": int(a.size), "period": period}
    rs = avg_gain / avg_loss
    return {"value": float(100 - 100 / (1 + rs)), "n": int(a.size), "period": period}


def moving_averages(closes: list[float]) -> dict:
    a = np.asarray([c for c in closes if c is not None], dtype=float)
    cur = float(a[-1]) if a.size else None
    ma50 = float(a[-50:].mean()) if a.size >= 50 else None
    ma200 = float(a[-200:].mean()) if a.size >= 200 else None
    return {
        "price": cur, "ma50": ma50, "ma200": ma200,
        "price_vs_ma50": (cur / ma50 - 1.0) if (cur and ma50) else None,
        "price_vs_ma200": (cur / ma200 - 1.0) if (cur and ma200) else None,
        "golden_cross": (ma50 > ma200) if (ma50 and ma200) else None,
    }


def all_metrics(stock_closes: list[float], index_closes: list[float] | None, rf: float = 0.0) -> dict:
    out = {
        "annualized_volatility": annualized_vol(stock_closes),
        "sharpe": sharpe(stock_closes, rf),
        "sortino": sortino(stock_closes, rf),
        "max_drawdown": max_drawdown(stock_closes),
        "momentum_12_1": momentum_12_1(stock_closes),
        "rsi_14": rsi(stock_closes),
        "moving_averages": moving_averages(stock_closes),
    }
    if index_closes:
        out["beta_vs_index"] = beta_corr(stock_closes, index_closes)
    return out
