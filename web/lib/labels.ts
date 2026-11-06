// Names and order for the answer values the model gives.

// tone fills the mark; ink is the text color that reads on that fill (set per theme in CSS).
export type Level = { value: string; label: string; tone: string; ink: string };

// Ordered from the strongest requirement down; tones are steps of the ordinal ramp.
export const GERMAN: Level[] = [
  { value: "native", label: "Native", tone: "var(--ord-4)", ink: "var(--ord-ink-4)" },
  { value: "fluent", label: "Fluent (C1–C2)", tone: "var(--ord-3)", ink: "var(--ord-ink-3)" },
  { value: "good", label: "Good (B2)", tone: "var(--ord-2)", ink: "var(--ord-ink-2)" },
  { value: "basic", label: "Basic", tone: "var(--ord-1)", ink: "var(--ord-ink-1)" },
  { value: "unknown", label: "Asked, level not stated", tone: "var(--gray-2)", ink: "var(--gray-ink-2)" },
  { value: "not asked", label: "Not mentioned", tone: "var(--gray-1)", ink: "var(--gray-ink-1)" },
];

export const REMOTE: Level[] = [
  { value: "onsite", label: "On site", tone: "var(--ord-1)", ink: "var(--ord-ink-1)" },
  { value: "hybrid", label: "Hybrid", tone: "var(--ord-3)", ink: "var(--ord-ink-3)" },
  { value: "remote", label: "Fully remote", tone: "var(--ord-5)", ink: "var(--ord-ink-5)" },
  { value: "unknown", label: "Not mentioned", tone: "var(--gray-1)", ink: "var(--gray-ink-1)" },
];

export const SENIORITY: Level[] = [
  { value: "student", label: "Student", tone: "var(--ord-1)", ink: "var(--ord-ink-1)" },
  { value: "junior", label: "Junior", tone: "var(--ord-2)", ink: "var(--ord-ink-2)" },
  { value: "mid", label: "Professional", tone: "var(--ord-3)", ink: "var(--ord-ink-3)" },
  { value: "senior", label: "Senior", tone: "var(--ord-4)", ink: "var(--ord-ink-4)" },
  { value: "lead", label: "Lead", tone: "var(--ord-5)", ink: "var(--ord-ink-5)" },
  { value: "unknown", label: "Not clear", tone: "var(--gray-1)", ink: "var(--gray-ink-1)" },
];

// Short names for the state tiles.
export const STATE_SHORT: Record<string, string> = {
  BADEN_WUERTTEMBERG: "BW",
  BAYERN: "BY",
  BERLIN: "BE",
  BRANDENBURG: "BB",
  BREMEN: "HB",
  HAMBURG: "HH",
  HESSEN: "HE",
  MECKLENBURG_VORPOMMERN: "MV",
  NIEDERSACHSEN: "NI",
  NORDRHEIN_WESTFALEN: "NW",
  RHEINLAND_PFALZ: "RP",
  SAARLAND: "SL",
  SACHSEN: "SN",
  SACHSEN_ANHALT: "ST",
  SCHLESWIG_HOLSTEIN: "SH",
  THUERINGEN: "TH",
};

// A rough map of Germany: [column, row] for each state's tile.
export const STATE_TILES: Record<string, [number, number]> = {
  SCHLESWIG_HOLSTEIN: [2, 0],
  MECKLENBURG_VORPOMMERN: [3, 0],
  BREMEN: [1, 1],
  HAMBURG: [2, 1],
  BRANDENBURG: [3, 1],
  BERLIN: [4, 1],
  NORDRHEIN_WESTFALEN: [0, 2],
  NIEDERSACHSEN: [1, 2],
  SACHSEN_ANHALT: [2, 2],
  SACHSEN: [3, 2],
  RHEINLAND_PFALZ: [0, 3],
  HESSEN: [1, 3],
  THUERINGEN: [2, 3],
  SAARLAND: [0, 4],
  BADEN_WUERTTEMBERG: [1, 4],
  BAYERN: [2, 4],
};
