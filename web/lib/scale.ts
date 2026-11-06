// Sequential blue scale in 8 steps (CSS variables --seq-1 … --seq-8, light and dark).

export const STEPS = 8;

// Step 1 for the smallest values up to step 8 for the largest. Zero gets no color.
export function step(value: number, max: number): number {
  if (value <= 0 || max <= 0) return 0;
  return Math.min(STEPS, Math.max(1, Math.ceil((value / max) * STEPS)));
}

export function fill(stepIndex: number): string {
  return stepIndex === 0 ? "var(--track)" : `var(--seq-${stepIndex})`;
}

// Text on a filled cell: white on dark steps, near-black on light ones (per theme in CSS).
export function ink(stepIndex: number): string {
  return stepIndex === 0 ? "var(--muted)" : `var(--seq-ink-${stepIndex})`;
}
