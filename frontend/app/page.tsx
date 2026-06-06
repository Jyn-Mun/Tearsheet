"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export default function Landing() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    const saved = (localStorage.getItem("theme") as "dark" | "light") || "dark";
    setTheme(saved);
    document.documentElement.setAttribute("data-theme", saved);
  }, []);
  function applyTheme(t: "dark" | "light") {
    setTheme(t);
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("theme", t);
  }

  return (
    <div className="lp">
      <nav className="lp-nav">
        <div className="brand">Tearsheet<span className="dot">.</span></div>
        <div className="links">
          <a href="#features">Features</a>
          <a href="#how">How it works</a>
          <a href="#faq">FAQ</a>
          <div className="theme-mini" role="group" aria-label="theme">
            <button className={theme === "dark" ? "on" : ""} onClick={() => applyTheme("dark")}>Dark</button>
            <button className={theme === "light" ? "on" : ""} onClick={() => applyTheme("light")}>Cream</button>
          </div>
          <Link className="btn btn-primary btn-sm cta" href="/terminal">Launch terminal →</Link>
        </div>
      </nav>

      {/* HERO */}
      <header className="hero">
        <div>
          <span className="eyebrow"><span className="sparkle">✦</span> Research tool · not financial advice</span>
          <h1>
            Equity research that <span className="gold">reasons</span>, not just reports.
          </h1>
          <p className="lede">
            Enter a ticker and get a sourced, structured brief — fundamentals, a transparent DCF,
            peers, and a falsifiable bull/bear thesis. Every number traces to its source. It even
            scores its own accuracy.
          </p>
          <div className="cta-row">
            <Link className="btn btn-primary" href="/terminal">Launch the terminal →</Link>
            <a className="btn btn-ghost" href="#how">See how it works</a>
          </div>
        </div>
        <PreviewCard />
      </header>

      {/* VALUE LINE */}
      <section className="lp-section" style={{ textAlign: "center", paddingTop: 20 }}>
        <h2 style={{ margin: "0 auto", maxWidth: 760, fontSize: "clamp(22px,3vw,30px)", fontWeight: 700 }}>
          Separate the company from the stock. Separate <span className="accent">price</span> from{" "}
          <span className="accent">value</span>.
        </h2>
        <p className="sub" style={{ margin: "12px auto 0" }}>
          A great business can be a poor investment. Tearsheet surfaces what the price already
          implies — and where the signals agree or conflict.
        </p>
      </section>

      {/* FEATURES */}
      <section id="features" className="lp-section">
        <div className="kicker">What it does</div>
        <h2>Built like a precision instrument.</h2>
        <div className="feat-grid">
          <Feature icon="◆" title="Grounded in data"
            text="Numbers only from retrieved sources — never invented. Every claim ships a real source link and a retrieval timestamp." />
          <Feature featured icon="∿" title="Transparent DCF + reverse-DCF"
            text="Every assumption is visible: explicit WACC, growth fade, terminal value, a sensitivity grid — and what growth today's price implies." />
          <Feature icon="◷" title="Reasons, not reports"
            text="Falsifiable bull/bear points, a pre-mortem, the 'beats ≠ up' pattern around earnings, and a market/sector/stock-specific move breakdown." />
        </div>
      </section>

      {/* HOW IT WORKS / EVAL */}
      <section id="how" className="lp-section">
        <div className="split">
          <div>
            <div className="kicker">The differentiator</div>
            <h2>It scores its own accuracy.</h2>
            <p className="sub">
              Most AI demos have no evaluation. Tearsheet ships a Python harness that grades factual
              accuracy, citation validity, hallucinations, DCF correctness — and a hard{" "}
              <span className="accent">no-advice</span> gate. One command, one summary line.
            </p>
          </div>
          <div className="codeblock">
            $ python eval/run_eval.py<br />
            <br />
            Accuracy: <span className="ok">100%</span> · Citation validity: <span className="ok">100%</span><br />
            Hallucinations: 0/2 · DCF checks: 2/2<br />
            No-advice gate: <span className="ok">PASS</span> · Falsifiers: 4/4<br />
            Attribution/conflict: 2/2
          </div>
        </div>
      </section>

      {/* CTA BAND */}
      <section className="cta-band">
        <div>
          <h2>Look up a company.</h2>
          <p>Free data, live or offline. No account, no API key required.</p>
        </div>
        <Link className="btn btn-primary" href="/terminal">Open the terminal →</Link>
      </section>

      {/* FAQ */}
      <section id="faq" className="lp-section">
        <div className="kicker">Questions</div>
        <h2>Good to know.</h2>
        <div className="faq">
          <Faq q="Is this financial advice?"
            a="No. Tearsheet is a research tool. It shows model outputs with stated assumptions — never buy/sell/hold calls or price targets. That restraint is enforced in code and in the eval harness." />
          <Faq q="Where does the data come from?"
            a="Free sources only — SEC EDGAR for fundamentals (real 10-K/20-F filings) and Yahoo Finance for market data, with an offline snapshot mode that always works. Toggle Live/Offline in the terminal." />
          <Faq q="Do I need an API key?"
            a="No. The structural analysis — price, financials, valuation, DCF, the reasoning modules — needs no key. An optional Anthropic key upgrades the written thesis from a grounded template to live Claude reasoning." />
          <Faq q="How current is the data?"
            a="Live mode is real-time-ish (end-of-day / delayed). The free tier is rate-limited, so when it's exhausted the app transparently falls back to a flagged snapshot instead of breaking." />
        </div>
      </section>

      <footer className="lp-footer">
        <div className="brand" style={{ fontSize: 17 }}>Tearsheet<span className="dot">.</span></div>
        <div className="mono">
          Generated by AI from public sources · research tool, not financial advice · {new Date().getUTCFullYear()}
        </div>
      </footer>
    </div>
  );
}

function Feature({ icon, title, text, featured }: { icon: string; title: string; text: string; featured?: boolean }) {
  return (
    <div className={`feat-card ${featured ? "featured" : ""}`}>
      <div className="ficon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}

function Faq({ q, a }: { q: string; a: string }) {
  return (
    <details>
      <summary>{q}</summary>
      <p>{a}</p>
    </details>
  );
}

function PreviewCard() {
  // Static, decorative preview (no API calls) — labelled illustrative.
  const pts = [22, 26, 24, 30, 28, 35, 33, 40, 38, 46, 44, 52];
  const w = 100, h = 60, min = Math.min(...pts), max = Math.max(...pts), span = max - min || 1;
  const path = pts
    .map((v, i) => `${(i / (pts.length - 1)) * w},${h - ((v - min) / span) * h}`)
    .join(" ");
  return (
    <div className="preview" aria-hidden>
      <div className="pv-head">
        <span className="pv-tkr">NVDA · NVIDIA</span>
        <span className="pv-tag">illustrative</span>
      </div>
      <div className="pv-px">$205.10</div>
      <div className="pv-delta">▲ +3.42 (+1.69%)</div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <polyline points={path} fill="none" stroke="#2e9e54" strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="pv-grid">
        <div><div className="k">P/E</div><div className="v">41.5×</div></div>
        <div><div className="k">DCF upside</div><div className="v">−57%</div></div>
        <div><div className="k">Implied g</div><div className="v">61%</div></div>
      </div>
    </div>
  );
}
