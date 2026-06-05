// Typed client to the FastAPI backend. One place that knows the base URL and endpoint shapes.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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
export const api = {
  health: () => getJSON<HealthResponse>("/health"),
  company: (tk: string) => getJSON<any>(`/company/${t(tk)}`),
  financials: (tk: string) => getJSON<any>(`/financials/${t(tk)}`),
  valuation: (tk: string) => getJSON<any>(`/valuation/${t(tk)}`),
  dcf: (tk: string) => getJSON<any>(`/dcf/${t(tk)}`),
  news: (tk: string) => getJSON<any>(`/news/${t(tk)}`),
  analysis: (tk: string) => getJSON<any>(`/analysis/${t(tk)}`),
  events: (tk: string) => getJSON<any>(`/events/${t(tk)}`),
  interpret: (tk: string) => getJSON<any>(`/interpret/${t(tk)}`),
  explainMove: (tk: string, date?: string) =>
    getJSON<any>(`/explain-move/${t(tk)}${date ? `?date=${date}` : ""}`),
};
