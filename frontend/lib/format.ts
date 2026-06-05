// Number formatting helpers. All financial numerics render via these so digits stay tabular.

export const NA = "n/a";

export function num(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return NA;
  return x.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function money(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return NA;
  return "$" + num(x, digits);
}

export function pct(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return NA;
  return (x >= 0 ? "+" : "") + num(x * 100, digits) + "%";
}

export function pctPlain(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return NA;
  return num(x * 100, digits) + "%";
}

export function mult(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return NA;
  return num(x, digits) + "x";
}

// Compact large currency: $1.23T / $45.6B / $789M
export function bigMoney(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return NA;
  const abs = Math.abs(x);
  const sign = x < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${num(abs / 1e12, 2)}T`;
  if (abs >= 1e9) return `${sign}$${num(abs / 1e9, 2)}B`;
  if (abs >= 1e6) return `${sign}$${num(abs / 1e6, 1)}M`;
  if (abs >= 1e3) return `${sign}$${num(abs / 1e3, 1)}K`;
  return `${sign}$${num(abs, 0)}`;
}

export function deltaClass(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "";
  return x > 0 ? "up" : x < 0 ? "down" : "";
}

export function shortDate(s: string | null | undefined): string {
  if (!s) return NA;
  return s.slice(0, 10);
}
