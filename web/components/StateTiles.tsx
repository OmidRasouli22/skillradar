"use client";

import type { Choice } from "@/lib/api";
import { count } from "@/lib/format";
import { STATE_SHORT, STATE_TILES } from "@/lib/labels";
import { fill, ink, step } from "@/lib/scale";
import { useTip } from "./Tooltip";

// A rough map of Germany, one tile per state, darker = more postings. Click to filter.
export function StateTiles(props: { states: Choice[]; selected: string; onSelect: (id: string) => void }) {
  const { states, selected, onSelect } = props;
  const tip = useTip();
  const byId = Object.fromEntries(states.map((s) => [s.id, s]));
  const max = Math.max(1, ...states.map((s) => s.postings));
  return (
    <div className="tiles" role="group" aria-label="Postings per German state">
      {Object.entries(STATE_TILES).map(([id, [column, row]]) => {
        const postings = byId[id]?.postings ?? 0;
        const label = byId[id]?.label ?? id;
        const s = step(postings, max);
        return (
          <button
            key={id}
            type="button"
            className={id === selected ? "tile selected" : "tile"}
            style={{
              gridColumn: column + 1,
              gridRow: row + 1,
              background: fill(s),
              color: ink(s),
            }}
            onClick={() => onSelect(id === selected ? "all" : id)}
            aria-pressed={id === selected}
            {...tip({ value: `${count(postings)} postings`, label, detail: "Click to filter the page" })}
          >
            <span className="tile-short">{STATE_SHORT[id]}</span>
            <span className="tile-count">{count(postings)}</span>
          </button>
        );
      })}
    </div>
  );
}
