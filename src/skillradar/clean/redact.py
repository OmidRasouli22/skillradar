"""Remove personal data from posting texts: emails, phone numbers, links and contact names.

Uses rules, not a name model. A name model would also remove skills like "Kafka".
"""

import re
from dataclasses import dataclass

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LINK = re.compile(r"(?:https?://|www\.)[^\s)\]>]+", re.IGNORECASE)
# +49, 0049 or 0, then digits and separators on one line. Digits are counted in _phone().
PHONE = re.compile(r"(?<![\w.])(?:\+\d{2}|00\d{2}|\(?0)[\d \t/()\-–]{5,}\d")

# Letters with accents count too: "René", "Toromanović".
UPPER = r"A-ZÄÖÜÀ-ÖØ-Þ"
LOWER = r"a-zäöüßà-öø-ÿ\u0100-\u017f"
NAME_WORD = rf"[{UPPER}][{LOWER}]+(?:-[{UPPER}][{LOWER}]+)?"
# Names never cross a line break, so only spaces and tabs join their words.
TITLES = r"(?:(?:Prof|Dr|Dipl)\.(?:[\w-]+\.)?[ \t]*)*"
FULL_NAME = rf"{TITLES}{NAME_WORD}(?:[ \t]+(?:[A-Z]\.?[ \t]+)?{NAME_WORD}){{0,2}}"
FIRST_AND_LAST = rf"{TITLES}{NAME_WORD}(?:[ \t]+(?:[A-Z]\.?[ \t]+)?{NAME_WORD}){{1,2}}"

# "Frau Dr. Anna Schmidt", "Herrn Müller"
SALUTATION = re.compile(rf"\b(Herrn?|Frau)[ \t]+{FULL_NAME}")
# "Ansprechpartnerin: Lisa Schuppeli", "Ansprechpartner*in ist Romina Esser".
# Singular forms only, and first plus last name, so job duties are not touched.
CONTACT = re.compile(
    rf"\b(Ansprechpartner(?:in|\*in|:in|_in|/-?in|\(in\))?|Kontaktperson|Contact person"
    rf"|Your contact)(?![{LOWER}])([ \t*:]*(?:ist|is)?[ \t*:]*\n?[ \t*]*)({FIRST_AND_LAST})"
)
# A line that is only a name, e.g. "Christine Höpfner" above a phone number.
NAME_LINE = re.compile(rf"[ \t*_]*({TITLES}{NAME_WORD}(?:[ \t]+{NAME_WORD}){{1,2}})[ \t*_]*")

# Capitalised words that look like names but start sentences, headings or job titles.
NOT_NAMES = {
    "Bei", "Bitte", "Bewerbung", "Bewerbungen", "Das", "Der", "Die", "Du", "Ein", "Eine",
    "Frau", "Fragen", "Für", "Gerne", "Haben", "Hast", "Herr", "Herrn", "Hier", "Ihr",
    "Ihre", "Jetzt", "Kontakt", "Mit", "Möchtest", "Personalabteilung", "Recruiting", "Sie",
    "Team", "Und", "Unser", "Unsere", "Wir", "Wenn",
    "Administrator", "Analyst", "Architekt", "Berater", "Beraterin", "Consultant", "Developer",
    "Engineer", "Entwickler", "Entwicklerin", "Leiter", "Leiterin", "Leitung", "Manager",
    "Managerin", "Referent", "Referentin", "Scientist", "Spezialist", "Specialist",
}  # fmt: skip

CONTACT_MARKERS = ("[phone]", "[email]")


@dataclass(frozen=True)
class Redacted:
    text: str
    emails: int
    phones: int
    links: int
    names: int


def redact(text: str) -> Redacted:
    text, emails = EMAIL.subn("[email]", text)
    text, links = LINK.subn("[link]", text)
    text, phones = _replace(PHONE, _phone, text)
    text, salutations = SALUTATION.subn(r"\1 [name]", text)
    text, contacts = _replace(CONTACT, _contact, text)
    text, lines = _name_lines(text)
    return Redacted(text, emails, phones, links, salutations + contacts + lines)


def _replace(pattern: re.Pattern[str], replace, text: str) -> tuple[str, int]:
    count = 0

    def counting(match: re.Match[str]) -> str:
        nonlocal count
        new = replace(match)
        count += new != match.group(0)
        return new

    return pattern.sub(counting, text), count


def _phone(match: re.Match[str]) -> str:
    digits = sum(char.isdigit() for char in match.group(0))
    return "[phone]" if 7 <= digits <= 16 else match.group(0)


def _contact(match: re.Match[str]) -> str:
    label, gap, name = match.groups()
    return match.group(0) if _looks_like_text(name) else f"{label}{gap}[name]"


def _looks_like_text(name: str) -> bool:
    return any(word in NOT_NAMES for word in re.findall(r"\w+", name))


def _name_lines(text: str) -> tuple[str, int]:
    """Replace lines that are only a name when a nearby line has a phone or email."""
    lines = text.split("\n")
    count = 0
    for i, line in enumerate(lines):
        match = NAME_LINE.fullmatch(line)
        if not match or _looks_like_text(match.group(1)):
            continue
        if any(marker in near for near in _neighbours(lines, i) for marker in CONTACT_MARKERS):
            lines[i] = "[name]"
            count += 1
    return "\n".join(lines), count


def _neighbours(lines: list[str], i: int, reach: int = 2) -> list[str]:
    """The closest non-empty lines above and below, `reach` on each side."""
    above = [line for line in reversed(lines[:i]) if line.strip()][:reach]
    below = [line for line in lines[i + 1 :] if line.strip()][:reach]
    return above + below
