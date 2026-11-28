/*
  transcript.js: read a GOLD transcript into the plan, entirely in the browser.

  Privacy: the file is read by JavaScript on the student's own computer
  (FileReader, then pdf.js for a PDF). It is never uploaded; there's no
  server to upload it to. It isn't stored either: only the courses and
  grades the student approves go into their plan (localStorage).

  pdf.js (Mozilla's PDF reader) is loaded from cdnjs the first time a PDF
  is opened. That downloads the library's code; nothing about the file is
  sent. Without internet (say, the one-file copy offline), pasting the
  transcript's text works the same way. See loadPdfJs for how the download
  is checked.

  How GOLD's "Unofficial Transcript - Printable Version" is laid out
  -----------------------------------------------------------------
    Fall 2018
    Course                     Grade EnrlCd Att Comp GPA  Points Additional Info
                                            Unit Unit Unit
    HIST 202 -HISTORICAL       A     27201  4.0  4.0  4.0 16.00
    METHODS
    HIST 295LA-WORKSHOP        A     60137  1.0  1.0  1.0  4.00
    LATIN AM
    Quarter Total (Grad)       GPA 4.00     13.0 13.0 13.0 52.00

  Things that matter for reading it:
    - Long titles wrap onto a second line, and the grade and numbers sit
      halfway between the two lines. In a PDF those are three separate lines
      of text, so a course is read as its first line plus every line after
      it, up to the next course, term or total.
    - A course starts with its subject and number, then a dash and the
      title: "HIST 202 -HISTORICAL", "HIST 295LA-WORKSHOP", "RG ST 251B -REL".
      Old subject codes no longer in the catalog still count.
    - The grade comes right before the 5-digit enrollment code (EnrlCd); the
      units are the first number after it (Att Unit). A course in progress
      has no grade yet.
    - Grades: A+ … F, P, NP; S and U (graduate Satisfactory/Unsatisfactory,
      read as P and NP); I (Incomplete, read as In Progress); W (Withdrawn)
      and courses marked "No Credit" are listed but left unticked.
  Pasted text (copied from GOLD's page) usually has each row on one line;
  the same rules read it.

  How UC San Diego's "Academic History" (TritonLink) is laid out
  ---------------------------------------------------------------
  (From a student-posted copy, printed to PDF; terms come newest first.)
    Term: Fall Qtr 2024
    Subject  Course  Course Title                    Units  Grade  Points  Repeat
    CHIN     10AN    First-Year Chinese I            5.00   A-     18.50
    DSC      180A    Data Science Project I          4.00   A      16.00
             Term Credits Passed: 9.00   Term GPA: 3.833
    ...
    Transfer Courses
    Subject Course Course Title        Units Grade Term Level UCSD Approx
    AP      BI3    Biology             8.00  P     SP19 LD    BILD 10
                   Advanced Placement Credit
    CISC    2      Fundamentals of Comp Sci I 6.00 A WI21 LD  CSE 8A
  Things that matter:
    - The columns after the title are units, grade (blank while in
      progress) and grade points, so they're read by position: "Chinese I"
      ends in a word that looks like a grade.
    - The term lines, the "Term Credits Passed / GPA / Honors / Academic
      Status" lines, "page 1 of 3" and the watermark letters a PDF scatters
      through the text all end a course and are skipped.
    - Transfer and AP courses count as credit for their UCSD equivalent
      (the last column), not as courses in a quarter. A row whose equivalent
      isn't a UCSD course (BILD APC, "no credit") is listed but unticked.

  Everything read is shown in a table to check and correct before it's used.
*/

/*
  pdf.js 4.10.38. Versions before 4.2.67 let a crafted PDF run JavaScript
  (CVE-2024-4367). Each file's SHA-384 hash is fixed here: if cdnjs ever
  served something else, the browser refuses it (Subresource Integrity).
  To upgrade: change the version, download both files, and put in their
  new hashes (openssl dgst -sha384 -binary FILE | openssl base64 -A).
*/
const PDFJS = {
  main: "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs",
  mainHash: "sha384-+0ti2moQlmLN7WZHE2RHIf5lV8hHxhxEalN0il3YZceG26fUPyOkR0hp9daxk1i7",
  worker: "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs",
  workerHash: "sha384-ToeVvShCxKc6CEvhHeMt0Q8A06pSPDbAlngO9nokrDmh914gk/pYd0N7D0a4Lz2o",
};
const GRADE_WORDS = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F", "P", "NP", "IP"];
// Grades on a transcript that the plan stores differently.
const GRADE_ALIASES = { S: "P", U: "NP", I: "IP", DR: "IP", NR: "IP" };
const TRANSCRIPT_GRADES = GRADE_WORDS.concat(Object.keys(GRADE_ALIASES), ["W"]);

const transcriptEl = {
  box: document.getElementById("transcript"),
  open: document.getElementById("plan-import"),
  file: document.getElementById("transcript-file"),
  text: document.getElementById("transcript-text"),
  read: document.getElementById("transcript-read"),
  status: document.getElementById("transcript-status"),
  review: document.getElementById("transcript-review"),
  apply: document.getElementById("transcript-apply"),
};

let transcriptRows = [];     // what was read: { code, title, term, units, grade, use }

// ===========================================================================
// 1. Getting the text
// ===========================================================================

/*
  pdf.js 4 comes only as a JavaScript module, and a module loaded with
  import() can't carry an integrity hash. So each file is downloaded with
  fetch(), which does check one, and then run from a local copy in memory
  (a "blob:" address). The main file sets window.pdfjsLib; the worker (the
  part that reads the PDF in the background) is pointed at its own copy.
*/
async function checkedCopy(url, hash) {
  const response = await fetch(url, { integrity: hash, mode: "cors", credentials: "omit" });
  if (!response.ok) throw new Error("pdf.js didn't load (" + response.status + ")");
  return URL.createObjectURL(new Blob([await response.text()], { type: "text/javascript" }));
}

let pdfJsLoading = null;
function loadPdfJs() {
  if (!pdfJsLoading) {
    pdfJsLoading = (async function () {
      const main = await checkedCopy(PDFJS.main, PDFJS.mainHash);
      await import(main);
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = await checkedCopy(PDFJS.worker, PDFJS.workerHash);
      return window.pdfjsLib;
    })();
    pdfJsLoading.catch(function () { pdfJsLoading = null; });     // let a later try start over
  }
  return pdfJsLoading;
}

/*
  A PDF stores text as separate pieces placed on the page, not as lines.
  To get lines back, pieces at the same height (y) are joined left to right.
*/
async function pdfText(file) {
  const pdfjs = await loadPdfJs();
  // isEvalSupported: false: never build code from what's in the PDF (the
  // CVE above came through that path; it's off as a second guard).
  const pdf = await pdfjs.getDocument({ data: await file.arrayBuffer(), isEvalSupported: false }).promise;
  const lines = [];
  for (let n = 1; n <= pdf.numPages; n++) {
    const page = await pdf.getPage(n);
    const content = await page.getTextContent();
    // UCLA's transcript is printed in two columns: read the left one down
    // the page, then the right one, so a line never mixes two terms.
    const columns = (campusDetails().transcript || {}).columns === 2 ? 2 : 1;
    const middle = page.getViewport({ scale: 1 }).width / 2;
    for (let column = 0; column < columns; column++) {
      const rows = {};
      for (const item of content.items) {
        if (!item.str.trim()) continue;
        if (columns === 2 && (item.transform[4] < middle) !== (column === 0)) continue;
        const y = Math.round(item.transform[5] / 2) * 2;     // within 2 points counts as the same line
        (rows[y] = rows[y] || []).push({ x: item.transform[4], text: item.str });
      }
      Object.keys(rows).map(Number).sort((a, b) => b - a).forEach(function (y) {
        lines.push(rows[y].sort((a, b) => a.x - b.x).map(p => p.text).join(" "));
      });
    }
  }
  return lines.join("\n");
}

// ===========================================================================
// 2. Reading terms and courses
// ===========================================================================

function parseTranscript(text) {
  const subjects = ((creditTable && creditTable.subjects) || []).slice().sort((a, b) => b.length - a.length);
  const rows = [];
  let term = null;
  let pending = null;      // the course being read: its first line plus what follows

  function finish() {
    if (!pending) return;
    const course = readCourse(pending.code, pending.text);
    course.term = pending.term;
    rows.push(course);
    pending = null;
  }

  let transfer = false;     // in UCSD's "Transfer Courses" section
  const ucla = (campusDetails().transcript || {}).format === "ucla";
  let columnTerms = [];     // UCLA, pasted with both columns on one line: each column's term

  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\s+/g, " ").trim();
    if (!line) continue;
    // A PDF's watermark ("Not Official Transcript") comes out as stray letters.
    if (line.length <= 2 || /^\**\s*(this is )?not (an )?official transcript/i.test(line)) continue;
    if (/^Transfer Courses\b/i.test(line)) {
      finish();
      transfer = true;
      continue;
    }
    if (transfer) {
      const credit = transferRow(line, subjects);
      if (credit) rows.push(credit);
      continue;
    }
    if (ucla) {
      // Two term headings on one line: the two columns' terms.
      const headings = Array.from(line.matchAll(TERM_HEADING));
      if (headings.length === 2) {
        columnTerms = headings.map(termOf);
        term = columnTerms[0];
        continue;
      }
      const found = uclaCourses(raw, subjects);
      if (found.length) {
        finish();
        found.forEach(function (course, i) {
          const right = columnTerms.length === 2 && (found.length === 2 ? i === 1 : course.at > raw.length / 2);
          course.term = right ? columnTerms[1] : (columnTerms.length === 2 ? columnTerms[0] : term);
          delete course.at;
          rows.push(course);
        });
        continue;
      }
    }
    const start = courseStart(line, subjects);
    if (start) {
      finish();
      pending = { code: start.code, text: start.rest, term: term };
      continue;
    }
    // "Fall 2018" (GOLD), "Term: Fall Qtr 2024" (UCSD), "summer sessions 2018" (UCLA).
    const termMatch = line.match(/^(?:Term:\s*)?(Fall|Winter|Spring|Summer)\b(?:\s+(?:Quarter|Qtr|Sessions?|Sess)\b)?(?:\s+(?:I{1,3}|1|2|3|Med\w*|Special))?\s+(\d{4})\b/i);
    if (termMatch && line.length < 60) {
      finish();
      term = termOf(termMatch);
      columnTerms = [];
      continue;
    }
    // Totals, column headings and page headers end a course.
    if (/^(Quarter Total|Cumulative Total|Term Total|Course\b|Unit\b|Dean'?s|University of California|https?:|\d{1,2}\/\d{1,2}\/\d{2,4}|Term (Credits|GPA|Grade|Honors)|Academic (Status|History)|Subject\b|page \d+ of \d+|Transfer Credit|Entity Name|Cumulative Summary|Create Date|General Information|All credits|UCSD Undergraduate)/i.test(line)) {
      finish();
      continue;
    }
    if (pending) pending.text += " " + line;
  }
  finish();

  /*
    A course taken more than once: every attempt is listed. The latest one
    that counts is used ("repeated: F replaced by B"); earlier ones stay in
    the table, unticked, so nothing disappears without explanation. The
    plan keeps one grade per course, so only one attempt can be applied.
  */
  const attempts = {};
  for (const row of rows) (attempts[row.code] = attempts[row.code] || []).push(row);
  for (const code of Object.keys(attempts)) {
    const list = attempts[code];
    if (list.length < 2) continue;
    const kept = list.slice().reverse().find(r => r.use) || list[list.length - 1];
    const others = list.filter(r => r !== kept);
    for (const r of others) {
      r.use = false;
      r.note = (r.note ? r.note + "; " : "") + "earlier attempt, replaced by " + (kept.grade === "IP" ? "the current one" : kept.grade);
    }
    kept.note = (kept.note ? kept.note + "; " : "") + "repeated: " + others.map(r => r.grade === "IP" ? "no grade" : r.grade).join(", ") +
                " replaced by " + (kept.grade === "IP" ? "In Progress" : kept.grade);
  }
  return rows;
}

/*
  Does this line start a course? Two forms:
    GOLD's:  "HIST 202 -HISTORICAL", "HIST 295LA-WORKSHOP" (a dash after the
             number). Any subject made of capital letters counts, since old
             transcripts can have subject codes the catalog has since dropped.
    plain:   "ECE 15A Fund of Logic Design 4.0 A-" (no dash). Only a real
             catalog subject counts, so ordinary text isn't mistaken for one.
*/
function courseStart(line, subjects) {
  const gold = line.match(/^([A-Z][A-Z&]*(?: [A-Z&]+){0,2}) (\d{1,3}[A-Z]{0,4}) ?-(.*)$/);
  if (gold) return { code: gold[1] + " " + gold[2], rest: gold[3] };
  const upper = line.toUpperCase();
  const subject = subjects.find(s => upper.startsWith(s + " "));
  if (!subject) return null;
  const number = line.slice(subject.length).trim().match(/^(\d{1,3}[A-Z]{0,4})\b(.*)$/i);
  if (!number) return null;
  return { code: subject + " " + number[1].toUpperCase(), rest: number[2] };
}

const TERM_HEADING = /\b(Fall|Winter|Spring|Summer)(?:\s+(?:Quarter|Qtr|Sessions?))?\s+(\d{4})\b/gi;

function termOf(match) {
  return { quarter: match[1][0].toUpperCase() + match[1].slice(1).toLowerCase(), year: Number(match[2]) };
}

/*
  UCLA's transcript lines: an abbreviated title, then the course, units,
  grade points earned and the grade:
    "MACHINE LEARNING      COM SCI M146  4.0   14.8   A-"
    "ELECTRODYNMC&OPTICS   PHYSICS 1C    5.0    0.0   I"
  (from a real transcript, 2021 format). Pasted from a two-column PDF, a
  line can hold two of them, so every match is returned, with where it
  starts (`at`).
*/
function uclaCourses(line, subjects) {
  const found = [];
  // Title and subject together, then number, units, points, grade.
  const pattern = /(\S(?:.*?\S)?)\s+([A-Z]{0,2}\d{1,3}[A-Z]{0,3})\s+(\d{1,2}\.\d)\s+(\d{1,3}\.\d)\s+([A-Z][A-Z+\-]?)(?=\s|$)/g;
  for (const m of line.matchAll(pattern)) {
    const before = m[1].replace(/\s+/g, " ");
    // The subject is the longest code the words before the number end with
    // ("… MACHINE LEARNING COM SCI" -> COM SCI; subjects are longest first).
    const subject = subjects.find(s => before === s || before.endsWith(" " + s));
    if (!subject) continue;
    let grade = m[5].toUpperCase();
    if (!TRANSCRIPT_GRADES.concat(["DR", "NR"]).includes(grade)) continue;
    const withdrawn = grade === "W";
    if (GRADE_ALIASES[grade]) grade = GRADE_ALIASES[grade];
    // With two columns on one line, the title is only the words after the
    // gap (the raw line keeps the spacing).
    const title = before.slice(0, before.length - subject.length).trim();
    found.push({ code: subject + " " + m[2], title: title, units: Number(m[3]), grade: withdrawn ? "IP" : grade,
                 use: !withdrawn, note: withdrawn ? "withdrawn" : "", at: m.index });
  }
  return found;
}

/*
  One row of UCSD's "Transfer Courses": the course at the other school (or
  the AP exam), then units, grade, term ("WI21"), level, and the UCSD course
  it counts as. Becomes credit for that UCSD course.
*/
function transferRow(line, subjects) {
  const match = line.match(/^(\S+)\s+(\S+)\s+(.*?)\s+(\d+\.\d\d)\s+(?:(\S{1,2})\s+)?(FA|WI|SP|S[123U]|SU)\d{2}\s+(?:LD|UD)\b\s*(.*)$/i);
  if (!match) return null;
  const from = match[1].toUpperCase() === "AP" ? "AP " + match[3] : match[1] + " " + match[2];
  const equivalent = match[7].trim().toUpperCase().replace(/\s+/g, " ");
  const subject = subjects.find(s => equivalent.startsWith(s + " "));
  const real = subject && /^\d{1,3}[A-Z]{0,4}$/.test(equivalent.slice(subject.length + 1));
  return {
    code: real ? equivalent : (equivalent || "—"), title: from, term: null, transfer: true,
    units: Number(match[4]), grade: null, use: Boolean(real),
    note: real ? (match[1].toUpperCase() === "AP" ? "AP credit" : "transfer credit") : "no matching UCSD course",
  };
}

// Grade, units and title from a course's text (everything after its code).
function readCourse(code, text) {
  const words = text.trim().split(" ").filter(Boolean);
  let grade = null;
  let units = null;
  // UCSD's columns: title, units, [grade], points, [repeat], read from the right.
  const ucsd = text.trim().match(/^(.*?)\s*(\d+\.\d\d)\s+(?:(\S{1,2})\s+)?(\d+\.\d\d)(?:\s+(\S+))?$/);
  if (ucsd && (!ucsd[3] || TRANSCRIPT_GRADES.includes(ucsd[3].toUpperCase()))) {
    let ucsdGrade = (ucsd[3] || "IP").toUpperCase();
    const withdrawn = ucsdGrade === "W";
    const repeated = Boolean(ucsd[5]);
    if (GRADE_ALIASES[ucsdGrade]) ucsdGrade = GRADE_ALIASES[ucsdGrade];
    return { code: code, title: ucsd[1].trim(), units: Number(ucsd[2]), grade: withdrawn ? "IP" : ucsdGrade,
             use: !withdrawn, note: withdrawn ? "withdrawn" : repeated ? "marked repeated" : "" };
  }
  const numbersAt = words.findIndex(w => /^\d{5}$/.test(w));       // the EnrlCd

  if (numbersAt >= 0) {
    // GOLD's columns: [grade] EnrlCd AttUnit CompUnit GPAUnit Points
    const before = (words[numbersAt - 1] || "").toUpperCase();
    if (TRANSCRIPT_GRADES.includes(before)) grade = before;
    const att = Number(words[numbersAt + 1]);
    if (!isNaN(att)) units = att;
  } else {
    // Plain text: the last grade-like word, and the first sensible number.
    for (const word of words) {
      if (TRANSCRIPT_GRADES.includes(word.toUpperCase())) grade = word.toUpperCase();
      const value = Number(word);
      if (units === null && /^\d+(\.\d+)?$/.test(word) && value >= 0.5 && value <= 12) units = value;
    }
  }
  if (/in progress/i.test(text)) grade = "IP";

  // The title: the words that aren't the grade, numbers or the notes column.
  const title = words.filter(function (w, i) {
    if (numbersAt >= 0 && (i === numbersAt - 1 && grade) ) return false;
    if (/^\d+(\.\d+)?$/.test(w)) return false;
    return numbersAt < 0 ? !TRANSCRIPT_GRADES.includes(w.toUpperCase()) : true;
  }).join(" ").replace(/\b(No Credit|Honors|Repeated|In Progress)\b/gi, "").replace(/\s+/g, " ").trim();

  const noCredit = /no credit/i.test(text);
  let use = !noCredit && grade !== "W";
  let note = noCredit ? "no credit" : grade === "W" ? "withdrawn" : "";
  if (grade === "W") grade = null;
  if (grade && GRADE_ALIASES[grade]) grade = GRADE_ALIASES[grade];
  return { code: code, title: title, units: units, grade: grade || "IP", use: use, note: note };
}

// ===========================================================================
// 3. Checking what was read, then using it
// ===========================================================================

function termName(term) {
  return term ? term.quarter + " " + term.year : "term not found";
}

function showReview() {
  if (!transcriptRows.length) {
    transcriptEl.review.innerHTML = '<p class="flag">No courses found. If this is a PDF, try copying its text and pasting it instead.</p>';
    transcriptEl.apply.hidden = true;
    return;
  }
  const gradeOptions = g => ["", ...GRADE_WORDS].map(x =>
    '<option value="' + x + '"' + (x === g ? " selected" : "") + ">" + (x === "IP" ? "In Progress" : x || "—") + "</option>").join("");
  transcriptEl.review.innerHTML = '<p class="note">' + transcriptRows.length +
    " courses read. Check them, fix anything wrong, untick any to leave out, then apply.</p>" +
    '<table class="review-table"><thead><tr><th>Use</th><th>Course</th><th>Term</th><th>Units</th><th>Grade</th></tr></thead><tbody>' +
    transcriptRows.map((r, i) =>
      '<tr><td><input type="checkbox" data-row="' + i + '" data-field="use"' + (r.use ? " checked" : "") + "></td>" +
      "<td><strong>" + escapeHtml(r.code) + '</strong> <span class="note">' + escapeHtml(r.title) +
      (r.note ? " (" + escapeHtml(r.note) + ")" : "") + "</span></td>" +
      "<td>" + escapeHtml(r.transfer ? "credit" : termName(r.term)) + "</td>" +
      '<td><input type="number" step="0.5" min="0" max="12" data-row="' + i + '" data-field="units" value="' + (r.units === null ? "" : r.units) + '"></td>' +
      '<td><select data-row="' + i + '" data-field="grade">' + gradeOptions(r.grade) + "</select></td></tr>").join("") +
    "</tbody></table>";
  transcriptEl.apply.hidden = false;
}

transcriptEl.review.addEventListener("change", function (event) {
  const row = transcriptRows[Number(event.target.dataset.row)];
  if (!row) return;
  const field = event.target.dataset.field;
  if (field === "use") row.use = event.target.checked;
  if (field === "units") row.units = event.target.value === "" ? null : Number(event.target.value);
  if (field === "grade") row.grade = event.target.value || null;
});

// The plan quarter for a term: Fall 2026 is year 1 if the plan starts in
// Fall 2026; Winter and Spring 2027 are year 1 too.
function slotForTerm(term) {
  const academicYear = term.quarter === "Fall" ? term.year : term.year - 1;
  const year = academicYear - plan.startYear + plan.firstYear;
  const q = { Fall: "F", Winter: "W", Spring: "S", Summer: "U" }[term.quarter];
  return { year: year, id: year + "-" + q };
}

function applyTranscript() {
  const credits = transcriptRows.filter(r => r.use && r.transfer && r.code);
  const rows = transcriptRows.filter(r => r.use && r.term && !r.transfer);
  if (!rows.length && !credits.length) return;
  // AP and transfer courses (UCSD's Academic History lists them) become credit.
  for (const r of credits) if (!credit.transfer.includes(r.code)) credit.transfer.push(r.code);
  if (!rows.length) {
    transcriptRows = [];
    transcriptEl.box.close();
    say(credits.length + " transfer and AP courses are now in your credit.");
    creditUpdated();
    return;
  }
  // Start the plan at the first term on the transcript, if that's earlier.
  const firstAcademic = Math.min(...rows.map(r => (r.term.quarter === "Fall" ? r.term.year : r.term.year - 1)));
  if (firstAcademic < plan.startYear || Object.keys(plan.placed).length === 0) {
    const shift = plan.startYear - firstAcademic;
    for (const code of Object.keys(plan.placed)) {
      const [year, q] = plan.placed[code].split("-");
      plan.placed[code] = (Number(year) + shift) + "-" + q;
    }
    for (const e of plan.electives || []) {
      const [year, q] = e.slot.split("-");
      e.slot = (Number(year) + shift) + "-" + q;
    }
    plan.startYear = firstAcademic;
  }
  plan.info = plan.info || {};
  for (const r of rows) {
    const slot = slotForTerm(r.term);
    while (slot.year > plan.firstYear + plan.years - 1 && plan.years < MAX_YEARS) plan.years += 1;
    if (r.term.quarter === "Summer") plan.summer = true;
    plan.placed[r.code] = slot.id;
    if (r.grade) plan.grades[r.code] = r.grade; else delete plan.grades[r.code];
    if (r.units !== null) plan.units[r.code] = r.units;
    // A course outside the programs on screen has no catalog details here,
    // so its units come from the transcript (what the student actually took).
    const node = nodesById[r.code];
    plan.info[r.code] = node
      ? { title: node.title, units: node.units, offered: node.offered || [] }
      : { title: r.title, units: String(r.units === null ? 4 : r.units), offered: [] };
  }
  for (const r of rows) delete (plan.auto || {})[r.code];
  pruneCovered();
  rebuildAfterTranscript(new Set(rows.map(r => r.code)));
  transcriptRows = [];
  transcriptEl.box.close();
  say(rows.length + " courses from your transcript are in your plan, with their grades" +
      (credits.length ? ", and " + credits.length + " transfer and AP courses are in your credit" : "") +
      ". The rest of your plan now starts after them.");
  if (credits.length) creditUpdated();
  planChanged();
  if (graph) draw();
}

// ===========================================================================
// 4. The box
// ===========================================================================

transcriptEl.open.addEventListener("click", function () {
  transcriptEl.status.textContent = "";
  transcriptEl.review.innerHTML = "";
  transcriptEl.apply.hidden = true;
  transcriptEl.box.showModal();
});

transcriptEl.read.addEventListener("click", async function () {
  transcriptEl.status.textContent = "Reading…";
  try {
    let text = transcriptEl.text.value;
    const file = transcriptEl.file.files[0];
    if (!text.trim() && file) {
      text = /\.pdf$/i.test(file.name) || file.type === "application/pdf" ? await pdfText(file) : await file.text();
    }
    transcriptRows = parseTranscript(text);
    transcriptEl.status.textContent = "";
    showReview();
  } catch (error) {
    transcriptEl.status.textContent = "Couldn't read that file (" + error.message + "). Try pasting its text instead.";
  }
});

transcriptEl.apply.addEventListener("click", applyTranscript);
transcriptEl.box.addEventListener("click", function (event) {
  if (event.target === transcriptEl.box) transcriptEl.box.close();
});
