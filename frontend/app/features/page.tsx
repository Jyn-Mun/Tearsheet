import Link from "next/link";
import { SiteNav, SiteFooter } from "@/components/SiteChrome";
import { Feature, type FeatureItem } from "@/components/Features";

export const metadata = {
  title: "Features · Tearsheet",
  description: "What the Tearsheet brief includes and why each part is there.",
};

/* ---- inline SVG illustrations (theme-aware via CSS vars) ---- */

function DataGraphic() {
  return (
    <svg viewBox="0 0 240 150" role="img" aria-label="Sourced data illustration">
      <rect x="34" y="20" width="172" height="110" rx="10"
        style={{ fill: "var(--panel-2)", stroke: "var(--border)" }} strokeWidth="1.5" />
      <rect x="50" y="36" width="86" height="9" rx="4" style={{ fill: "var(--accent)" }} />
      <rect x="50" y="58" width="140" height="6" rx="3" style={{ fill: "var(--border)" }} />
      <rect x="50" y="72" width="120" height="6" rx="3" style={{ fill: "var(--border)" }} />
      <rect x="50" y="86" width="132" height="6" rx="3" style={{ fill: "var(--border)" }} />
      <rect x="50" y="104" width="74" height="16" rx="8"
        style={{ fill: "var(--accent-soft)", stroke: "var(--accent)" }} strokeWidth="1" />
      <text x="60" y="116" style={{ fill: "var(--accent)", fontFamily: "var(--mono)", fontSize: "9px" }}>↗ source</text>
      <circle cx="178" cy="112" r="11" style={{ fill: "none", stroke: "var(--up)" }} strokeWidth="2" />
      <path d="M173 112 l4 4 l7 -8" style={{ fill: "none", stroke: "var(--up)" }} strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DcfGraphic() {
  const cols = 5, rows = 4;
  const cells = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      // diagonal gradient: upper-left favourable (up), lower-right unfavourable (down)
      const score = (cols - 1 - c) + (rows - 1 - r);
      const fill = score >= 5 ? "var(--up)" : score >= 3 ? "var(--accent)" : "var(--down)";
      const op = 0.35 + (score / ((cols - 1) + (rows - 1))) * 0.5;
      cells.push(
        <rect key={`${r}-${c}`} x={42 + c * 34} y={26 + r * 26} width="28" height="20" rx="4"
          style={{ fill, opacity: op }} />,
      );
    }
  }
  return (
    <svg viewBox="0 0 240 150" role="img" aria-label="DCF sensitivity grid">
      {cells}
      <text x="42" y="146" style={{ fill: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: "8px" }}>terminal g →</text>
      <text x="14" y="120" transform="rotate(-90 14 120)"
        style={{ fill: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: "8px" }}>WACC →</text>
    </svg>
  );
}

function ReasonGraphic() {
  return (
    <svg viewBox="0 0 240 150" role="img" aria-label="Bull and bear split">
      <line x1="120" y1="22" x2="120" y2="128" style={{ stroke: "var(--border)" }} strokeWidth="1.5" strokeDasharray="4 5" />
      {/* bull side */}
      {[0, 1, 2].map((i) => (
        <rect key={`u${i}`} x={40 + i * 22} y={96 - i * 22} width="14" height={26 + i * 22} rx="3"
          style={{ fill: "var(--up)", opacity: 0.85 }} />
      ))}
      <path d="M44 44 l10 -12 l10 12" style={{ fill: "none", stroke: "var(--up)" }} strokeWidth="2.5"
        strokeLinecap="round" strokeLinejoin="round" />
      <text x="40" y="142" style={{ fill: "var(--up)", fontFamily: "var(--mono)", fontSize: "10px" }}>BULL</text>
      {/* bear side */}
      {[0, 1, 2].map((i) => (
        <rect key={`d${i}`} x={150 + i * 22} y={30} width="14" height={28 + i * 22} rx="3"
          style={{ fill: "var(--down)", opacity: 0.85 }} />
      ))}
      <path d="M186 100 l10 12 l10 -12" style={{ fill: "none", stroke: "var(--down)" }} strokeWidth="2.5"
        strokeLinecap="round" strokeLinejoin="round" />
      <text x="150" y="142" style={{ fill: "var(--down)", fontFamily: "var(--mono)", fontSize: "10px" }}>BEAR</text>
    </svg>
  );
}

function FeatureRow({ kicker, title, text, graphic, reverse }:
  { kicker: string; title: string; text: string; graphic: React.ReactNode; reverse?: boolean }) {
  return (
    <div className={`feature-row ${reverse ? "reverse" : ""}`}>
      <div className="feat-text">
        <div className="kicker">{kicker}</div>
        <h3 className="feat-row-title">{title}</h3>
        <p className="sub">{text}</p>
      </div>
      <div className="feat-visual">{graphic}</div>
    </div>
  );
}

const DEPTH: FeatureItem[] = [
  { icon: "▤", title: "Fundamentals and quality scores",
    text: "Income, balance sheet, and cash flow from SEC filings, plus Piotroski F, Altman Z, Beneish M, margins, and multi-year growth trends." },
  { icon: "◇", title: "Valuation and peers",
    text: "P/E, EV/EBITDA, P/S, P/B, FCF yield, and ROIC computed from filings and live price, set against a sector peer group." },
  { icon: "◔", title: "Risk and price behaviour",
    text: "Volatility, Sharpe, Sortino, beta, drawdown, momentum, and moving averages, each reported with its sample size." },
  { icon: "≈", title: "Move attribution",
    text: "Each session's move is split into market, sector, and stock-specific parts, with same-day headlines flagged as correlation, not proven cause." },
  { icon: "◷", title: "Earnings behaviour",
    text: "Beat rate, average surprise, and how the stock actually traded into and out of prior reports, so a beat is never assumed to mean up." },
  { icon: "✓", title: "Honest by default",
    text: "Missing data reads as n/a, never a guess. A hard no-advice gate keeps the output to research, with no buy, sell, or hold calls." },
];

export default function FeaturesPage() {
  return (
    <div className="lp">
      <SiteNav active="features" />

      <section className="lp-section" style={{ paddingTop: 36, paddingBottom: 10 }}>
        <div className="kicker">Features</div>
        <h2>Everything in the brief, and why it is there.</h2>
        <p className="sub">
          Tearsheet turns a single ticker into a sourced research brief. Each capability below answers
          one question about the business, and every figure traces back to a filing or a price feed.
        </p>
      </section>

      <section className="lp-section" style={{ paddingTop: 0 }}>
        <FeatureRow
          kicker="Provenance"
          title="Grounded in data"
          text="Numbers come only from retrieved sources, never invented. Every claim ships with a real source link and the time it was retrieved, so you can check the brief instead of trusting it."
          graphic={<DataGraphic />}
        />
        <FeatureRow
          reverse
          kicker="Valuation"
          title="Transparent DCF and reverse DCF"
          text="Every assumption is visible: explicit WACC, growth fade, terminal value, and a full sensitivity grid. The reverse DCF then shows the growth rate today's price already implies."
          graphic={<DcfGraphic />}
        />
        <FeatureRow
          kicker="Reasoning"
          title="Reasons, not reports"
          text="Falsifiable bull and bear points, a pre-mortem, and a clear read of what the price is counting on. Each point states the condition that would prove it wrong."
          graphic={<ReasonGraphic />}
        />
      </section>

      <section className="lp-section" style={{ paddingTop: 10 }}>
        <div className="kicker">In depth</div>
        <h2>The full toolkit.</h2>
        <div className="feat-grid" style={{ marginTop: 30 }}>
          {DEPTH.map((f) => <Feature key={f.title} {...f} />)}
        </div>
      </section>

      <section className="cta-band">
        <div>
          <h2>See it on a real company.</h2>
          <p>Free data, live or offline. No account, no API key required.</p>
        </div>
        <Link className="btn btn-primary" href="/terminal">Open the terminal →</Link>
      </section>

      <SiteFooter />
    </div>
  );
}
