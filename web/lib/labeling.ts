// Calls for the review page (local only): the evaluation labels in eval/labels.jsonl.

import type { Mark } from "@/lib/api";

export type Status = "todo" | "draft" | "verified";

export type SkillItem = { name: string; required: boolean };
export type LanguageItem = { language: string; level: string };

export type Answer = {
  role: string;
  seniority: string;
  remote: string;
  languages: LanguageItem[];
  skills: SkillItem[];
};

export type Label = {
  refnr: string;
  status: Status;
  answer: Answer | null;
  drafted_by: string | null;
  verified_at: string | null;
  note: string;
};

export type Sample = {
  items: { refnr: string; status: Status; title: string | null }[];
  choices: {
    role: { id: string; hint: string }[];
    seniority: string[];
    remote: string[];
    language: string[];
    level: string[];
  };
  skills: string[];
};

export type LabelPosting = { refnr: string; title: string; text: string; label: Label };

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

const path = (refnr: string) => `/api/labels/${encodeURIComponent(refnr)}`;

export const getSample = () => call<Sample>("/api/labels");

export const getLabelPosting = (refnr: string) => call<LabelPosting>(path(refnr));

export function getMarks(refnr: string, skills: SkillItem[], signal?: AbortSignal) {
  return call<{ marks: Mark[] }>(`${path(refnr)}/marks`, {
    method: "POST",
    body: JSON.stringify({ skills }),
    signal,
  });
}

export function saveLabel(refnr: string, answer: Answer, status: "draft" | "verified", note: string) {
  return call<Label>(path(refnr), { method: "PUT", body: JSON.stringify({ answer, status, note }) });
}
