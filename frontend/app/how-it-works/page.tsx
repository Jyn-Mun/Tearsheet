import Link from "next/link";
import { SiteNav, SiteFooter } from "@/components/SiteChrome";

export const metadata = {
  title: "How it works · Tearsheet",
  description: "From SEC filing to a checked thesis, every step of the Tearsheet pipeline.",
};

const STEPS = [
  {
    n: "01",
    title: "Retrieve",
    text: "Fundamentals come from SEC EDGAR (real 10-K and 20-F filings); price, history, and quotes come from Alpaca. A short-lived cache keeps requests fast and within rate limits.",
  },
  {
    n: "02",
    title: "Compute",
    text: "Margins, growth, quality scores, and valuation multiples are calculated in code from the filings and the live price. The DCF and reverse DCF run with assumptions you can see and change.",
  },
  {
    n: "03",
    title: "Reason",
    text: "A thesis layer assembles falsifiable bull and bear points, a pre-mortem, an interpretation of what the price implies, and a market, sector, and stock-specific breakdown of recent moves.",
  },
  {
    n: "04",
    title: "Check",
    text: "An evaluation harness grades factual accuracy, citation validity, hallucinations, and DCF correctness, and enforces a hard no-advice gate before anything reaches you.",
  },
];

export default function HowItWorksPage() {
  return (
    <div className="lp">
      <SiteNav active="how" />

      <section className="lp-section" style={{ paddingTop: 36 }}>
        <div className="kicker">How it works</div>
        <h2>From filing to thesis, every step is visible.</h2>
        <p className="sub">
          Tearsheet is built so you can trust the output by tracing it. Data is retrieved from
          primary sources, every number is computed in the open, and the result is checked before
          it is shown.
        </p>
        <div className="feat-grid" style={{ marginTop: 30 }}>
          {STEPS.map((s) => (
            <div className="feat-card" key={s.n}>
              <div className="ficon" style={{ fontFamily: "var(--mono)", fontWeight: 700 }}>{s.n}</div>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="lp-section" style={{ paddingTop: 0 }}>
        <div className="split">
          <div>
            <div className="kicker">The differentiator</div>
            <h2>It scores its own accuracy.</h2>
            <p className="sub">
              Most AI demos have no evaluation. Tearsheet ships a Python harness that grades the
              output on real checks and prints one summary line, so quality is measured, not claimed.
            </p>
            <div style={{ marginTop: 18 }}>
              <Link className="btn btn-primary" href="/terminal">Try it now →</Link>
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

      <section className="lp-section" style={{ paddingTop: 0 }}>
        <div className="kicker">Coverage and limits</div>
        <h2>What it covers, plainly.</h2>
        <p className="sub">
          Tearsheet covers US-listed equities and works best on liquid names. Live prices are
          delayed end-of-day data on a free tier, so when a limit is reached the app falls back to a
          clearly labelled snapshot rather than breaking. It is a research tool, not financial
          advice, and it never issues buy, sell, or hold calls or price targets.
        </p>
      </section>

      <SiteFooter />
    </div>
  );
}
