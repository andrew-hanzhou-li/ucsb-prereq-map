"""
build_ap.py (UCLA): the AP credit chart, from UCLA Admission's tables.

    python pipeline/campuses/ucla/build_ap.py

Reads   https://admission.ucla.edu/admitted-students/ap-credit-the-college
        https://admission.ucla.edu/admitted-students/ap-credit-engineering
Writes  data/ucla/ap_credit.json     in the shape build_credit.py reads (as UCSB's
                                     and UCSD's ap_credit.json)

UCLA's chart depends on the school a student is in; each school has a page
of tables, one per subject:
    AP Exam Name | AP Score | Subject Area | Title/Course # | Units | Req's Met
    Calculus BC  | 3        | MATH         | Calculus       | 8.0   | QR
    Calculus BC  | 5        | MATH         | 31A and 31B    | 8.0   | QR
A "Title/Course #" with numbers names the UCLA courses the exam counts as
("31A and 31B" -> MATH 31A, MATH 31B); a title alone ("Calculus",
"Unassigned") is credit with no particular course. The College of Letters
and Science's page is used, and where Engineering's differs a row says what
Engineering students get instead.
"""

import html
import json
import os
import re
import urllib.request

PAGES = {
    "college": "https://admission.ucla.edu/admitted-students/ap-credit-the-college",
    "engineering": "https://admission.ucla.edu/admitted-students/ap-credit-engineering",
}
OUTPUT = os.path.join("data", "ucla", "ap_credit.json")
USER_AGENT = "prereq-planner (student project)"


def cells(row):
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def scores_of(text):
    """"3–5" -> [3, 4, 5]; "4" -> [4]; "4, 5" -> [4, 5]."""
    text = text.replace("–", "-").replace("—", "-")
    found = set()
    for low, high in re.findall(r"(\d)\s*-\s*(\d)", text):
        found.update(range(int(low), int(high) + 1))
    found.update(int(n) for n in re.findall(r"(?<![-\d])(\d)(?![-\d])", re.sub(r"\d\s*-\s*\d", "", text)))
    return sorted(found)


def courses_of(subject, title):
    """"31A and 31B" with subject MATH -> ["MATH 31A", "MATH 31B"]; a title -> []."""
    numbers = re.findall(r"\b([A-Z]{0,2}\d+[A-Z]*)\b", title)
    if not numbers or not subject:
        return []
    return [subject.strip() + " " + n for n in numbers]


def read_page(url):
    page = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=60).read().decode("utf-8", "replace")
    exams = {}
    for table in re.findall(r"<table.*?</table>", page, re.S):
        name = None
        for row in re.findall(r"<tr.*?</tr>", table, re.S):
            c = cells(row)
            if not c or c[0].lower().startswith("ap exam"):
                continue
            if len(c) < 5:
                continue
            # The exam's name is written once; its later rows leave the cell blank.
            if c[0]:
                name = c[0]
            else:
                c[0] = name
            exam, score, subject, title, units = c[:5]
            scores = scores_of(score)
            if not exam or not scores:
                continue
            try:
                unit_value = float(units)
            except ValueError:
                unit_value = None
            exams.setdefault(exam, []).append({
                "scores": scores, "units": int(unit_value) if unit_value and unit_value.is_integer() else unit_value,
                "equivalents": courses_of(subject, title),
                "note": "" if courses_of(subject, title) or title.lower() in ("unassigned", "") else "credit as " + subject + " (" + title + ")",
            })
    return exams


def main():
    college = read_page(PAGES["college"])
    engineering = read_page(PAGES["engineering"])
    exams = []
    for name in sorted(college):
        rows = college[name]
        for row in rows:
            other = next((r for r in engineering.get(name, []) if set(row["scores"]) & set(r["scores"])), None)
            if other and other["equivalents"] != row["equivalents"]:
                said = ", ".join(other["equivalents"]) if other["equivalents"] else "no particular course"
                row["note"] = (row["note"] + "; " if row["note"] else "") + "Engineering students: " + said
        exams.append({"name": name, "rows": rows})
    chart = {
        "source": PAGES["college"],
        "catalog_year": "2026-27",
        "notes": ["Read from UCLA Admission's AP credit tables for the College of Letters and Science; "
                  "where the Samueli School of Engineering's table differs, the row's note says so "
                  "(" + PAGES["engineering"] + ").",
                  "Each row: the scores that earn it, the units, and the UCLA courses the exam counts as."],
        "exams": exams,
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(chart, f, indent=1, ensure_ascii=False)
    print("Wrote %s: %d exams, %d rows with courses" % (OUTPUT, len(exams),
          sum(1 for e in exams for r in e["rows"] if r["equivalents"])))


if __name__ == "__main__":
    main()
