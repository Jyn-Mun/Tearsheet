"use client";

import { useEffect, useState } from "react";

export type FeatureItem = { icon: string; title: string; text: string; featured?: boolean };

export const FEATURES: FeatureItem[] = [
  {
    icon: "◆",
    title: "Grounded in data",
    featured: false,
    text: "Numbers come only from retrieved sources, never invented. Every claim ships with a real source link and the time it was retrieved.",
  },
  {
    icon: "∿",
    title: "Transparent DCF and reverse DCF",
    featured: true,
    text: "Every assumption is visible: explicit WACC, growth fade, terminal value, and a sensitivity grid, plus the growth rate today's price already implies.",
  },
  {
    icon: "◷",
    title: "Reasons, not reports",
    featured: false,
    text: "Falsifiable bull and bear points, a pre-mortem, the pattern of beats that did not move the stock around earnings, and a market, sector, and stock-specific breakdown of each move.",
  },
];

export function Feature({ icon, title, text, featured }: FeatureItem) {
  return (
    <div className={`feat-card ${featured ? "featured" : ""}`}>
      <div className="ficon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}

export function FeatureCarousel() {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const n = FEATURES.length;
  const go = (next: number) => setI((next + n) % n);

  // Auto-advance, looping. Pauses on hover/focus and when the user prefers reduced motion.
  useEffect(() => {
    if (paused) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => setI((p) => (p + 1) % n), 4200);
    return () => clearInterval(id);
  }, [paused, n]);

  return (
    <div
      className="carousel"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div className="carousel-viewport">
        <button className="carousel-arrow prev" aria-label="Previous feature" onClick={() => go(i - 1)}>‹</button>
        <div className="carousel-track" style={{ transform: `translateX(-${i * 100}%)` }}>
          {FEATURES.map((f, idx) => (
            <div className={`carousel-slide ${idx === i ? "active" : ""}`} key={idx} aria-hidden={idx !== i}>
              <Feature {...f} />
            </div>
          ))}
        </div>
        <button className="carousel-arrow next" aria-label="Next feature" onClick={() => go(i + 1)}>›</button>
      </div>
      <div className="carousel-dots" role="tablist" aria-label="features">
        {FEATURES.map((f, idx) => (
          <button
            key={idx}
            className={`carousel-dot ${idx === i ? "on" : ""}`}
            role="tab"
            aria-selected={idx === i}
            aria-label={f.title}
            onClick={() => setI(idx)}
          />
        ))}
      </div>
    </div>
  );
}
