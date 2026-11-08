// How the CV analysis works, in plain words. Numbers match src/skillradar/cv/match.py.
export function CvMethod() {
  return (
    <footer className="method cv-method">
      <h3>How the comparison works</h3>
      <p>
        <strong>Reading the CV.</strong> Claude reads the CV with the same skill list it uses for the postings, so both sides
        use the same names. A product the CV does not name is dropped (only general skills like &quot;ETL&quot; may come
        from a description), and skills the keyword search finds but Claude missed are added as &quot;only listed&quot;.
        Years of experience are counted from the job dates, by code, not by the model.
      </p>
      <p>
        <strong>A match.</strong> For each posting: <code>skills × language × seniority</code>. Skills is the covered part
        of the posting&apos;s skills; required skills weigh 1, nice-to-have skills 0.4. A skill counts 100% when used at work,
        80% in a project, 70% from a course and 60% when only listed, a little less when last used five or more years ago.
        A skill that proves another counts fully (AWS proves cloud computing); a similar skill counts partly, at most half
        (AWS for Azure), more when the two appear in the same kind of jobs. Language: 1 when you meet the level, 0.7 one
        level short, 0.4 two levels or more. Seniority: 1 at your level, 0.8 one step up, 0.9 one step down, less further
        away. Strong is 70% or more, good 50% or more, partial 30% or more.
      </p>
      <p>
        <strong>What to learn next.</strong> For each missing skill: if you learned it in a solid project (80%), how many
        postings would become at least a good match? Reaching fluent German or English is checked the same way. Postings
        that name fewer than three skills are not scored.
      </p>
      <p>
        <strong>Privacy.</strong> This page runs only on this computer. Before the text goes to Claude, email addresses,
        phone numbers, links and the name at the top are replaced. Nothing about the CV is saved; only the cost of the
        call is recorded for the monthly limit.
      </p>
    </footer>
  );
}
