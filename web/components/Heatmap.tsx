"use client";

import type { Dashboard } from "@/lib/api";
import { count, percent } from "@/lib/format";
import { fill, step } from "@/lib/scale";
import { useTip } from "./Tooltip";

// Roles × the most asked-for skills. Darker = a larger share of the role's postings.
export function Heatmap(props: {
  heatmap: Dashboard["heatmap"];
  selected: string;
  onSelect: (role: string) => void;
}) {
  const { heatmap, selected, onSelect } = props;
  const tip = useTip();
  return (
    <div className="heatmap-wrap">
      <table className="heatmap">
        <thead>
          <tr>
            <th scope="col" className="sr-only">
              Role
            </th>
            {heatmap.skills.map((skill) => (
              <th key={skill} scope="col">
                <span>{skill}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {heatmap.rows.map((row) => (
            <tr key={row.id} className={row.id === selected ? "selected" : undefined}>
              <th scope="row">
                <button type="button" onClick={() => onSelect(row.id)} aria-pressed={row.id === selected}>
                  {row.label}
                  <small>{count(row.postings)}</small>
                </button>
              </th>
              {row.shares.map((share, index) => (
                <td key={heatmap.skills[index]}>
                  <span
                    className="cell"
                    style={{ background: fill(step(share, 1)) }}
                    {...tip({
                      value: percent(share),
                      label: `${row.label} · ${heatmap.skills[index]}`,
                      detail: `of ${count(row.postings)} postings`,
                    })}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ScaleLegend() {
  const stops = [1, 2, 3, 4, 5, 6, 7, 8];
  return (
    <span className="scale" aria-label="Color scale from 0% to 100% of postings">
      <span>0%</span>
      {stops.map((s) => (
        <i key={s} style={{ background: `var(--seq-${s})` }} />
      ))}
      <span>100%</span>
    </span>
  );
}
