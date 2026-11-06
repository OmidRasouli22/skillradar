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

export type SkillList = {
  role: string;
  region: string;
  total_postings: number;
  skills: Skill[];
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

export function getSkills(
  role: string,
  region: string,
  limit: number,
  signal?: AbortSignal,
): Promise<SkillList> {
  const query = new URLSearchParams({ role, region, limit: String(limit) });
  return get<SkillList>(`/api/skills?${query}`, signal);
}
