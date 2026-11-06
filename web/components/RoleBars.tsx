"use client";

import { count, percent } from "@/lib/format";
import { useTip } from "./Tooltip";

export type RoleValue = { id: string; label: string; share: number; postings: number; total: number };

// One bar per role. When a role is chosen it keeps the accent color and the others turn
// gray; with "all roles" every bar is in the accent color.
export function RoleBars(props: { rows: RoleValue[]; selected: string; onSelect: (id: string) => void }) {
  const { rows, selected, onSelect } = props;
  const tip = useTip();
  return (
    <ul className={selected === "all" ? "bars compact" : "bars compact focus"}>
      {rows.map((row) => (
        <li
          key={row.id}
          className={row.id === selected ? "bar-row emphasis" : "bar-row"}
          onClick={() => onSelect(row.id)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onSelect(row.id);
            }
          }}
          {...tip({
            value: percent(row.share),
            label: row.label,
            detail: `${count(row.postings)} of ${count(row.total)} postings`,
          })}
        >
          <span className="name">{row.label}</span>
          <span className="track" aria-hidden="true">
            <span className="fill one" style={{ width: `${row.share * 100}%` }} />
          </span>
          <span className="value">{percent(row.share)}</span>
        </li>
      ))}
    </ul>
  );
}
