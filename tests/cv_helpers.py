"""Shared pieces for the CV analysis tests: PDFs, a fake Claude and small markets."""

import json
from types import SimpleNamespace as NS

import duckdb

from skillradar.cv.market import Market, Posting, PostingSkill
from skillradar.cv.similarity import Similarity
from skillradar.transform.runner import serve_dir

CV_TEXT = """Lena Example
Data Engineer, Berlin
lena@example.org, +49 151 23456789

EXPERIENCE
Data Engineer, Example GmbH, 05/2024 - present
Built pipelines with Python, SQL and Airflow on AWS. Data modeling for the warehouse.

Working Student, Example GmbH, 10/2022 - 04/2024
SQL reports in Excel.

SKILLS
Python, SQL, Airflow, AWS, Docker, Kafka

LANGUAGES
German native, English fluent
"""

ANSWER = {
    "headline": "Data Engineer",
    "role": "data_engineer",
    "seniority": "mid",
    "jobs": [
        {
            "title": "Data Engineer",
            "start": "2024-05",
            "end": "present",
            "kind": "job",
            "tech": True,
        },
        {
            "title": "Working Student",
            "start": "2022-10",
            "end": "2024-04",
            "kind": "working_student",
            "tech": True,
        },
    ],
    "languages": [
        {"language": "Deutsch", "level": "native"},
        {"language": "English", "level": "fluent"},
    ],
    "skills": [
        {"name": "python", "evidence": "work", "years": 2.5, "last_used": 2026, "context": "x"},
        {"name": "SQL", "evidence": "work", "years": 4, "last_used": 2026, "context": ""},
        {"name": "Airflow", "evidence": "work", "years": None, "last_used": None, "context": ""},
        {
            "name": "Data Modeling",
            "evidence": "work",
            "years": 99,
            "last_used": 2031,
            "context": "",
        },
        {"name": "Snowflake", "evidence": "work", "years": 1, "last_used": 2025, "context": ""},
        {"name": "Python", "evidence": "listed", "years": 3, "last_used": 2024, "context": ""},
    ],
}


def message(answer=None, stop_reason="end_turn", text=None):
    body = text if text is not None else json.dumps(answer or ANSWER)
    usage = NS(input_tokens=6000, output_tokens=1500, cache_read_input_tokens=0)
    return NS(stop_reason=stop_reason, content=[NS(type="text", text=body)], usage=usage)


class FakeMessages:
    def __init__(self, reply):
        self.reply = reply
        self.sent = []

    def create(self, **params):
        self.sent.append(params)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class FakeClient:
    def __init__(self, reply=None):
        self.messages = FakeMessages(reply if reply is not None else message())


def make_pdf(pages: list[str]) -> bytes:
    """A small valid PDF with one text page per entry (ASCII text)."""
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    for i, text in enumerate(pages):
        page, content = 4 + 2 * i, 5 + 2 * i
        ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
        for line in text.split("\n"):
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({safe}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objects[content] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        objects[page] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content} 0 R >>"
        ).encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    xref = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for number in range(1, size):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def posting(
    refnr,
    skills,
    role="data_engineer",
    regions=("BERLIN",),
    seniority="mid",
    german="not asked",
    english="not asked",
    published="2026-11-01",
):
    """skills: names, a trailing "?" marks nice to have."""
    return Posting(
        refnr=refnr,
        title=f"Job {refnr}",
        employer="Example",
        city="Berlin",
        published=published,
        role=role,
        seniority=seniority,
        remote="hybrid",
        german=german,
        english=english,
        regions=frozenset(regions),
        skills=tuple(PostingSkill(s.rstrip("?"), not s.endswith("?")) for s in skills),
    )


def market(postings, min_postings=1):
    sim = Similarity((p.skill_names() for p in postings), min_postings=min_postings)
    return Market("2026-11-08", tuple(postings), sim)


def write_market(data_dir):
    """Gold files for three scored postings and one with too few skills."""
    folder = serve_dir(data_dir)
    folder.mkdir(parents=True)
    with duckdb.connect() as con:
        con.execute(
            "create table gold_meta as select date '2026-11-08' as as_of, 4 as tech_postings"
        )
        con.execute(
            "create table gold_postings as select * from (values "
            "('p1', 'Data Engineer', 'A', 'Berlin', date '2026-11-05', 'data_engineer', 'mid', "
            "'hybrid', 'fluent', 'not asked'), "
            "('p2', 'Data Engineer', 'B', 'Berlin', date '2026-11-06', 'data_engineer', "
            "'senior', 'remote', 'not asked', 'good'), "
            "('p3', 'Backend Dev', 'C', 'München', null, 'backend_developer', 'junior', "
            "'onsite', 'good', 'not asked'), "
            "('p4', 'IT Job', 'D', 'Wien', date '2026-11-01', 'other_tech', 'mid', 'unknown', "
            "'not asked', 'not asked')"
            ") t(refnr, title, employer, city, first_published, role, seniority, remote, "
            "german, english)"
        )
        con.execute(
            "create table gold_posting_skills as select * from (values "
            "('p1', 'SQL', true), ('p1', 'Python', true), ('p1', 'Airflow', false), "
            "('p2', 'Python', true), ('p2', 'Spark', true), ('p2', 'Azure', true), "
            "('p2', 'Golang', false), ('p2', 'Go', true), "
            "('p3', 'Java', true), ('p3', 'Spring', true), ('p3', 'PostgreSQL', false), "
            "('p4', 'Excel', true)"
            ") t(refnr, skill, required)"
        )
        con.execute(
            "create table gold_scope as select * from (values "
            "('p1', 'data_engineer', 'BERLIN'), ('p1', 'data_engineer', 'all'), "
            "('p2', 'data_engineer', 'BERLIN'), ('p2', 'data_engineer', 'all'), "
            "('p3', 'backend_developer', 'BAYERN'), ('p3', 'backend_developer', 'all'), "
            "('p4', 'other_tech', 'all')"
            ") t(refnr, role, region)"
        )
        for name in ("gold_meta", "gold_postings", "gold_posting_skills", "gold_scope"):
            con.execute(f"copy {name} to '{folder / name}.parquet' (format parquet)")
