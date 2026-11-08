"use client";

import { percent } from "@/lib/format";

const SIZE = 340;
const CENTER = SIZE / 2;
const RINGS = [36, 72, 108, 144];
// The sweep turns once in this time; each blip lights up as it passes.
const TURN_S = 7;

// The hero picture: the most asked skills of the current selection as blips on a
// radar. The more postings ask for a skill, the closer it sits to the center.
export function Radar({ skills }: { skills: { name: string; share: number }[] }) {
  const top = skills.slice(0, 7);
  const most = Math.max(...top.map((s) => s.share), 0.01);
  return (
    <figure className="radar" aria-label={`Most asked skills: ${top.map((s) => `${s.name} ${percent(s.share)}`).join(", ")}`}>
      <div className="radar-sweep" style={{ animationDuration: `${TURN_S}s` }} aria-hidden="true" />
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden="true">
        {RINGS.map((r) => (
          <circle key={r} cx={CENTER} cy={CENTER} r={r} className="radar-ring" />
        ))}
        <line x1={CENTER} y1={CENTER - 150} x2={CENTER} y2={CENTER + 150} className="radar-axis" />
        <line x1={CENTER - 150} y1={CENTER} x2={CENTER + 150} y2={CENTER} className="radar-axis" />
        {top.map((skill, i) => {
          // Spread the blips around the circle, starting at the top, clockwise like the sweep.
          const angle = (i / top.length) * 360 + 18;
          const radius = 34 + (1 - skill.share / most) * 98;
          const rad = ((angle - 90) * Math.PI) / 180;
          const x = CENTER + radius * Math.cos(rad);
          const y = CENTER + radius * Math.sin(rad);
          const right = Math.cos(rad) >= 0;
          const delay = `${((angle / 360) * TURN_S).toFixed(2)}s`;
          return (
            <g key={skill.name} className="radar-blip" style={{ animationDelay: delay }}>
              <circle cx={x} cy={y} r={11} className="radar-halo" style={{ animationDelay: delay }} />
              <circle cx={x} cy={y} r={4.5} className="radar-dot" />
              <text x={x + (right ? 10 : -10)} y={y + 4} textAnchor={right ? "start" : "end"} className="radar-label">
                {skill.name}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption>Most asked skills · closer to the center = asked more</figcaption>
    </figure>
  );
}
