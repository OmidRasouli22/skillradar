// Types and calls for the CV analysis page (local only): src/skillradar/api/cv.py.

export type Evidence = "work" | "project" | "education" | "listed";
export type Level = "basic" | "good" | "fluent" | "native" | "unknown";

export type CvSkill = {
  name: string;
  evidence: Evidence;
  years: number | null;
  last_used: number | null;
  context: string;
  source: "claude" | "keyword" | "you";
};

export type CvProfile = {
  headline: string;
  role: string;
  seniority: string;
  years_experience: number | null;
  languages: { language: string; level: Level }[];
  skills: CvSkill[];
};

export type Choice = { id: string; label: string };

export type CvStatus = {
  claude: boolean;
  model: string;
  typical_cost_usd: number;
  budget_usd: number;
  room_left_usd: number;
  limits: { pdf_mb: number; min_chars: number; max_chars: number };
  skills: string[];
  roles: Choice[];
  regions: Choice[];
};

export type ReadResult = { mode: "claude" | "keywords"; profile: CvProfile; notes: string[]; cost_usd: number };

export type Coverage = {
  kind: "have" | "proven" | "substitute" | "missing" | "lower";
  via: string | null;
  value: number;
};

export type Gap = {
  kind: "skill" | "language";
  name: string;
  postings: number;
  required_postings: number;
  share: number;
  coverage: Coverage;
  gained: number;
  mean_gain: number;
  builds_on: string[];
};

export type Match = {
  refnr: string;
  title: string;
  employer: string | null;
  city: string | null;
  regions: number;
  published: string | null;
  role: string;
  seniority: string;
  remote: string;
  match: number;
  band: "strong" | "good" | "partial" | "weak";
  parts: { skills: number; language: number; seniority: number };
  skills: { skill: string; required: boolean; coverage: Coverage }[];
  languages: { language: string; needed: string; have: string | null }[];
};

export type Analysis = {
  role: string;
  role_label: string;
  region: string;
  region_label: string;
  as_of: string | null;
  summary: {
    postings: number;
    scored: number;
    bands: Record<"strong" | "good" | "partial" | "weak", number>;
    median: number | null;
    good_or_better: number;
  };
  roles: { id: string; label: string; scored: number; good_or_better: number; share: number; median: number }[];
  demand: {
    skill: string;
    postings: number;
    required_postings: number;
    share: number;
    coverage: Coverage;
    evidence: Evidence | null;
  }[];
  gaps: Gap[];
  matches: Match[];
};

export type ShowcaseItem = {
  id: string;
  title: string;
  person: string;
  language: string;
  target: { role: string; region: string };
};

export type Showcase = ShowcaseItem & {
  story: string;
  text: string;
  profile: CvProfile | null;
  notes: string[];
  read: { read_at: string | null; model: string | null; prompt_version: string | null };
};

export type CheckResult = { kind: string; check: string; why: string; passed: boolean; actual: string };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

const post = <T,>(path: string, body: unknown, signal?: AbortSignal) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body), signal });

export const getStatus = () => call<CvStatus>("/api/cv/status");

export const readPdf = (data: string) => post<{ text: string; pages: number; chars: number }>("/api/cv/pdf", { data });

export const readCv = (text: string, mode: "claude" | "keywords") => post<ReadResult>("/api/cv/read", { text, mode });

export const analyse = (profile: CvProfile, role: string, region: string, signal?: AbortSignal) =>
  post<Analysis>("/api/cv/analyse", { profile, role, region }, signal);

export const getShowcases = () => call<ShowcaseItem[]>("/api/cv/showcases");

export const getShowcase = (id: string) => call<Showcase>(`/api/cv/showcases/${encodeURIComponent(id)}`);

export const getShowcaseChecks = (id: string) =>
  call<{ as_of: string | null; results: CheckResult[] }>(`/api/cv/showcases/${encodeURIComponent(id)}/checks`);

// Labels shown on the page.
export const EVIDENCE: { value: Evidence; label: string; hint: string }[] = [
  { value: "work", label: "Used at work", hint: "counts 100%" },
  { value: "project", label: "Project", hint: "counts 80%" },
  { value: "education", label: "Course or degree", hint: "counts 70%" },
  { value: "listed", label: "Only listed", hint: "counts 60%" },
];

export const LEVELS: { value: Level | ""; label: string }[] = [
  { value: "", label: "None" },
  { value: "basic", label: "Basic (A1–B1)" },
  { value: "good", label: "Good (B2)" },
  { value: "fluent", label: "Fluent (C1–C2)" },
  { value: "native", label: "Native" },
  { value: "unknown", label: "Yes, level not stated" },
];

export const SENIORITY = [
  { value: "student", label: "Student" },
  { value: "junior", label: "Junior (0–2 yrs)" },
  { value: "mid", label: "Professional (2–5 yrs)" },
  { value: "senior", label: "Senior (5+ yrs)" },
  { value: "lead", label: "Lead" },
  { value: "unknown", label: "Not clear" },
];

export const BAND_LABEL: Record<Match["band"], string> = {
  strong: "Strong match",
  good: "Good match",
  partial: "Partial match",
  weak: "Weak match",
};
