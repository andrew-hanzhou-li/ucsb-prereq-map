/*
  transcript.js: read a GOLD transcript into the plan, entirely in the browser.

  Privacy: the file is read by JavaScript on the student's own computer
  (FileReader, then pdf.js for a PDF). It is never uploaded; there's no
  server to upload it to. It isn't stored either: only the courses and
  grades the student approves go into their plan (localStorage).

  pdf.js (Mozilla's PDF reader) is loaded from cdnjs the first time a PDF
  is opened. That downloads the library's code; nothing about the file is
  sent. Without internet (say, the one-file copy offline), pasting the
  transcript's text works the same way.

  How the text is read
  --------------------
  A transcript lists terms ("Fall 2025") with the courses under each. So:
    1. a line naming a quarter and year starts a new term;
    2. a line starting with a real UCSB subject code and a course number
       ("ECE 15A", "ENV S 1") is a course. On that line, the last grade-like
       word (A+ … F, P, NP, IP) is the grade, and the first number from 0.5
       to 12 after the title is the units. No grade, or the words "in
       progress", means In Progress.
  This hasn't been tuned against a real GOLD transcript yet, which is why
  everything read is shown in a table to check and correct before it's used.
*/

const PDFJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
const PDFJS_WORKER = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
const GRADE_WORDS = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F", "P", "NP", "IP"];

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

function loadPdfJs() {
  if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
  return new Promise(function (resolve, reject) {
    const script = document.createElement("script");
    script.src = PDFJS_URL;
    script.onload = function () {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
      resolve(window.pdfjsLib);
    };
    script.onerror = () => reject(new Error("pdf.js didn't load"));
    document.head.appendChild(script);
  });
}

/*
  A PDF stores text as separate pieces placed on the page, not as lines.
  To get lines back, pieces at the same height (y) are joined left to right.
*/
async function pdfText(file) {
  const pdfjs = await loadPdfJs();
  const pdf = await pdfjs.getDocument({ data: await file.arrayBuffer() }).promise;
  const lines = [];
  for (let n = 1; n <= pdf.numPages; n++) {
    const page = await pdf.getPage(n);
    const content = await page.getTextContent();
    const rows = {};
    for (const item of content.items) {
      if (!item.str.trim()) continue;
      const y = Math.round(item.transform[5] / 2) * 2;     // within 2 points counts as the same line
      (rows[y] = rows[y] || []).push({ x: item.transform[4], text: item.str });
    }
    Object.keys(rows).map(Number).sort((a, b) => b - a).forEach(function (y) {
      lines.push(rows[y].sort((a, b) => a.x - b.x).map(p => p.text).join(" "));
    });
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
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\s+/g, " ").trim();
    if (!line) continue;
    const termMatch = line.match(/\b(Fall|Winter|Spring|Summer)\b(?:\s+(?:Quarter|Session))?\s+(\d{4})\b/i);
    const course = readCourseLine(line, subjects);
    if (!course && termMatch) {
      term = { quarter: termMatch[1][0].toUpperCase() + termMatch[1].slice(1).toLowerCase(), year: Number(termMatch[2]) };
      continue;
    }
    if (course) {
      course.term = term;
      rows.push(course);
    }
  }
  // A course taken twice: keep the latest attempt.
  const latest = {};
  for (const row of rows) latest[row.code] = row;
  return Object.values(latest).map(r => Object.assign(r, { use: true }));
}

// "ECE 15A FUND LOGIC DESIGN 4.0 A- 14.8" -> { code, title, units, grade }
function readCourseLine(line, subjects) {
  const upper = line.toUpperCase();
  const subject = subjects.find(s => upper.startsWith(s + " "));
  if (!subject) return null;
  const rest = line.slice(subject.length).trim();
  const number = rest.match(/^(\d{1,3}[A-Z]{0,4})\b(.*)$/i);
  if (!number) return null;
  const code = subject + " " + number[1].toUpperCase();
  const words = number[2].trim().split(" ");

  let grade = null;
  for (const word of words) {
    if (GRADE_WORDS.includes(word.toUpperCase())) grade = word.toUpperCase();
  }
  if (/in progress/i.test(line)) grade = "IP";

  let units = null;
  const titleWords = [];
  for (const word of words) {
    const value = Number(word);
    if (units === null && /^\d+(\.\d+)?$/.test(word) && value >= 0.5 && value <= 12) {
      units = value;
    } else if (units === null && !GRADE_WORDS.includes(word.toUpperCase())) {
      titleWords.push(word);
    }
  }
  return { code: code, title: titleWords.join(" "), units: units, grade: grade || "IP" };
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
      "<td><strong>" + escapeHtml(r.code) + '</strong> <span class="note">' + escapeHtml(r.title) + "</span></td>" +
      "<td>" + escapeHtml(termName(r.term)) + "</td>" +
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
  const rows = transcriptRows.filter(r => r.use && r.term);
  if (!rows.length) return;
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
    const info = courseInfo(r.code);
    plan.info[r.code] = { title: info.title || r.title, units: info.units || String(r.units || 4), offered: info.offered };
  }
  transcriptRows = [];
  transcriptEl.box.close();
  say(rows.length + " courses from your transcript are in your plan, with their grades.");
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
