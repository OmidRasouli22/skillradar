# Labeling guide

How to write the correct answer for a posting in `labels.jsonl`. The rules are the same
as in the extraction prompt (`src/skillradar/extract/prompt.py`), so the evaluation
measures how well Claude follows them. Where the prompt leaves a case open, the rule
below says how it was decided; these clarifications are marked *(guide)*. When a rule
here and the prompt disagree, fix one of them and note it in the commit.

Label what the posting says, not what the job probably needs. Don't look at Claude's
answer while labeling; the review page never shows it.

## Role

The one role that fits the main work. The role list and its short descriptions are on
the review page. If two fit, take the one the title names.

- `not_tech` for jobs that are not IT, software or data work, even if they mention an IT
  tool (a warehouse worker who uses SAP is `not_tech`).
- *(guide)* Hardware, electronics, physics, power systems and lab work are `not_tech`
  unless the main work is programming. Firmware and PLC programming are
  `embedded_engineer`.
- *(guide)* Teaching an IT subject is `other_tech`; teaching anything else is `not_tech`.

## Seniority

Check in this order and take the first that fits:

1. `student`: Werkstudent, internship, thesis, apprenticeship, duales Studium
2. `lead`: team lead, head of, principal, chief
3. `senior`: Senior in the title, langjährige Erfahrung, or 5 or more years
4. `junior`: entry level, Berufseinsteiger, Absolvent, PhD position, "erste
   Berufserfahrung", or at most 3 years
5. `mid`: every other professional job
6. `unknown`: only when it is not a normal job offer, e.g. a talent pool

*(guide)* "At most 3 years" means the posting asks for 3 years or less, however it is
written: "mindestens 2 Jahre" and "2-3 Jahre" are junior, "3-4 Jahre" is mid.

## Home office

`remote` (fully from home possible), `hybrid` (some home office, also "nach Absprache"
or "mobiles Arbeiten"), `onsite` (the posting says on site, without home office),
`unknown` (not mentioned). Home office named only among the benefits still counts.

## Languages

Only languages the posting asks for, with the level: native, fluent (verhandlungssicher,
fließend, sehr gut, C1, C2), good (gut, B2), basic (A1 to B1), unknown (asked for, no
level). A posting written in German does not ask for German by itself. A language that
is only a plus is left out. *(guide)* When a posting gives a word and a level that
disagree ("sehr gut (B2)"), the level wins.

## Skills

Technical skills the candidate should have: programming languages, frameworks, tools,
platforms, databases, cloud services and technical methods.

- Not soft skills, degrees, human languages or benefits.
- Use the name from `config/skills.yaml` when the skill is in the list (the review page
  suggests these names). Otherwise the usual name.
- Only skills written in the posting, including its title. Never add one the posting
  doesn't name.
- Examples count: "Kenntnisse in X (z. B. Y oder Z)" gives X, Y and Z.
- A general word is not a product: "Cloud" is Cloud Computing, not AWS; "Container" is
  not Docker; "Datenbank" is not PostgreSQL. *(guide)* The other way round, a product
  does not add its general skill: "AWS" alone does not add Cloud Computing.
- *(guide)* A skill named in the tasks counts. A tool named only in the text about the
  company, in a "our tech stack" list, or in search keywords ("Schlagworte") does not.
- *(guide)* Interfaces in general are "APIs"; use REST, GraphQL or OData only when the
  posting names them.

### Required or nice to have

- Required: expected (Anforderungen, Profil, setzen voraus, sehr gute Kenntnisse), or
  named in the tasks.
- Nice to have: wünschenswert, von Vorteil, idealerweise, nice to have, "kein Muss", or
  only an interest ("Interesse an KI").
- *(guide)* When the profile calls a skill a plus, it is nice to have even if the tasks
  name it.
- *(guide)* A soft heading over the whole profile ("Idealerweise bringst du mit") does not
  make every skill a plus; only skills the posting singles out are.
- *(guide)* "Vorzugsweise" or "ideally" that picks one option of a required group
  ("Cloud-Erfahrung, vorzugsweise GCP") leaves the options required.

## Status

- `draft`: a first label written by a model. It does not count in the report.
- `verified`: you read the posting and the label is right. Fix anything that is wrong
  before you press "Verify".

Write a note when a case was hard to decide, so the rules can be made clearer.
