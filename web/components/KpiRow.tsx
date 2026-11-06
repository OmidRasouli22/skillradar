"use client";

import { useCountUp } from "@/hooks/motion";
import { count, percent } from "@/lib/format";

export type Kpi = { label: string; value: number; kind: "count" | "share"; hint: string };

// The headline numbers for the current selection; they count to each new value.
export function KpiRow({ kpis }: { kpis: Kpi[] }) {
  return (
    <div className="kpis">
      {kpis.map((kpi, index) => (
        <div className="kpi" key={kpi.label} style={{ "--i": index } as React.CSSProperties}>
          <div className="kpi-label">{kpi.label}</div>
          <KpiValue kpi={kpi} />
          <div className="kpi-hint">{kpi.hint}</div>
        </div>
      ))}
    </div>
  );
}

function KpiValue({ kpi }: { kpi: Kpi }) {
  const shown = useCountUp(kpi.value);
  return (
    <div className="kpi-value" aria-label={kpi.kind === "count" ? count(kpi.value) : percent(kpi.value)}>
      {kpi.kind === "count" ? count(Math.round(shown)) : percent(shown)}
    </div>
  );
}
