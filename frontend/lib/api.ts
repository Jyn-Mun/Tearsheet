// Typed client to the FastAPI backend. One place that knows the base URL and endpoint shapes.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type Mode = "live" | "offline";

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  integrations: { anthropic: boolean; fred: boolean };
  data_source: string;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`${path} → ${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

const t = (s: string) => encodeURIComponent(s.trim().toUpperCase());

// Endpoint responses are loosely typed (any) — shapes are documented in the backend services.
// Every call carries the Live/Offline mode so the backend serves real API data or snapshots.
export const api = {
  health: () => getJSON<HealthResponse>("/health"),
  samples: () => getJSON<{ tickers: string[] }>("/samples"),
  company: (tk: string, mode: Mode) => getJSON<any>(`/company/${t(tk)}?mode=${mode}`),
  financials: (tk: string, mode: Mode) => getJSON<any>(`/financials/${t(tk)}?mode=${mode}`),
  valuation: (tk: string, mode: Mode) => getJSON<any>(`/valuation/${t(tk)}?mode=${mode}`),
  dcf: (tk: string, mode: Mode) => getJSON<any>(`/dcf/${t(tk)}?mode=${mode}`),
  news: (tk: string, mode: Mode) => getJSON<any>(`/news/${t(tk)}?mode=${mode}`),
  analysis: (tk: string, mode: Mode) => getJSON<any>(`/analysis/${t(tk)}?mode=${mode}`),
  events: (tk: string, mode: Mode) => getJSON<any>(`/events/${t(tk)}?mode=${mode}`),
  interpret: (tk: string, mode: Mode) => getJSON<any>(`/interpret/${t(tk)}?mode=${mode}`),
  explainMove: (tk: string, mode: Mode, date?: string) =>
    getJSON<any>(`/explain-move/${t(tk)}?mode=${mode}${date ? `&date=${date}` : ""}`),
};
