import xml.etree.ElementTree as ET

from skillradar.publish.figures import DARK, LIGHT, Bar, bar_chart, write_figures
from tests.test_api import write_gold


def test_bar_chart_is_valid_svg_with_escaped_text():
    bars = [Bar("C# & .NET <core>", 0.5, 0.3), Bar("Go", 0.25)]
    svg = bar_chart("Skills", "A note", bars, LIGHT, [("Required", "main")])
    root = ET.fromstring(svg)  # noqa: S314 - our own SVG; fails if a name was not escaped
    texts = [t.text for t in root.iter("{http://www.w3.org/2000/svg}text")]
    assert "C# & .NET <core>" in texts and "50%" in texts and "25%" in texts


def test_light_and_dark_use_their_own_colors():
    bars = [Bar("Python", 0.3)]
    assert LIGHT.surface in bar_chart("t", "n", bars, LIGHT, [])
    assert DARK.surface in bar_chart("t", "n", bars, DARK, [])


def test_gray_rows_are_not_the_point():
    svg = bar_chart("t", "n", [Bar("All", 0.1), Bar("Other", 0.05, strong=False)], LIGHT, [])
    assert LIGHT.main in svg and LIGHT.dim in svg


def test_write_figures_from_gold(tmp_path):
    write_gold(tmp_path)
    written = write_figures(tmp_path, tmp_path / "images")
    assert sorted(p.name for p in written) == [
        "ai-wave-dark.svg",
        "ai-wave-light.svg",
        "top-skills-dark.svg",
        "top-skills-light.svg",
    ]
    top = (tmp_path / "images" / "top-skills-light.svg").read_text()
    assert "Python" in top and "75%" in top and "6 Nov 2026" in top
    for path in written:
        ET.fromstring(path.read_text())  # noqa: S314 - parses the SVG we just wrote
