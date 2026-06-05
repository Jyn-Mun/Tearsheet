"use client";

import { api } from "@/lib/api";
import {
  bigMoney, deltaClass, money, mult, num, pct, pctPlain, shortDate, NA,
} from "@/lib/format";
import { Module, useEndpoint, Loading, ErrBox } from "./Module";
import { Sparkline } from "./Sparkline";

function srcLink(url?: string | null) {
  if (!url) return null;
  return (
    <a className="src" href={url} target="_blank" rel="noreferrer">
      ↗ source
    </a>
  );
}

function sampleBanner(source?: string) {
  if (source && source.includes("fixture")) {
    return <div className="banner">⚠ Recorded SAMPLE data (synthetic) — Yahoo unavailable here. Not live market data.</div>;
  }
  return null;
}

/* ------------------------------------------------- Overview */
export function Overview({ ticker, index }: { ticker: string; index: number }) {
  const q = useEndpoint(["company", ticker], () => api.company(ticker));
  return (
    <Module title="Overview" index={index} right={q.data ? <span className="muted">{q.data.source}</span> : null}>
      {q.isLoading && <Loading />}
      {q.isError && <ErrBox msg={(q.error as Error).message} />}
      {q.data && <OverviewBody d={q.data} />}
    </Module>
  );
}
function OverviewBody({ d }: { d: any }) {
  const p = d.price, km = d.key_metrics, prof = d.profile;
  const empty = !prof.name && p.current === null && (!d.sparkline || d.sparkline.length === 0);
  if (empty) {
    return (
      <div className="errbox" style={{ color: "var(--text-muted)" }}>
        <div style={{ color: "var(--accent)", marginBottom: 6 }}>No data for {d.ticker}.</div>
        {(d.warnings ?? []).map((w: string, i: number) => (
          <div key={i} style={{ fontSize: 12, marginBottom: 4 }}>{w}</div>
        ))}
        <div style={{ fontSize: 12, marginTop: 8 }}>
          This instance is running on offline <strong>sample</strong> data (live market data is
          unavailable here). Try a sample ticker above.
        </div>
      </div>
    );
  }
  return (
    <>
      {sampleBanner(d.source)}
      <div className="headline">
        <span className="company-name">{prof.name ?? d.ticker}</span>
        <span className="muted mono">{d.ticker}</span>
        <span className="px">{money(p.current)}</span>
        <span className={`delta ${deltaClass(p.change_pct)}`}>
          {money(p.change_abs)} ({pct(p.change_pct)})
        </span>
      </div>
      <div className="subtle" style={{ marginTop: 6 }}>
        {[prof.exchange, prof.sector, prof.industry, prof.country].filter(Boolean).join(" · ") || NA}
      </div>
      <div style={{ marginTop: 12 }}>
        <Sparkline data={d.sparkline ?? []} color="auto" />
        <div className="subtle">
          52w {money(p.fifty_two_week_low)} – {money(p.fifty_two_week_high)} · mkt cap {bigMoney(p.market_cap)} · β {num(p.beta)}
        </div>
      </div>
      <div className="kv">
        <Metric k="P/E (TTM)" v={mult(km.pe_ttm)} />
        <Metric k="EV/EBITDA" v={mult(km.ev_ebitda)} />
        <Metric k="P/S" v={mult(km.ps)} />
        <Metric k="P/B" v={mult(km.pb)} />
        <Metric k="Gross margin" v={pctPlain(km.gross_margin)} />
        <Metric k="Oper. margin" v={pctPlain(km.operating_margin)} />
        <Metric k="Net margin" v={pctPlain(km.net_margin)} />
        <Metric k="ROE" v={pctPlain(km.roe)} />
      </div>
      {prof.summary && <p className="subtle" style={{ marginTop: 12, lineHeight: 1.55 }}>{prof.summary}</p>}
    </>
  );
}
function Metric({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

/* ------------------------------------------------- Financials */
export function Financials({ ticker, index }: { ticker: string; index: number }) {
  const q = useEndpoint(["financials", ticker], () => api.financials(ticker));
  return (
    <Module title="Financials" index={index} right={q.data ? <span className="muted">EDGAR-ready · {q.data.currency ?? ""}</span> : null}>
      {q.isLoading && <Loading />}
      {q.isError && <ErrBox msg={(q.error as Error).message} />}
      {q.data && (
        <>
          <StmtTable title="Income statement (B)" table={q.data.income} />
          <div style={{ height: 14 }} />
          <StmtTable title="Cash flow (B)" table={q.data.cashflow} />
        </>
      )}
    </Module>
  );
}
function StmtTable({ title, table }: { title: string; table: any }) {
  if (!table?.periods?.length) return <div className="subtle">{title}: not available</div>;
  return (
    <table className="t">
      <thead>
        <tr>
          <th>{title}</th>
          {table.fiscal_years.map((y: number, i: number) => <th key={i}>FY{y}</th>)}
        </tr>
      </thead>
      <tbody>
        {table.rows.map((row: any, ri: number) => (
          <tr key={ri}>
            <td>{row.label}</td>
            {row.values.map((v: number | null, ci: number) => (
              <td key={ci}>{v === null ? NA : num(v / 1e9, 1)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ------------------------------------------------- Valuation */
export function Valuation({ ticker, index }: { ticker: string; index: number }) {
  const q = useEndpoint(["valuation", ticker], () => api.valuation(ticker));
  return (
    <Module title="Valuation" index={index}>
      {q.isLoading && <Loading />}
      {q.isError && <ErrBox msg={(q.error as Error).message} />}
      {q.data && <ValuationBody d={q.data} />}
    </Module>
  );
}
function ValuationBody({ d }: { d: any }) {
  const m = d.multiples;
  return (
    <>
      <div className="kv">
        <Metric k="P/E (TTM)" v={mult(m.pe_ttm)} />
        <Metric k="Fwd P/E" v={mult(m.forward_pe)} />
        <Metric k="EV/EBITDA" v={mult(m.ev_ebitda)} />
        <Metric k="P/S" v={mult(m.ps)} />
        <Metric k="P/B" v={mult(m.pb)} />
        <Metric k="FCF yield" v={pctPlain(m.fcf_yield, 2)} />
        <Metric k="ROIC" v={pctPlain(m.roic)} />
        <Metric k="Div yield" v={pctPlain(m.dividend_yield, 2)} />
      </div>
      <div className="subtle" style={{ marginTop: 12 }}>
        Peers — <span className="pill">sector approximation</span>
      </div>
      {d.peers.count > 0 ? (
        <table className="t" style={{ marginTop: 8 }}>
          <thead>
            <tr><th>Ticker</th><th>Mkt cap</th><th>P/E</th><th>EV/EBITDA</th><th>P/S</th><th>P/B</th></tr>
          </thead>
          <tbody>
            {d.peers.rows.map((r: any) => (
              <tr key={r.ticker}>
                <td>{r.ticker}</td><td>{bigMoney(r.market_cap)}</td>
                <td>{mult(r.pe_ttm)}</td><td>{mult(r.ev_ebitda)}</td><td>{mult(r.ps)}</td><td>{mult(r.pb)}</td>
              </tr>
            ))}
            <tr>
              <td className="accent">median</td><td>—</td>
              <td>{mult(d.peers.median.pe_ttm)}</td><td>{mult(d.peers.median.ev_ebitda)}</td>
              <td>{mult(d.peers.median.ps)}</td><td>{mult(d.peers.median.pb)}</td>
            </tr>
          </tbody>
        </table>
      ) : (
        <div className="subtle" style={{ marginTop: 8 }}>{d.peers.note}</div>
      )}
    </>
  );
}

/* ------------------------------------------------- DCF */
export function Dcf({ ticker, index }: { ticker: string; index: number }) {
  const q = useEndpoint(["dcf", ticker], () => api.dcf(ticker));
  return (
    <Module title="DCF Model" index={index}>
      {q.isLoading && <Loading />}
      {q.isError && <ErrBox msg={(q.error as Error).message} />}
      {q.data && (q.data.reliable === false && !q.data.outputs
        ? <UnreliableDcf d={q.data} />
        : <DcfBody d={q.data} />)}
    </Module>
  );
}
function UnreliableDcf({ d }: { d: any }) {
  return (
    <>
      <div className="banner">DCF flagged unreliable for this name.</div>
      {(d.flags ?? []).map((f: any, i: number) => (
        <div key={i} className={`pill ${f.level === "error" ? "bad" : "warn"}`} style={{ margin: "0 6px 6px 0" }}>{f.msg}</div>
      ))}
      <div className="subtle">{d.reason}</div>
    </>
  );
}
function DcfBody({ d }: { d: any }) {
  const o = d.outputs, a = d.assumptions;
  return (
    <>
      <div className="headline" style={{ marginBottom: 8 }}>
        <span><span className="k">intrinsic / share</span><div className="px">{money(o.intrinsic_per_share)}</div></span>
        <span><span className="k">vs price {money(d.current_price)}</span>
          <div className={`px ${deltaClass(o.upside_vs_price)}`}>{pct(o.upside_vs_price)}</div></span>
      </div>
      <div className="disc">Model output with stated assumptions — not a recommendation or price target.</div>
      {(d.flags ?? []).map((f: any, i: number) => (
        <span key={i} className={`pill ${f.level === "error" ? "bad" : "warn"}`} style={{ margin: "8px 6px 0 0" }}>{f.msg}</span>
      ))}
      <div className="kv" style={{ marginTop: 12 }}>
        <Metric k="WACC" v={pctPlain(a.wacc, 2)} />
        <Metric k="Cost of equity" v={pctPlain(a.cost_of_equity, 2)} />
        <Metric k="Start growth" v={pctPlain(a.start_growth)} />
        <Metric k="Terminal g" v={pctPlain(a.terminal_growth)} />
        <Metric k="EBIT margin" v={pctPlain(a.ebit_margin)} />
        <Metric k="Beta" v={num(a.beta)} />
        <Metric k="Risk-free" v={pctPlain(a.risk_free, 2)} />
        <Metric k="EV" v={bigMoney(o.enterprise_value)} />
      </div>
      <div className="subtle" style={{ margin: "14px 0 6px" }}>Projection — unlevered FCF (B)</div>
      <table className="t">
        <thead>
          <tr><th>Year</th><th>Rev</th><th>EBIT</th><th>uFCF</th><th>PV(FCF)</th></tr>
        </thead>
        <tbody>
          {d.projection.map((r: any) => (
            <tr key={r.year}>
              <td>Y{r.year}</td><td>{num(r.revenue / 1e9, 1)}</td><td>{num(r.ebit / 1e9, 1)}</td>
              <td>{num(r.ufcf / 1e9, 1)}</td><td>{num(r.pv_fcf / 1e9, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Sensitivity sens={d.sensitivity} price={d.current_price} />
    </>
  );
}
function Sensitivity({ sens, price }: { sens: any; price: number }) {
  if (!sens) return null;
  return (
    <>
      <div className="subtle" style={{ margin: "14px 0 6px" }}>Sensitivity — intrinsic / share · WACC (rows) × terminal g (cols)</div>
      <table className="t">
        <thead>
          <tr><th>WACC ╲ g</th>{sens.growths.map((g: number, i: number) => <th key={i}>{pctPlain(g)}</th>)}</tr>
        </thead>
        <tbody>
          {sens.waccs.map((w: number, ri: number) => (
            <tr key={ri}>
              <td>{pctPlain(w, 1)}</td>
              {sens.intrinsic[ri].map((v: number | null, ci: number) => {
                const cls = v == null ? "" : v >= price ? "up" : "down";
                return <td key={ci} className={cls}>{v == null ? NA : num(v, 0)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

/* ------------------------------------------------- Analysis */
export function Analysis({ ticker, index }: { ticker: string; index: number }) {
  const q = useEndpoint(["analysis", ticker], () => api.analysis(ticker));
  return (
    <Module title="Analysis — AI thesis" index={index}
      right={q.data ? <span className="muted">{q.data.analysis.synthesizer}</span> : null}>
      {q.isLoading && <Loading />}
      {q.isError && <ErrBox msg={(q.error as Error).message} />}
      {q.data && <AnalysisBody d={q.data} />}
    </Module>
  );
}
function AnalysisBody({ d }: { d: any }) {
  const a = d.analysis, inv = d.invariants;
  return (
    <>
      <div style={{ marginBottom: 8 }}>
        <span className={`pill ${inv.no_advice.passed ? "good" : "bad"}`}>no-advice {inv.no_advice.passed ? "PASS" : "FAIL"}</span>{" "}
        <span className={`pill ${inv.falsifiers_present.passed ? "good" : "bad"}`}>falsifiers {inv.falsifiers_present.passed ? "PASS" : "FAIL"}</span>
      </div>
      <p style={{ lineHeight: 1.5 }}>{a.snapshot}</p>
      <div className="col2" style={{ marginTop: 10 }}>
        <div>
          <div className="subtle accent">BULL</div>
          {a.bull_case.map((p: any, i: number) => <Point key={i} p={p} />)}
        </div>
        <div>
          <div className="subtle" style={{ color: "var(--down)" }}>BEAR / RISKS</div>
          {a.bear_case.map((p: any, i: number) => <Point key={i} p={p} />)}
        </div>
      </div>
      <div className="subtle" style={{ marginTop: 12 }}>THESIS</div>
      <ul style={{ margin: "4px 0", paddingLeft: 18, lineHeight: 1.5 }}>
        {a.thesis.map((t: string, i: number) => <li key={i}>{t}</li>)}
      </ul>
      <div className="callout"><strong className="accent">Pre-mortem · </strong>{a.premortem}</div>
      <div className="disc">{d.disclaimer}</div>
    </>
  );
}
function Point({ p }: { p: any }) {
  return (
    <div className="point">
      <div className="claim">{p.claim} {srcLink(p.source_url)}</div>
      <div className="meta falsifier">✕ falsifier: {p.falsifier}</div>
      {p.variant_view && <div className="meta">↔ variant: {p.variant_view}</div>}
    </div>
  );
}

/* ------------------------------------------------- Events */
export function Events({ ticker, index }: { ticker: string; index: number }) {
  const q = useEndpoint(["events", ticker], () => api.events(ticker));
  return (
    <Module title="Behaviour & Events" index={index}>
      {q.isLoading && <Loading />}
      {q.isError && <ErrBox msg={(q.error as Error).message} />}
      {q.data && <EventsBody d={q.data} />}
    </Module>
  );
}
function EventsBody({ d }: { d: any }) {
  const eb = d.earnings_behaviour;
  return (
    <>
      {eb.insufficient_sample && <span className="pill warn">insufficient sample (n={eb.n_reports})</span>}
      <div className="kv" style={{ marginTop: 8 }}>
        <Metric k="Reports (n)" v={String(eb.n_reports)} />
        <Metric k="Beat rate" v={pctPlain(eb.beat_rate)} />
        <Metric k="Avg surprise" v={eb.avg_surprise_pct == null ? NA : num(eb.avg_surprise_pct, 1) + "%"} />
        <Metric k="Post-5d up rate" v={pctPlain(eb.post_window.hit_rate)} />
      </div>
      <table className="t" style={{ marginTop: 10 }}>
        <thead><tr><th>Window</th><th>n</th><th>mean</th><th>median</th><th>std</th><th>up rate</th></tr></thead>
        <tbody>
          {[eb.pre_window, eb.post_window].map((w: any, i: number) => (
            <tr key={i}>
              <td>{w.label}</td><td>{w.n}</td><td className={deltaClass(w.mean)}>{pct(w.mean)}</td>
              <td className={deltaClass(w.median)}>{pct(w.median)}</td><td>{pctPlain(w.std)}</td>
              <td>{pctPlain(w.hit_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="callout">
        <strong className="accent">Beats ≠ up · </strong>
        {d.narration?.beat_vs_move_note ?? `Surprise↔post-move correlation: ${num(eb.surprise_vs_post_correlation.value, 2)} (n=${eb.surprise_vs_post_correlation.n}).`}
      </div>
      <div className="disc">{eb.regime_note}</div>
    </>
  );
}

/* ------------------------------------------------- Interpretation */
export function Interpretation({ ticker, index }: { ticker: string; index: number }) {
  const q = useEndpoint(["interpret", ticker], () => api.interpret(ticker));
  return (
    <Module title="Interpretation — what it means" index={index}
      right={q.data ? <span className={`pill ${q.data.coherence === "conflicting" ? "warn" : "good"}`}>{q.data.coherence}</span> : null}>
      {q.isLoading && <Loading />}
      {q.isError && <ErrBox msg={(q.error as Error).message} />}
      {q.data && <InterpretBody d={q.data} />}
    </Module>
  );
}
function InterpretBody({ d }: { d: any }) {
  const order = ["dcf", "multiples", "narrative", "price_behaviour"];
  return (
    <>
      <table className="coh">
        <tbody>
          {order.map((k) => {
            const s = d.per_signal[k];
            if (!s) return null;
            return (
              <tr key={k}>
                <td style={{ width: 130 }} className="muted">{k.replace("_", " ")}</td>
                <td><span className={`dir ${s.direction}`}>● {s.direction}</span></td>
                <td className="subtle">{s.reading} <span className="muted">({s.basis})</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {d.implied_expectations?.reading && (
        <div className="callout"><strong className="accent">What's priced in · </strong>{d.implied_expectations.reading}</div>
      )}
      <div className="callout"><strong className="accent">Integrated read · </strong>{d.integrated_read}</div>
      <div className="subtle" style={{ marginTop: 8 }}><strong>Key unknown:</strong> {d.key_unknown}</div>
      <div className="disc">{d.disclaimer}</div>
    </>
  );
}

/* ------------------------------------------------- Move explanation */
export function MoveExplain({ ticker, index }: { ticker: string; index: number }) {
  const q = useEndpoint(["move", ticker], () => api.explainMove(ticker));
  return (
    <Module title="Why did it move?" index={index}>
      {q.isLoading && <Loading />}
      {q.isError && <ErrBox msg={(q.error as Error).message} />}
      {q.data && (q.data.available ? <MoveBody d={q.data} /> : <div className="subtle">{q.data.reason}</div>)}
    </Module>
  );
}
function MoveBody({ d }: { d: any }) {
  const a = d.attribution;
  const bars = [
    { label: "market", v: a.market, c: "var(--text-muted)" },
    { label: "sector", v: a.sector, c: "var(--accent)" },
    { label: "stock-specific", v: a.idiosyncratic, c: d.classification === "stock_specific" ? "var(--down)" : "var(--text-muted)" },
  ];
  const maxAbs = Math.max(...bars.map((b) => Math.abs(b.v ?? 0)), 0.001);
  return (
    <>
      <div className="headline" style={{ marginBottom: 10 }}>
        <span><span className="k">{shortDate(d.date)} session</span>
          <div className={`px ${deltaClass(d.total_return)}`}>{pct(d.total_return)}</div></span>
        <span className={`pill ${d.classification === "systematic" ? "warn" : d.classification === "stock_specific" ? "bad" : ""}`}>{d.classification}</span>
        <span className="pill">{d.driver_type.replace("_", " ")}</span>
        <span className="muted mono">β {d.beta_used}</span>
      </div>
      {bars.map((b) => (
        <div key={b.label} style={{ display: "flex", alignItems: "center", gap: 10, margin: "5px 0" }}>
          <span className="muted" style={{ width: 110, fontSize: 12 }}>{b.label}</span>
          <div style={{ flex: 1, background: "var(--panel-2)", height: 14, position: "relative" }}>
            <div style={{
              position: "absolute", left: (b.v ?? 0) < 0 ? `${50 - (Math.abs(b.v ?? 0) / maxAbs) * 50}%` : "50%",
              width: `${(Math.abs(b.v ?? 0) / maxAbs) * 50}%`, height: "100%", background: b.c,
            }} />
            <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--border)" }} />
          </div>
          <span className="num mono" style={{ width: 64 }}>{pct(b.v)}</span>
        </div>
      ))}
      <div className="callout">
        <strong className="accent">Thesis impact · </strong>
        {d.thesis_impact.reasoning}
      </div>
      {d.candidate_causes?.length > 0 && (
        <div className="subtle" style={{ marginTop: 8 }}>
          Candidate cause (correlation, not causation): {d.candidate_causes[0].headline} {srcLink(d.candidate_causes[0].source_url)}
        </div>
      )}
      <div className="subtle" style={{ marginTop: 6 }}><strong>Disambiguator:</strong> {d.key_disambiguator}</div>
      <div className="disc">{d.disclaimer}</div>
    </>
  );
}

/* ------------------------------------------------- News */
export function News({ ticker, index }: { ticker: string; index: number }) {
  const q = useEndpoint(["news", ticker], () => api.news(ticker));
  return (
    <Module title="News" index={index}
      right={q.data?.summary ? <span className={`pill ${q.data.summary.sentiment === "positive" ? "good" : q.data.summary.sentiment === "negative" ? "bad" : ""}`}>{q.data.summary.sentiment}</span> : null}>
      {q.isLoading && <Loading />}
      {q.isError && <ErrBox msg={(q.error as Error).message} />}
      {q.data && <NewsBody d={q.data} />}
    </Module>
  );
}
function NewsBody({ d }: { d: any }) {
  if (!d.headlines?.length) return <div className="subtle">No news available.</div>;
  return (
    <>
      {d.summary?.bullets?.length > 0 && (
        <ul style={{ margin: "0 0 12px", paddingLeft: 18, lineHeight: 1.5 }}>
          {d.summary.bullets.map((b: any, i: number) => (
            <li key={i}>{b.text} {srcLink(b.source_url)}</li>
          ))}
        </ul>
      )}
      <table className="t">
        <tbody>
          {d.headlines.slice(0, 8).map((h: any, i: number) => (
            <tr key={i}>
              <td style={{ fontFamily: "var(--sans)", color: "var(--text)" }}>
                {h.url ? <a className="src" style={{ color: "var(--text)", fontSize: 13 }} href={h.url} target="_blank" rel="noreferrer">{h.title}</a> : h.title}
              </td>
              <td className="muted">{shortDate(h.published)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="disc">{d.disclaimer}</div>
    </>
  );
}
