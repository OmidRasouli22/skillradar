// Types and calls for the data. The local page asks the API (src/skillradar/api); the
// public page reads the JSON files that skillradar-publish writes.

// Set at build time by `npm run build:public`.
export const PUBLIC_SITE = process.env.NEXT_PUBLIC_DATA_MODE === "static";
const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const PAGE_SIZE = 20;

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

export type PostingCard = {
  refnr: string;
  title: string;
  employer: string | null;
  city: string | null;
  published: string | null;
  seniority: string;
  remote: string;
  skills: string[];
};

export type PostingList = {
  role: string;
  region: string;
  total: number;
  offset: number;
  items: PostingCard[];
};

export type Mark = {
  start: number;
  end: number;
  kind: "required" | "nice" | "language" | "home_office";
  label: string;
};

export type PostingDetail = {
  refnr: string;
  title: string;
  employer: string | null;
  city: string | null;
  region: string | null;
  published: string | null;
  role: string;
  role_id: string;
  role_postings: number;
  seniority: string;
  remote: string;
  german: string;
  english: string;
  url: string;
  // share_in_role: how many postings of the same role ask for the skill
  skills: { name: string; required: boolean; emerging: boolean; share_in_role: number }[];
  text: string;
  marks: Mark[];
};

class NotFound extends Error {}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal, headers: { Accept: "application/json" } });
  if (response.status === 404) throw new NotFound("not found");
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

// A file name part from an id; ids are checked by the API, this only keeps paths safe.
function part(id: string): string {
  return encodeURIComponent(id);
}

export function getOverview(signal?: AbortSignal): Promise<Overview> {
  return get<Overview>(PUBLIC_SITE ? `${BASE}/data/overview.json` : "/api/overview", signal);
}

export function getDashboard(region: string, signal?: AbortSignal): Promise<Dashboard> {
  return get<Dashboard>(
    PUBLIC_SITE
      ? `${BASE}/data/dashboard/${part(region)}.json`
      : `/api/dashboard?${new URLSearchParams({ region })}`,
    signal,
  );
}

// The public site has one file per role and region with every posting; pages of 20 are
// cut from it here, so the list behaves the same as with the API.
const lists = new Map<string, Promise<PostingList>>();

export async function getPostings(
  role: string,
  region: string,
  offset: number,
  signal?: AbortSignal,
): Promise<PostingList> {
  if (!PUBLIC_SITE) {
    const query = new URLSearchParams({ role, region, offset: String(offset), limit: String(PAGE_SIZE) });
    return get<PostingList>(`/api/postings?${query}`, signal);
  }
  const key = `${role}/${region}`;
  if (!lists.has(key)) {
    const file = get<PostingList>(`${BASE}/data/postings/${part(role)}/${part(region)}.json`).catch(
      (error) => {
        if (error instanceof NotFound) return { role, region, total: 0, offset: 0, items: [] };
        lists.delete(key);
        throw error;
      },
    );
    lists.set(key, file);
  }
  const all = await lists.get(key)!;
  if (signal?.aborted) throw new DOMException("aborted", "AbortError");
  return { ...all, offset, items: all.items.slice(offset, offset + PAGE_SIZE) };
}

export async function getPosting(refnr: string, signal?: AbortSignal): Promise<PostingDetail> {
  try {
    return await get<PostingDetail>(
      PUBLIC_SITE ? `${BASE}/data/jobs/${part(refnr)}.json` : `/api/postings/${part(refnr)}`,
      signal,
    );
  } catch (error) {
    if (error instanceof NotFound) throw new Error("no open posting with this number");
    throw error;
  }
}
