"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Mode } from "@/lib/api";
import {
  Overview, Financials, Valuation, Dcf, Analysis, Analytics, Events, Interpretation, MoveExplain, News,
} from "@/components/panels";

const DEFAULT = "NVDA";

export default function Home() {
  const [ticker, setTicker] = useState(DEFAULT);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>("live");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [recent, setRecent] = useState<string[]>([DEFAULT]);
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });

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
    if (v) { setTicker(v); setInput(""); }
  }

  const ok = health.data?.status === "ok";
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
            onChange={(e) => setInput(e.target.value)} aria-label="ticker search" spellCheck={false}
          />
        </form>

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
