import Link from "next/link";
import { SiteNav, SiteFooter } from "@/components/SiteChrome";
import { FeatureCarousel } from "@/components/Features";

export default function Landing() {
  return (
    <div className="lp">
      <SiteNav />

      {/* HERO */}
      <header className="hero">
        <div>
          <span className="eyebrow"><span className="sparkle">✦</span> Research tool · not financial advice</span>
          <h1>
            Equity research that <span className="gold">reasons</span>, not just reports.
          </h1>
          <p className="lede">
            Enter a ticker and get a sourced, structured brief: fundamentals, a transparent DCF,
            peers, and a falsifiable bull and bear thesis. Every number traces back to its source,
            and the model scores its own accuracy.
          </p>
          <div className="cta-row">
            <Link className="btn btn-primary" href="/terminal">Launch the terminal →</Link>
            <Link className="btn btn-ghost" href="/how-it-works">See how it works</Link>
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
          implies, and shows where the signals agree or conflict.
        </p>
      </section>

      {/* FEATURES */}
      <section id="features" className="lp-section">
        <div className="kicker">What it does</div>
        <h2>Built like a precision instrument.</h2>
        <FeatureCarousel />
        <div style={{ marginTop: 22 }}>
          <Link className="btn btn-ghost" href="/features">See all features →</Link>
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
              accuracy, citation validity, hallucinations, and DCF correctness, with a hard{" "}
              <span className="accent">no-advice</span> gate. One command, one summary line.
            </p>
            <div style={{ marginTop: 18 }}>
              <Link className="btn btn-ghost" href="/how-it-works">Read how it works →</Link>
            </div>
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
            a="No. Tearsheet is a research tool. It shows model outputs with stated assumptions, never buy, sell, or hold calls or price targets. That restraint is enforced in code and in the eval harness." />
          <Faq q="Where does the data come from?"
            a="Free, public sources only: SEC EDGAR for fundamentals (real 10-K and 20-F filings) and Alpaca for market data, with an offline snapshot mode that always works. Toggle Live or Offline in the terminal." />
          <Faq q="Do I need an API key?"
            a="No. The structural analysis (price, financials, valuation, DCF, and the reasoning modules) needs no key. An optional Anthropic key upgrades the written thesis from a grounded template to live Claude reasoning." />
          <Faq q="How current is the data?"
            a="Live mode shows delayed, end-of-day prices. The free tier is rate limited, so when it is exhausted the app falls back to a clearly labelled snapshot instead of breaking." />
        </div>
      </section>

      <SiteFooter />
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
  // Static, decorative preview (no API calls), labelled illustrative.
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
        <div><div className="k">P/E</div><div className="v">41.5x</div></div>
        <div><div className="k">DCF upside</div><div className="v">-57%</div></div>
        <div><div className="k">Implied g</div><div className="v">61%</div></div>
      </div>
    </div>
  );
}
