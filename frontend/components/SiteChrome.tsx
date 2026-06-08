"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

// Shared marketing-site chrome (nav + footer) used by the landing, Features, and How it works
// pages so they stay visually identical and the theme toggle behaves the same everywhere.

type Theme = "dark" | "light";

export function SiteNav({ active }: { active?: "features" | "how" | "faq" }) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const saved = (localStorage.getItem("theme") as Theme) || "dark";
    setTheme(saved);
    document.documentElement.setAttribute("data-theme", saved);
  }, []);
  function applyTheme(t: Theme) {
    setTheme(t);
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("theme", t);
  }
  const close = () => setOpen(false);
  return (
    <nav className="lp-nav">
      <div className="nav-top">
        <Link href="/" className="brand" style={{ textDecoration: "none", color: "inherit" }} onClick={close}>
          Tearsheet<span className="dot">.</span>
        </Link>
        <button
          className="nav-burger" aria-label="Menu" aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          {open ? "✕" : "☰"}
        </button>
      </div>

      <div className={`nav-links ${open ? "open" : ""}`}>
        <Link href="/features" className={active === "features" ? "on" : ""} onClick={close}>Features</Link>
        <Link href="/how-it-works" className={active === "how" ? "on" : ""} onClick={close}>How it works</Link>
        <Link href="/#faq" onClick={close}>FAQ</Link>
      </div>

      <div className="nav-actions">
        <div className="theme-mini" role="group" aria-label="theme">
          <button className={theme === "dark" ? "on" : ""} onClick={() => applyTheme("dark")} aria-label="Dark theme">
            <span className="lbl-text">Dark</span><span className="lbl-icon" aria-hidden>☾</span>
          </button>
          <button className={theme === "light" ? "on" : ""} onClick={() => applyTheme("light")} aria-label="Cream theme">
            <span className="lbl-text">Cream</span><span className="lbl-icon" aria-hidden>☀</span>
          </button>
        </div>
        <Link className="btn btn-primary btn-sm cta" href="/terminal" onClick={close}>Launch terminal →</Link>
      </div>
    </nav>
  );
}

export function SiteFooter() {
  return (
    <footer className="lp-footer">
      <div className="brand" style={{ fontSize: 17 }}>Tearsheet<span className="dot">.</span></div>
      <div className="mono">
        Generated from public sources · research tool, not financial advice · {new Date().getUTCFullYear()}
      </div>
    </footer>
  );
}
