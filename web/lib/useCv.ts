"use client";

import { useEffect, useState } from "react";
import { analyse, type Analysis, type CvProfile } from "@/lib/cv";

// Wait this long after the last edit or filter change before comparing again.
const DEBOUNCE_MS = 300;

export type CvAnalysis = { data: Analysis | null; loading: boolean; error: string | null };

// The comparison of a CV profile with the postings of the page's role and region.
// An older answer never replaces a newer one: it is aborted, and results carry their key.
export function useCvAnalysis(profile: CvProfile | null, role: string, region: string): CvAnalysis {
  const [result, setResult] = useState<{ key: string; data?: Analysis; error?: string } | null>(null);
  const key = profile ? JSON.stringify([profile, role, region]) : null;

  useEffect(() => {
    if (!profile || !key) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      analyse(profile, role, region, controller.signal)
        .then((data) => setResult({ key, data }))
        .catch((error: Error) => {
          if (error.name !== "AbortError") setResult({ key, error: error.message });
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [key, profile, role, region]);

  if (!profile) return { data: null, loading: false, error: null };
  const current = result?.key === key ? result : null;
  return {
    // While a new comparison runs, the last one stays visible (dimmed).
    data: current?.data ?? result?.data ?? null,
    loading: !current,
    error: current?.error ?? null,
  };
}
