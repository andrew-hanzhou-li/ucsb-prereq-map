"""
extract.py (UC San Diego): read the saved department pages into a course list.

    python pipeline/campuses/ucsd/extract.py

Reads   data/ucsd/raw/<DEPT>.html      (from fetch.py)
Writes  data/ucsd/raw_courses.json     every undergraduate course, in the same
                                       shape as UCSB's data/raw_courses.json

How a course looks on a department page
---------------------------------------
    <p class="course-name">CSE 100. Advanced Data Structures (4)</p>
    <p class="course-descriptions">High-performance data structures ...
       <strong><em>Prerequisites:</em></strong> CSE 21 or MATH 154 and CSE 12;
       restricted to undergraduates. Graduate students will be allowed as
       space permits.</p>

The name line can also be a cross-listed course ("CSE 256/LING 256.",
"AAS/ANSC 185.", "HIEU 160/260."), a remote twin ("DSC 10/R."), a list
("POLI 5R, POLI 5DR, ECON 5R."), a sequence ("MATH 20A-B-C.", "EDS 128 A-B.",
"GSS 21-22-23."), or start with a department name ("Linguistics/Arabic (LIAB)
1A."). CSE adds the tags its majors use ("(4) Tag: Systems"). After
"Prerequisites:" the catalog writes the prerequisites, then often notes about
enrolling; the notes are split off into "comments" (see split_prereq_text).

Graduate courses (numbered 200 and up) are left out: the site is for
undergraduates. The level comes from the number (under 100: lower
division), which is how UCSD numbers courses.
"""

import glob
import html.parser
import json
import os
import re

RAW_DIR = os.path.join("data", "ucsd", "raw")
OUTPUT = os.path.join("data", "ucsd", "raw_courses.json")

# One piece of the code list: "CSE 100", "COM GEN 194", "CSE" (a subject
# whose number follows), "260" (a number whose subject came before), "R"
# (letters added to the code before), or a sequence ("20A-B-C", "21-22-23").
SUBJECT = r"[A-Z]{2,8}(?: GEN)?"
PIECE = r"(?:%s(?: ?\d+ ?[A-Z]*(?:(?:[-–][A-Z]+)+|(?:-\d+)+)?)?|\d+[A-Z]*(?:-\d+)*|[A-Z]{1,3})" % SUBJECT
CODE_LIST = r"%s(?:\s*[/,]\s*%s)*" % (PIECE, PIECE)
# "CSE 100. Advanced Data Structures (4)": the codes, the title, the units.
# The period is missing on a few lines ("COMM 114M CSI: ..."), and a few
# have no units.
NAME_LINE = re.compile(r"^(?P<codes>%s)(?:[.:]\s*|\s+)(?P<title>.*?)\s*(?:\((?P<units>[^()]*)\))?\s*$" % CODE_LIST)
# "Linguistics/Arabic (LIAB) 1A": the department name in front of the code
# (words, then the code in brackets, then the number).
NAMED_SUBJECT = re.compile(r"^[A-Z][a-z][A-Za-z /&-]*\(([A-Z]{2,8})\)\s*(?=\d)")
# "(4) Tag: Systems" or "(4) Tags: Systems, Applications of Computing"
TAGS = re.compile(r"\s+Tags?:\s*(?P<tags>.*)$")
# One course code anywhere in a sentence ("MATH 20C", "Math 20D", "MATH 20 C").
CODE_IN_TEXT = re.compile(r"\b[A-Za-z]{2,5} ?\d+[A-Z]{0,3}\b")

# Sentences after the first that are about enrolling, not about what must
# come first. They go into "comments".
COMMENT_STARTS = re.compile(
    r"^(?:(?:students )?(?:may not|will not|cannot) receive (?:duplicate )?credit|recommended|"
    r"(?:graduate|all other) students will be allowed|this course|attendance|"
    r"credit (?:not|will not)|may be (?:repeated|taken for credit)|program or materials fee|"
    r"renumbered|formerly|must be taken in sequence|letter grade|duplicate credit|"
    r"students may receive credit for|\(?(?:may not be|only) offered|pass/not pass|repeatable)", re.IGNORECASE)
# Sentences after the first that ARE requirements even without a course code:
# who may enroll, and whose approval is needed.
REQUIREMENT_WORDS = re.compile(
    r"\b(?:restricted to|open to|majors? only|consent|approval|authorization|stamp|"
    r"accepted (?:in|into|to)|acceptance|admission|admittance|standing|may enroll|cannot enroll|"
    r"enrollment via|invitation|must be (?:an? )?[\w ]*students?|participants)\b", re.IGNORECASE)
# "(F,W,S)": the quarters a course is usually offered, written by a few
# departments at the end of the description or prerequisites.
QUARTER_MARK = re.compile(r"\s*\((?P<quarters>[FWSU](?:\s*,\s*[FWSU])*)\)\.?")
QUARTER_NAMES = {"F": "Fall", "W": "Winter", "S": "Spring", "U": "Summer"}

# Clauses inside a sentence (after ";") that are notes, e.g. "CSE 11;
# restricted to undergraduates; graduate students will be allowed as space permits".
COMMENT_CLAUSE = re.compile(r";\s*(?:graduate|all other) students will be allowed as space permits", re.IGNORECASE)


class CoursePageParser(html.parser.HTMLParser):
    """Collects (kind, text) for each course-name and course-descriptions
    paragraph, in page order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paragraphs = []
        self.kind = None          # "course-name" or "course-descriptions" while inside one
        self.text = []

    def handle_starttag(self, tag, attrs):
        css = dict(attrs).get("class") or ""
        if tag == "p" and css in ("course-name", "course-descriptions"):
            self.kind, self.text = css, []
        elif tag == "br" and self.kind:
            self.text.append(" ")

    def handle_endtag(self, tag):
        if tag == "p" and self.kind:
            self.paragraphs.append((self.kind, " ".join("".join(self.text).split())))
            self.kind = None

    def handle_data(self, data):
        if self.kind:
            self.text.append(data)


def expand_codes(codes_text):
    """The course codes on a name line, in order.
        "CSE 100"             -> ["CSE 100"]
        "CSE 256/LING 256"    -> ["CSE 256", "LING 256"]
        "AAS/ANSC 185"        -> ["AAS 185", "ANSC 185"]
        "HIEU 160/260"        -> ["HIEU 160", "HIEU 260"]
        "DSC 10/R"            -> ["DSC 10", "DSC 10R"]
        "MATH 20A-B-C"        -> ["MATH 20A", "MATH 20B", "MATH 20C"]
        "ECE 145AL-BL-CL"     -> ["ECE 145AL", "ECE 145BL", "ECE 145CL"]
        "VIS 128A–E"          -> ["VIS 128A", ..., "VIS 128E"] (an en dash
                                 between single letters is a range)
        "GSS 21-22-23"        -> ["GSS 21", "GSS 22", "GSS 23"]
    Returns [] if a piece can't be read."""
    codes, waiting_subjects, subject = [], [], None
    for piece in re.split(r"\s*[/,]\s*", codes_text.strip()):
        full = re.match(r"^(%s) ?(\d+) ?([A-Z]*)((?:[-–][A-Z]+)+)?((?:-\d+)+)?$" % SUBJECT, piece)
        bare_number = re.match(r"^(\d+[A-Z]*)$", piece)
        if full:
            subject, number, letters, letter_run, number_run = full.groups()
            range_end = re.match(r"^–([A-Z])$", letter_run or "")
            if range_end and len(letters) == 1:  # "128A–E": A through E
                numbers = [number + chr(c) for c in range(ord(letters), ord(range_end.group(1)) + 1)]
            elif letter_run:                    # "20A-B-C", "128 A-B", "145AL-BL-CL"
                numbers = [number + letters] + [number + x for x in re.split("[-–]", letter_run.strip("-–"))]
            elif number_run:                    # "21-22-23"
                numbers = [number + letters] + number_run.strip("-").split("-")
            else:
                numbers = [number + letters]
            for waiting in waiting_subjects:    # "AAS/ANSC 185": AAS takes ANSC's number
                codes.append("%s %s" % (waiting, numbers[0]))
            waiting_subjects = []
            codes.extend("%s %s" % (subject, n) for n in numbers)
        elif re.match(r"^%s$" % SUBJECT, piece) and len(piece) >= 2 and not codes:
            waiting_subjects.append(piece)
        elif bare_number and subject:
            codes.append("%s %s" % (subject, bare_number.group(1)))
        elif re.match(r"^[A-Z]{1,3}$", piece) and codes:
            codes.append(codes[-1] + piece)     # "DSC 10/R": the remote twin
        else:
            return []
    return [] if waiting_subjects else codes


def level_of(code):
    """"lower", "upper" or "graduate", from the course number."""
    number = int(re.search(r"\d+", code.split(" ")[-1]).group())
    return "lower" if number < 100 else "upper" if number < 200 else "graduate"


def split_units(units_text, count):
    """Units for each of `count` courses from "(4)", "(2 or 4)", "(1–4)" or
    "(4-4-4)". A range is written "1-4", as UCSB writes it."""
    text = units_text.replace("–", "-").replace(" to ", "-").strip()
    parts = text.split("-")
    if count > 1 and len(parts) == count:            # a sequence: one number each
        return [p.strip() for p in parts]
    return [text] * count


def split_sentences(text):
    """Sentences, split after ". " (but not after "e.g." or initials)."""
    return [s for s in re.split(r"(?<![A-Z]\.[A-Z])(?<!\be\.g)(?<!\bi\.e)\.\s+(?=[A-Z])", text) if s]


def split_prereq_text(text):
    """(prerequisites, comments). The first sentence is always prerequisites
    (less any "graduate students will be allowed..." clause); each later one
    is judged on its own: a note about enrolling goes to comments, a sentence
    naming a course or saying who may enroll stays."""
    sentences = split_sentences(QUARTER_MARK.sub("", text).strip())
    prereqs, comments = [], []
    for i, sentence in enumerate(sentences):
        for clause in COMMENT_CLAUSE.findall(sentence):
            comments.append(clause.lstrip("; ").capitalize())
        sentence = COMMENT_CLAUSE.sub("", sentence)
        if i == 0:
            prereqs.append(sentence)
        elif COMMENT_STARTS.match(sentence):
            comments.append(sentence)
        elif CODE_IN_TEXT.search(sentence) or REQUIREMENT_WORDS.search(sentence):
            prereqs.append(sentence)
        else:
            comments.append(sentence)
    join = lambda parts: ". ".join(p.rstrip(".") for p in parts) + ("." if parts else "")
    return join(prereqs), join(comments)


def courses_on_page(path):
    """Every undergraduate course on one department page."""
    parser = CoursePageParser()
    with open(path, encoding="utf-8") as f:
        parser.feed(f.read())
    department = os.path.splitext(os.path.basename(path))[0].upper()
    courses, problems = [], []
    paragraphs = parser.paragraphs
    for i, (kind, text) in enumerate(paragraphs):
        if kind != "course-name":
            continue
        tags = TAGS.search(text)
        line = NAMED_SUBJECT.sub(r"\1 ", text[:tags.start()] if tags else text)
        name = NAME_LINE.match(line)
        codes = expand_codes(name.group("codes")) if name else []
        if not codes:
            problems.append("%s: can't read the name line %r" % (department, text))
            continue
        following = paragraphs[i + 1] if i + 1 < len(paragraphs) else None
        description = following[1] if following and following[0] == "course-descriptions" else ""
        marks = QUARTER_MARK.findall(description)
        offered = [QUARTER_NAMES[q] for q in "FWSU" if marks and q in marks[-1]]
        description = QUARTER_MARK.sub("", description)
        parts = re.split(r"\bPrerequisites?:\s*", description, maxsplit=1)
        prereq_text, comments = split_prereq_text(parts[1]) if len(parts) == 2 else ("", "")
        for code, units in zip(codes, split_units(name.group("units") or "", len(codes))):
            if level_of(code) == "graduate":
                continue
            subject, number = code.rsplit(" ", 1)
            courses.append({
                "code": code, "subject": subject, "number": number, "level": level_of(code),
                "title": name.group("title"), "units": units, "offered": offered,
                "prereq_text": prereq_text, "comments": comments,
                "description": parts[0].strip(), "departments": [department],
                "cross_listed": [c for c in codes if c != code and level_of(c) != "graduate"]
                                if "/" in name.group("codes") else [],
                "tags": [t.strip() for t in tags.group("tags").split(",")] if tags else [],
                # The course on its department's page: "...courses/CSE.html#cse100"
                "url": "https://catalog.ucsd.edu/courses/%s.html#%s" % (
                    os.path.splitext(os.path.basename(path))[0], code.replace(" ", "").lower()),
            })
    return courses, problems


def main():
    by_code, problems = {}, []
    for path in sorted(glob.glob(os.path.join(RAW_DIR, "*.html"))):
        if os.path.basename(path) == "index.html":
            continue
        courses, page_problems = courses_on_page(path)
        problems.extend(page_problems)
        for course in courses:
            # A cross-listed course is on each of its departments' pages:
            # keep the first copy, and note every department it's listed in.
            if course["code"] in by_code:
                known = by_code[course["code"]]
                known["departments"] = sorted(set(known["departments"]) | set(course["departments"]))
            else:
                by_code[course["code"]] = course
    courses = sorted(by_code.values(), key=lambda c: (c["subject"], int(re.match(r"\d+", c["number"]).group()), c["number"]))
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"courses": courses}, f, indent=1, ensure_ascii=False)
    print("Wrote %s: %d courses" % (OUTPUT, len(courses)))
    for problem in problems:
        print("  " + problem)


if __name__ == "__main__":
    main()
