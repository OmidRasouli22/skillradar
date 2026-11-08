import type { Metadata } from "next";
import { CvAnalyser } from "@/components/cv/CvAnalyser";

export const metadata: Metadata = {
  title: "SkillRadar: CV analysis",
  description: "Compare a CV with the open tech postings: fit, best matches and what to learn next.",
  robots: { index: false, follow: false },
};

// Local only (".local.tsx"): the public build leaves this page out, see next.config.ts.
export default function CvPage() {
  return <CvAnalyser />;
}
