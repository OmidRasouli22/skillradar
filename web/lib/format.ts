const number = new Intl.NumberFormat("en-GB");

export function count(value: number): string {
  return number.format(value);
}

export function percent(share: number): string {
  const value = share * 100;
  if (value > 0 && value < 1) return "<1%";
  return `${Math.round(value)}%`;
}

// "2026-11-06" -> "6 Nov 2026". Parsed as UTC so the day never shifts.
export function day(iso: string | null): string {
  if (!iso) return "unknown date";
  const date = new Date(`${iso}T00:00:00Z`);
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}
