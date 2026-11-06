"use client";

import type { Part } from "@/lib/api";
import { count, percent } from "@/lib/format";
import type { Level } from "@/lib/labels";
import { useTip } from "./Tooltip";

export type StackRow = { id: string; label: string; total: number; parts: Part[] };

// One 100% bar per row, split into ordered levels.
export function StackedBars(props: {
  rows: StackRow[];
  levels: Level[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const { rows, levels, selected, onSelect } = props;
  const tip = useTip();
  return (
    <ul className="stacks">
      {rows.map((row) => {
        const byValue = Object.fromEntries(row.parts.map((p) => [p.value, p]));
        return (
          <li key={row.id} className={row.id === selected ? "selected" : undefined}>
            <button type="button" className="name" onClick={() => onSelect(row.id)}>
              {row.label}
            </button>
            <span className="stack">
              {levels.map((level) => {
                const part = byValue[level.value];
                if (!part || part.share <= 0) return null;
                return (
                  <span
                    key={level.value}
                    className="segment"
                    style={{ width: `${part.share * 100}%`, background: level.tone }}
                    {...tip({
                      value: percent(part.share),
                      label: `${row.label} · ${level.label}`,
                      detail: `${count(part.postings)} of ${count(row.total)} postings`,
                    })}
                  />
                );
              })}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
