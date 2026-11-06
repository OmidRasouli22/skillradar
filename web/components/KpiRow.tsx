import { count, percent } from "@/lib/format";

export type Kpi = { label: string; value: number; kind: "count" | "share"; hint: string };

// The headline numbers for the current selection.
export function KpiRow({ kpis }: { kpis: Kpi[] }) {
  return (
    <div className="kpis">
      {kpis.map((kpi) => (
        <div className="kpi" key={kpi.label}>
          <div className="kpi-label">{kpi.label}</div>
          <div className="kpi-value">{kpi.kind === "count" ? count(kpi.value) : percent(kpi.value)}</div>
          <div className="kpi-hint">{kpi.hint}</div>
        </div>
      ))}
    </div>
  );
}
