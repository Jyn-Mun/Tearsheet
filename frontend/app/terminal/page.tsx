"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Mode } from "@/lib/api";
import {
  Overview, Financials, Valuation, Dcf, Analysis, Analytics, Events, Interpretation, MoveExplain, News,
} from "@/components/panels";

const DEFAULT = "NVDA";
// Steer users toward covered, liquid US names (the backend is US-listed equities only).
const SUGGESTED = ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META"];
// US ticker format: 1–5 letters, optional class suffix (e.g. BRK.B). Rejects ISINs, numbers,
// foreign formats (e.g. "7203.T", "VOD.L") before firing a doomed lookup.
const US_TICKER = /^[A-Z]{1,5}(\.[A-Z])?$/;

export default function Home() {
  const [ticker, setTicker] = useState(DEFAULT);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>("live");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [recent, setRecent] = useState<string[]>([DEFAULT]);
  const [hint, setHint] = useState("");
  // Retry a few times with backoff — covers Render free-tier cold starts (server waking ~30–60s).
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    retry: 8,
    retryDelay: (n) => Math.min(4000, 1000 * (n + 1)),
  });
  const [waitSecs, setWaitSecs] = useState(0);

  // Sync theme with <html data-theme> + localStorage.
  useEffect(() => {
    const saved = (localStorage.getItem("theme") as "dark" | "light") || "dark";
    setTheme(saved);
  }, []);
  function applyTheme(t: "dark" | "light") {
    setTheme(t);
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("theme", t);
  }

  // Same query key as the Overview panel → TanStack dedupes; this just reads it for the badge.
  const company = useQuery({
    queryKey: ["company", ticker, mode],
    queryFn: () => api.company(ticker, mode),
  });
  const samples = useQuery({ queryKey: ["samples"], queryFn: api.samples });

  useEffect(() => {
    setRecent((r) => [ticker, ...r.filter((x) => x !== ticker)].slice(0, 8));
  }, [ticker]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const v = input.trim().toUpperCase();
    if (!v) return;
    if (!US_TICKER.test(v)) {
      setHint("Enter a US ticker symbol like NVDA, MSFT, or AAPL.");
      return;
    }
    setHint("");
    setTicker(v);
    setInput("");
  }

  // Load a covered name directly (suggested chip / steering). Stays in the current mode.
  function pick(tk: string) {
    setHint("");
    setInput("");
    setTicker(tk);
  }

  const ok = health.data?.status === "ok";
  // Count seconds while the backend is still waking, so the cold-start banner looks intentional.
  useEffect(() => {
    if (ok) { setWaitSecs(0); return; }
    const start = Date.now();
    const id = setInterval(() => setWaitSecs(Math.round((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(id);
  }, [ok]);
  const waking = !ok && waitSecs >= 2;

  const dot = health.isLoading ? "var(--text-muted)" : ok ? "var(--up)" : "var(--down)";
  const badge = dataBadge(company.data);

  return (
    <div className="app">
      <aside className="rail">
        <a href="/" className="brand" style={{ textDecoration: "none", color: "inherit", display: "inline-block" }}>
          Tearsheet<span className="dot">.</span>
        </a>
        <div className="subtle" style={{ fontSize: 12, marginTop: 2 }}>equity research terminal</div>

        <div className="rail-label">Theme</div>
        <div className="seg" role="group" aria-label="theme">
          <button className={theme === "dark" ? "on" : ""} onClick={() => applyTheme("dark")}>Dark</button>
          <button className={theme === "light" ? "on" : ""} onClick={() => applyTheme("light")}>Cream</button>
        </div>

        <div className="rail-label">Data source</div>
        <div className="seg" role="group" aria-label="data source">
          <button className={mode === "live" ? "on" : ""} onClick={() => setMode("live")}>Live</button>
          <button className={mode === "offline" ? "on" : ""} onClick={() => setMode("offline")}>Offline</button>
        </div>
        <div className={`databadge ${badge.cls}`}>{badge.label}</div>
        <div className="subtle" style={{ fontSize: 11, marginTop: 4, lineHeight: 1.4 }}>{badge.note}</div>

        <div className="rail-label">Lookup</div>
        <form onSubmit={submit}>
          <input
            className="search" placeholder="TICKER" value={input}
            onChange={(e) => { setInput(e.target.value); if (hint) setHint(""); }}
            aria-label="ticker search" spellCheck={false}
          />
        </form>
        <div className="subtle" style={{ fontSize: 11, marginTop: 6, lineHeight: 1.4 }}>
          {hint || "US-listed stocks only — enter a ticker symbol like NVDA, MSFT, AAPL."}
        </div>
        <div className="chips" style={{ marginTop: 8 }}>
          {SUGGESTED.map((s) => (
            <button
              key={s}
              className={`chip ${s === ticker ? "on" : ""}`}
              onClick={() => pick(s)}
              title={`Look up ${s}`}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="rail-label">Recent</div>
        <ul className="recent">
          {recent.map((r) => (
            <li key={r} className={r === ticker ? "active" : ""} onClick={() => setTicker(r)}>{r}</li>
          ))}
        </ul>

        <div className="rail-label">
          Offline companies {mode === "offline" ? "(active)" : ""}
        </div>
        <div className="chips">
          {(samples.data?.tickers ?? []).map((s) => (
            <button
              key={s}
              className={`chip ${s === ticker ? "on" : ""}`}
              onClick={() => { setTicker(s); setMode("offline"); }}
              title={`Load ${s} from offline snapshot`}
            >
              {s}
            </button>
          ))}
          {!samples.data?.tickers?.length && <span className="subtle" style={{ fontSize: 12 }}>none loaded</span>}
        </div>
        <div className="subtle" style={{ fontSize: 11, marginTop: 6, lineHeight: 1.4 }}>
          Preloaded snapshots — always available, no API limits.
        </div>

        <div className="status-line">
          <span className="dot-ind" style={{ background: dot }} />
          <span>{health.isLoading ? "connecting…" : ok ? "backend ok" : "backend down"}</span>
        </div>
        {ok && (
          <div className="subtle mono" style={{ fontSize: 11, marginTop: 6 }}>
            default: {health.data?.data_source} · anthropic: {health.data?.integrations.anthropic ? "on" : "off"}
          </div>
        )}
      </aside>

      <main className="main">
        {waking && (
          <div className="banner" style={{ marginBottom: 16 }}>
            ⏳ Waking the server… The backend is on a free tier that sleeps when idle, so the first
            load takes ~30–60s ({waitSecs}s). This only happens once — thanks for your patience.
          </div>
        )}
        <Overview ticker={ticker} index={0} mode={mode} />
        <Analytics ticker={ticker} index={1} mode={mode} />
        <Interpretation ticker={ticker} index={2} mode={mode} />
        <MoveExplain ticker={ticker} index={3} mode={mode} />
        <Analysis ticker={ticker} index={4} mode={mode} />
        <Dcf ticker={ticker} index={5} mode={mode} />
        <Valuation ticker={ticker} index={6} mode={mode} />
        <Events ticker={ticker} index={7} mode={mode} />
        <Financials ticker={ticker} index={8} mode={mode} />
        <News ticker={ticker} index={9} mode={mode} />

        <div className="footer">
          Generated by AI from public sources · research tool, not financial advice · no buy/sell/hold, no price target<br />
          {mode === "live" ? "Live data: SEC EDGAR (fundamentals) + Yahoo Finance (market)." : "Offline snapshot data."} · provenance traced per figure · {new Date().getUTCFullYear()} · Tearsheet
        </div>
      </main>
    </div>
  );
}

function dataBadge(d: any): { label: string; cls: string; note: string } {
  if (!d) return { label: "…", cls: "neutral", note: "" };
  const src: string = d.source ?? "";
  const warns: string[] = d.warnings ?? [];
  if (src.includes("snapshot")) {
    return { label: "● OFFLINE SNAPSHOT", cls: "snapshot",
      note: "Recorded real data (point-in-time) — always available, not live." };
  }
  if (src.includes("fixture")) {
    return { label: "● OFFLINE SAMPLE", cls: "snapshot",
      note: "Synthetic sample data — always available, not live." };
  }
  if (warns.some((w) => w.toLowerCase().includes("snapshot"))) {
    return { label: "● LIVE → SNAPSHOT", cls: "snapshot",
      note: "Live unavailable (rate-limit/coverage) — showing a snapshot." };
  }
  if (src.toLowerCase().includes("edgar")) {
    return { label: "● LIVE · SEC EDGAR", cls: "live",
      note: "Real SEC filings (10-K). Fundamentals only — no price/market data." };
  }
  if (src && src.trim()) {
    return { label: "● LIVE", cls: "live", note: "Real-time-ish data from the live API." };
  }
  return { label: "● —", cls: "neutral", note: "" };
}
