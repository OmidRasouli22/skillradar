// Types and calls for the local API (src/skillradar/api).

export type Choice = { id: string; label: string; postings: number };

export type Overview = {
  as_of: string | null;
  tech_postings: number;
  model: string;
  prompt_version: string;
  roles: Choice[];
  regions: Choice[];
};

export type Skill = {
  name: string;
  postings: number;
  required_postings: number;
  share: number;
  required_share: number;
};

export type Part = { value: string; postings: number; share: number };

export type Dashboard = {
  region: string;
  as_of: string | null;
  model: string;
  prompt_version: string;
  total_postings: number;
  roles: Choice[];
  skills: Record<string, Skill[]>;
  heatmap: { skills: string[]; rows: (Choice & { shares: number[] })[] };
  emerging_skills: { name: string; postings: number; share: number }[];
  // role -> attribute (german, english, remote, seniority) -> parts
  attributes: Record<string, Record<string, Part[]>>;
  emerging: Record<string, { postings: number; share: number }>;
  // role -> postings per German state
  states: Record<string, Choice[]>;
};

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal, headers: { Accept: "application/json" } });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function getOverview(signal?: AbortSignal): Promise<Overview> {
  return get<Overview>("/api/overview", signal);
}

export function getDashboard(region: string, signal?: AbortSignal): Promise<Dashboard> {
  return get<Dashboard>(`/api/dashboard?${new URLSearchParams({ region })}`, signal);
}
