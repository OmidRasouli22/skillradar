"use client";

import type { Part } from "@/lib/api";
import { count, percent } from "@/lib/format";
import type { Level } from "@/lib/labels";
import { useTip } from "./Tooltip";

// One whole split into parts, with the share printed on each part that is wide enough.
export function SegmentedBar(props: { title: string; parts: Part[]; levels: Level[]; total: number }) {
  const { title, parts, levels, total } = props;
  const tip = useTip();
  const byValue = Object.fromEntries(parts.map((p) => [p.value, p]));
  const shown = levels.filter((level) => (byValue[level.value]?.share ?? 0) > 0);
  return (
    <figure className="segmented">
      <figcaption className="mini-title">{title}</figcaption>
      <div className="segments">
        {shown.map((level) => {
          const part = byValue[level.value];
          return (
            <span
              key={level.value}
              className="block"
              style={{ width: `${part.share * 100}%`, background: level.tone }}
              {...tip({
                value: percent(part.share),
                label: level.label,
                detail: `${count(part.postings)} of ${count(total)} postings`,
              })}
            >
              {part.share >= 0.09 && (
                <span className="block-label" style={{ color: level.ink }}>
                  {percent(part.share)}
                </span>
              )}
            </span>
          );
        })}
      </div>
      <div className="legend">
        {shown.map((level) => (
          <span className="swatch" key={level.value}>
            <i style={{ background: level.tone }} />
            {level.label}
          </span>
        ))}
      </div>
    </figure>
  );
}
