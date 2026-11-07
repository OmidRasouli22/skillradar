import type { Metadata } from "next";
import { LabelTool } from "@/components/LabelTool";

export const metadata: Metadata = {
  title: "SkillRadar: review labels",
  robots: { index: false, follow: false },
};

// Local only (".local.tsx"): the public build leaves this page out, see next.config.ts.
export default function LabelPage() {
  return <LabelTool />;
}
