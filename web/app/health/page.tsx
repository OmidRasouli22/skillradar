import type { Metadata } from "next";
import { HealthView } from "@/components/HealthView";

export const metadata: Metadata = {
  title: "SkillRadar: pipeline health",
  description: "Is the SkillRadar data fresh? Recent runs, data tests, Claude costs and answer quality.",
};

export default function HealthPage() {
  return <HealthView />;
}
