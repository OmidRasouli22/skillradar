"""Remove personal data from posting texts: emails, phone numbers, links and contact names.

Uses rules, not a name model. A name model would also remove skills like "Kafka".
"""

import re
from dataclasses import dataclass
from functools import cache

from skillradar.skills.taxonomy import load_taxonomy

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
BULLET = re.compile(r"[ \t]*[*\-•][ \t]")
MARKER = re.compile(r"\[(?:phone|email)\]")
# "melde dich bei Melina Jacobs (Recruiting) Telefon: [phone]": a first and last name in
# running text, at most this many characters before a phone or email, same paragraph.
NEAR_MARKER = 150
NAME_IN_TEXT = re.compile(rf"(?<![\w-]){FIRST_AND_LAST}(?!\w)")
BLANK_LINE = re.compile(r"\n[ \t]*\n")
# Running text has many capitalised nouns next to names: "Vergütung Marko Martinovic",
# "Luisa Thiele Teamleitung". These words and endings are trimmed from a match.
NOT_NAMES_IN_TEXT = {
    "Angabe", "Basis", "Bewirb", "Dein", "Deine", "Deinem", "Deinen", "Deiner", "Deines",
    "Dich", "Dir", "Euch", "Euer", "Eure", "Ihnen", "Ihrem", "Ihren", "Ihrer", "Ihres",
    "Kein", "Keine", "Starte", "Stelle", "Weitere", "Zum", "Zur",
}  # fmt: skip
NOUN_ENDINGS = (
    "ung", "ungen", "heit", "keit", "schaft", "tät", "ion", "ionen", "nis", "isse",
    "ment", "ence", "ance", "ing", "ity", "ness", "ship", "ions", "ems", "ces",
)  # fmt: skip
# Surnames have these endings too (Hornung, Kuckling), so after a first name only long
# words count as nouns.
LONG_NOUN = 10


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
    text, near = _names_near_markers(text)
    return Redacted(text, emails, phones, links, salutations + contacts + lines + near)


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
        if not match or _looks_like_text(match.group(1)) or _has_skill(match.group(1)):
            continue
        if BULLET.match(line):
            continue  # "* Globales Netzwerk" is a list item, not a name
        if any(marker in near for near in _neighbours(lines, i) for marker in CONTACT_MARKERS):
            lines[i] = "[name]"
            count += 1
    return "\n".join(lines), count


def _neighbours(lines: list[str], i: int, reach: int = 4) -> list[str]:
    """The closest non-empty lines above and below, `reach` on each side."""
    above = [line for line in reversed(lines[:i]) if line.strip()][:reach]
    below = [line for line in lines[i + 1 :] if line.strip()][:reach]
    return above + below


def _names_near_markers(text: str) -> tuple[str, int]:
    """Replace names in running text shortly before [phone] or [email]."""
    spans = set()
    for marker in MARKER.finditer(text):
        start = max(0, marker.start() - NEAR_MARKER)
        blanks = list(BLANK_LINE.finditer(text, start, marker.start()))
        if blanks:
            start = blanks[-1].end()
        pos = start
        while match := NAME_IN_TEXT.search(text, pos, marker.start()):
            first = _after_nouns(match)
            if first > match.start():
                # "Unsere Recruiterin Svenja Hofmann": match again without "Unsere",
                # so the match can reach the last name
                pos = first
                continue
            span = _name_span(match)
            if span:
                spans.add(span)
            pos = match.end()
    merged = _merge(spans)
    for begin, end in reversed(merged):
        text = text[:begin] + "[name]" + text[end:]
    return text, len(merged)


def _after_nouns(match: re.Match[str]) -> int:
    """Where the match starts once nouns at its start are skipped."""
    for word in re.finditer(r"\S+", match.group(0)):
        if not _is_noun(word.group(0), after_name=False):
            return match.start() + word.start()
    return match.end()


def _name_span(match: re.Match[str]) -> tuple[int, int] | None:
    """Where the name is in the match, without nouns at its end. None if no name."""
    words = list(re.finditer(r"\S+", match.group(0)))
    while words and _is_noun(words[-1].group(0), after_name=True):
        words.pop()
    if any(_is_noun(w.group(0), after_name=True) for w in words):
        return None
    if sum(bool(re.fullmatch(NAME_WORD, w.group(0))) for w in words) < 2:
        return None
    begin, end = match.start() + words[0].start(), match.start() + words[-1].end()
    return None if _has_skill(match.string[begin:end]) else (begin, end)


def _is_noun(word: str, after_name: bool) -> bool:
    if word in NOT_NAMES or word in NOT_NAMES_IN_TEXT:
        return True
    if word.endswith(NOUN_ENDINGS):
        # "Meier-Anding": only the last part of a double name counts
        return not after_name or len(word.split("-")[-1]) >= LONG_NOUN
    return False


def _merge(spans: set[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for begin, end in sorted(spans):
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((begin, end))
    return merged


@cache
def _has_skill(words: str) -> bool:
    """Skills like "Apache Kafka" look like names, so they stay."""
    return bool(_skills().find_in_text(words))


@cache
def _skills():
    return load_taxonomy()
