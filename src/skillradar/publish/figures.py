"""Command line: uv run skillradar-figures

Draws the README charts from the gold tables as SVG files in assets/images/, one light and
one dark version of each, with the same colors as the page.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import duckdb

from skillradar.api.labels import ROLES
from skillradar.config import DATA_DIR, PROJECT_ROOT
from skillradar.transform.runner import serve_dir

IMAGES = PROJECT_ROOT / "assets" / "images"
FONT = "system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str
    text: str
    secondary: str
    muted: str
    track: str
    main: str  # required, or the one series
    soft: str  # nice to have
    dim: str  # rows that are not the point


LIGHT = Theme(
    "light", "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#f0efec", "#2a78d6", "#b7d3f6", "#c3c2b7"
)
DARK = Theme(
    "dark", "#1a1a19", "#f0efec", "#c3c2b7", "#898781", "#242422", "#3987e5", "#184f95", "#4a4a46"
)


@dataclass(frozen=True)
class Bar:
    label: str
    value: float  # 0..1, the whole bar
    part: float = 0.0  # 0..1, the darker part from the start (e.g. required)
    strong: bool = True  # False draws the bar in the gray of rows that are not the point


def rect(x: float, y: float, width: float, height: float, fill: str, rx: int = 4) -> str:
    return f'<rect x="{x}" y="{y}" width="{width:.1f}" height="{height}" rx="{rx}" fill="{fill}"/>'


def text(x: float, y: float, content: str, fill: str, size: int = 13, **attrs: str) -> str:
    extra = "".join(f' {key.replace("_", "-")}="{value}"' for key, value in attrs.items())
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{extra}>{escape(content)}</text>'


def bar_chart(
    title: str, note: str, bars: list[Bar], theme: Theme, legend: list[tuple[str, str]]
) -> str:
    """Horizontal bars, largest first, with the share at each bar's end."""
    width, left, right, row = 760, 190, 64, 30
    top = 92 if legend else 72
    height = top + row * len(bars) + 44
    plot = width - left - right
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}" '
        f'font-family="{FONT}">',
        rect(0, 0, width, height, theme.surface, rx=14),
        text(24, 38, title, theme.text, size=18, font_weight="650"),
        text(24, 60, note, theme.secondary),
    ]
    x = 24
    for name, kind in legend:
        out.append(rect(x, 72, 10, 10, theme.main if kind == "main" else theme.soft, rx=3))
        out.append(text(x + 16, 81, name, theme.secondary, size=12))
        x += 16 + 7 * len(name) + 24
    for i, bar in enumerate(bars):
        y = top + i * row
        main = theme.main if bar.strong else theme.dim
        weight = "650" if bar.strong and not bar.part else "550"
        out.append(
            text(left - 14, y + 15, bar.label, theme.text, font_weight=weight, text_anchor="end")
        )
        out.append(rect(left, y + 4, plot, 14, theme.track))
        if bar.part:
            out.append(rect(left, y + 4, max(bar.value * plot, 2), 14, theme.soft))
            out.append(rect(left, y + 4, max(bar.part * plot, 2), 14, main))
        else:
            out.append(rect(left, y + 4, max(bar.value * plot, 2), 14, main))
        share = f"{round(bar.value * 100)}%"
        out.append(
            text(width - 24, y + 15, share, theme.text, font_weight="600", text_anchor="end")
        )
    source = "Source: Bundesagentur für Arbeit, read by Claude. SkillRadar."
    out.append(text(24, height - 18, source, theme.muted, size=11))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def top_skills(con: duckdb.DuckDBPyConnection, n: int = 12) -> tuple[str, list[Bar]]:
    [(as_of, total)] = con.execute("select as_of, tech_postings from gold_meta").fetchall()
    rows = con.execute(
        "select skill, share, required_postings / total_postings from gold_skill_demand "
        "where role = 'all' and region = 'all' order by share desc, skill limit ?",
        [n],
    ).fetchall()
    when = f"{as_of.day} {as_of:%b %Y}"
    note = f"Share of {total:,} open tech job postings that ask for each skill, {when}"
    return note, [Bar(name, float(share), float(required)) for name, share, required in rows]


# Rows drawn in color in the AI chart; the others are gray, so the story reads at a glance.
AI_HIGHLIGHT = ("all", "ml_engineer")


def ai_wave(con: duckdb.DuckDBPyConnection) -> tuple[str, list[Bar]]:
    [(as_of,)] = con.execute("select as_of from gold_meta").fetchall()
    rows = con.execute(
        "select role, share from gold_emerging_share where region = 'all' order by share desc, role"
    ).fetchall()
    note = (
        "Postings that ask for a skill mainstream only since 2022 "
        f"(LLMs, RAG, AI coding tools), {as_of.day} {as_of:%b %Y}"
    )
    return note, [
        Bar(ROLES.get(role, role), float(share), strong=role in AI_HIGHLIGHT)
        for role, share in rows
    ]


def write_figures(data_dir: Path, folder: Path = IMAGES) -> list[Path]:
    con = duckdb.connect()
    for table in ("gold_meta", "gold_skill_demand", "gold_emerging_share"):
        con.read_parquet(str(serve_dir(data_dir) / f"{table}.parquet")).create_view(table)
    charts = [
        ("top-skills", "The most asked-for skills in German tech jobs", *top_skills(con),
         [("Required", "main"), ("Nice to have", "soft")]),
        ("ai-wave", "How many postings ask for new AI skills, by role", *ai_wave(con), []),
    ]  # fmt: skip
    con.close()
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, title, note, bars, legend in charts:
        for theme in (LIGHT, DARK):
            path = folder / f"{name}-{theme.name}.svg"
            path.write_text(bar_chart(title, note, bars, theme, legend), "utf-8")
            written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draw the README charts from the gold tables.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args(argv)
    for path in write_figures(args.data_dir.resolve()):
        print(f"wrote {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
