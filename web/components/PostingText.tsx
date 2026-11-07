"use client";

import { useMemo } from "react";
import type { Mark } from "@/lib/api";

type Kind = Mark["kind"];
const NONE = new Set<Kind>();

// The text as paragraphs and lists. Lines are plain text; marks are <mark> elements.
// still: no sweep-in animation, for a page where the marks change while you work.
export function PostingText(props: { text: string; marks: Mark[]; hidden?: Set<Kind>; still?: boolean }) {
  const { text, marks, hidden = NONE, still = false } = props;
  const blocks = useMemo(() => toBlocks(text), [text]);
  return (
    <div className={still ? "posting still" : "posting"}>
      {blocks.map((block, b) =>
        block.kind === "list" ? (
          <ul key={b}>
            {block.lines.map((line) => (
              <li key={line.start}>{renderRange(text, line.start, line.end, marks, hidden)}</li>
            ))}
          </ul>
        ) : (
          <p key={b} className={block.heading ? "heading" : undefined}>
            {block.lines.map((line, i) => (
              <span key={line.start}>
                {i > 0 && <br />}
                {renderRange(text, line.start, line.end, marks, hidden)}
              </span>
            ))}
          </p>
        ),
      )}
    </div>
  );
}

type Line = { start: number; end: number };
type Block = { kind: "paragraph" | "list"; lines: Line[]; heading?: boolean };

// Blank lines split paragraphs; lines starting with "- " form a list. Offsets stay those
// of the full text, so the marks from the API still fit.
function toBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let at = 0;
  for (const raw of text.split("\n")) {
    const start = at;
    const end = at + raw.length;
    at = end + 1;
    if (raw.trim() === "") {
      blocks.push({ kind: "paragraph", lines: [] });
      continue;
    }
    const isItem = /^\s*-\s+/.test(raw);
    const content = isItem ? { start: start + raw.indexOf("-") + 1, end } : { start, end };
    const last = blocks[blocks.length - 1];
    const kind = isItem ? "list" : "paragraph";
    if (last && last.kind === kind && last.lines.length > 0) last.lines.push(content);
    else blocks.push({ kind, lines: [content] });
  }
  return blocks
    .filter((block) => block.lines.length > 0)
    .map((block) => {
      const only = block.lines[0];
      const line = text.slice(only.start, only.end).trim();
      // A short single line ending in ":" or without a full stop reads as a heading.
      const heading = block.kind === "paragraph" && block.lines.length === 1 && line.length < 60 && !/[.!?]$/.test(line);
      return { ...block, heading };
    });
}

function renderRange(text: string, start: number, end: number, marks: Mark[], hidden: Set<Kind>) {
  const parts: React.ReactNode[] = [];
  let at = start;
  marks.forEach((mark, index) => {
    if (mark.end <= start || mark.start >= end) return;
    const from = Math.max(mark.start, start);
    const to = Math.min(mark.end, end);
    if (from > at) parts.push(text.slice(at, from));
    parts.push(
      <mark
        key={index}
        data-i={index}
        className={hidden.has(mark.kind) ? `${mark.kind} off` : mark.kind}
        style={{ "--i": Math.min(index, 40) } as React.CSSProperties}
      >
        {text.slice(from, to)}
      </mark>,
    );
    at = to;
  });
  if (at < end) parts.push(text.slice(at, end));
  return parts;
}
