"use client";

// Minimal dependency-free SVG sparkline — no heavy chart kit (per DESIGN.md).
export function Sparkline({ data, color = "var(--accent)" }: { data: number[]; color?: string }) {
  if (!data || data.length < 2) return <div className="subtle">no price history</div>;
  const w = 100, h = 28, pad = 2;
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - 2 * pad);
    const y = pad + (1 - (v - min) / span) * (h - 2 * pad);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const rising = data[data.length - 1] >= data[0];
  const stroke = color === "auto" ? (rising ? "var(--up)" : "var(--down)") : color;
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
      <polyline points={pts.join(" ")} fill="none" stroke={stroke} strokeWidth="1" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
