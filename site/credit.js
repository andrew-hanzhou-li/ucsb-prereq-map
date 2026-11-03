/*
  credit.js: the "Credit you already have" box.

  Two kinds of credit (stored in student.js):
    AP exams     pick an exam's score; the catalog's AP chart says which
                 UCSB courses that score counts as.
    College      dual enrollment, community college or another university.
                 We don't list other schools' courses. The student ticks the
                 UCSB course each one counts as ("I have credit for CMPSC 40").
                 ASSIST.org is the official source for California community
                 colleges' equivalents.

  Whatever's entered counts as done everywhere: prerequisites on the map,
  "next" marks, and the planner.
*/

const creditEl = {
  box: document.getElementById("credit"),
  apList: document.getElementById("ap-list"),
  suggest: document.getElementById("transfer-suggest"),
  input: document.getElementById("transfer-input"),
  options: document.getElementById("transfer-options"),
  add: document.getElementById("transfer-add"),
  chosen: document.getElementById("transfer-chosen"),
  source: document.getElementById("ap-source"),
};

function openCreditBox() {
  fillCreditBox();
  creditEl.box.showModal();
}

function fillCreditBox() {
  // AP: one line per exam: a box to tick, the score, and what it counts as.
  if (!creditTable) {
    creditEl.apList.innerHTML = '<p class="note">The AP chart didn\'t load. Check your connection and reopen this box.</p>';
  } else {
    creditEl.source.href = creditTable.source;
    creditEl.apList.innerHTML = creditTable.ap.map(function (exam) {
      const score = credit.ap[exam.name] || "";
      const options = ["", "3", "4", "5"].map(s =>
        '<option value="' + s + '"' + (String(score) === s ? " selected" : "") + ">" + (s || "—") + "</option>").join("");
      return '<div class="ap-row' + (score ? " taken" : "") + '"><label class="ap-name"><input type="checkbox" data-exam-check="' +
             escapeHtml(exam.name) + '"' + (score ? " checked" : "") + "> " + escapeHtml(exam.name) + "</label>" +
             '<label class="ap-score">score <select data-exam="' + escapeHtml(exam.name) + '">' + options + "</select></label>" +
             '<span class="ap-result">' + escapeHtml(apResult(exam.name)) + "</span></div>";
    }).join("");
  }

  // College credit: suggestions from the programs on the map, then the rest.
  const lower = graph
    ? graph.nodes.filter(n => n.level === "lower" && n.status === "active" && (n.in_major || shown.has(n.id)))
        .map(n => n.id).sort(bySortKey)
    : [];
  creditEl.suggest.innerHTML = lower.length
    ? '<p class="note">Lower-division courses in ' + escapeHtml(thisProgram()) + ":</p>" +
      '<div class="transfer-grid">' + lower.map(code =>
        '<label><input type="checkbox" data-transfer="' + escapeHtml(code) + '"' +
        (credit.transfer.includes(code) ? " checked" : "") + "> " + escapeHtml(code) +
        ' <span class="note">' + escapeHtml(nodesById[code].title || "") + "</span></label>").join("") + "</div>"
    : '<p class="note">Open a major or minor first to see its lower-division courses here, or add any course below.</p>';

  creditEl.options.innerHTML = graph
    ? graph.nodes.map(n => '<option value="' + escapeHtml(n.id) + '">').join("")
    : "";

  const others = credit.transfer.filter(code => !lower.includes(code));
  creditEl.chosen.innerHTML = others.map(code =>
    "<li>" + escapeHtml(code) + ' <button type="button" class="text-button" data-untransfer="' +
    escapeHtml(code) + '">remove</button></li>').join("");
}

// "counts as MATH 2A, MATH 2B…" for the score chosen, or why not.
function apResult(examName) {
  const score = credit.ap[examName];
  if (!score) return "";
  const row = apRow(examName, score);
  if (!row) return "no credit at this score";
  const units = row.units + " units";
  if (row.note) return units + ". " + row.note;
  return row.equivalents.length ? units + ", counts as " + row.equivalents.join(", ") : units + ", no specific UCSB course";
}

// After any change: save it, then redraw whatever shows credit.
function creditUpdated() {
  creditChanged();
  fillCreditBox();
  if (graph) {
    draw();
    if (currentView === "map") {
      if (selected) showDetails(selected); else showMajorSummary();
    }
  }
  if (currentView === "plan") {
    const removed = pruneCovered();
    if (removed) say(removed + (removed === 1 ? " course" : " courses") + " your credit covers came out of the plan.");
    planChanged();
  }
}

creditEl.apList.addEventListener("change", function (event) {
  // Ticking an exam fills in 3, the lowest score that earns credit; the
  // line beside it shows what that counts as, so a different score is easy
  // to set. Unticking removes it.
  const ticked = event.target.dataset.examCheck;
  if (ticked) {
    if (event.target.checked) credit.ap[ticked] = credit.ap[ticked] || 3;
    else delete credit.ap[ticked];
    creditUpdated();
    return;
  }
  const name = event.target.dataset.exam;
  if (!name) return;
  if (event.target.value) credit.ap[name] = Number(event.target.value);
  else delete credit.ap[name];
  creditUpdated();
});

creditEl.suggest.addEventListener("change", function (event) {
  const code = event.target.dataset.transfer;
  if (!code) return;
  if (event.target.checked) {
    if (!credit.transfer.includes(code)) credit.transfer.push(code);
  } else {
    credit.transfer = credit.transfer.filter(c => c !== code);
  }
  creditUpdated();
});

// Add any UCSB course by its code ("cmpsc 40" works too).
function addTransfer() {
  const code = creditEl.input.value.trim().toUpperCase().replace(/\s+/g, " ");
  if (!/^[A-Z][A-Z &]* \d+[A-Z]*$/.test(code)) return;
  if (!credit.transfer.includes(code)) credit.transfer.push(code);
  creditEl.input.value = "";
  creditUpdated();
}
creditEl.add.addEventListener("click", addTransfer);
creditEl.input.addEventListener("keydown", function (event) {
  if (event.key === "Enter") {
    event.preventDefault();
    addTransfer();
  }
});

creditEl.chosen.addEventListener("click", function (event) {
  const code = event.target.dataset.untransfer;
  if (!code) return;
  credit.transfer = credit.transfer.filter(c => c !== code);
  creditUpdated();
});

// "Credit" in the masthead, and "Add it" on the map, open the box.
document.addEventListener("click", function (event) {
  if (event.target.closest("[data-open-credit]")) openCreditBox();
});
creditEl.box.addEventListener("click", function (event) {
  if (event.target === creditEl.box) creditEl.box.close();     // a click outside the box closes it
});
