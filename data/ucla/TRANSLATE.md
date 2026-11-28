# Translating UCLA's prose major rules

Most of each UCLA major comes from the catalog as structured lists. A few rule groups are only a sentence ("Complete three additional upper-division ecology and evolutionary biology courses (minimum 12 units)"). Each such rule is in `data/ucla/majors_prose.json` (`major`, `rule_id`, `title`, `text`). Turn each into one requirement node, so the planner can count it.

Work only from the rule's text. Don't invent courses or numbers.

## Node format (the same as UC San Diego's majors)

| Node | Meaning |
|---|---|
| `{"type": "course", "code": "COM SCI 31"}` | one course; UCLA codes as the catalog writes them, one space before the number: "COM SCI 31", "C&EE 110", "EC ENGR M16" |
| `{"type": "all", "items": [...]}` | every item |
| `{"type": "choose", "count": N, "items": [...]}` | N of the items |
| `{"type": "units", "units": N, "items": [...]}` | at least N units from the items |
| `{"type": "text", "text": "…"}` | a rule that can't be counted; quote the catalog |

Shorthand items, allowed inside `choose`/`units`:

| Item | Meaning |
|---|---|
| `{"type": "range", "subject": "COM SCI", "from": 100, "to": 188}` | every course of that subject numbered in the range (letters around the number, M151B or CM187, count by their number) |
| `{"type": "any", "subject": "EE BIOL", "level": "upper", "except": ["EE BIOL 199"]}` | any course of the subject at that level (`lower` 1–99, `upper` 100–199) |

Subjects are written in words in the rules; their codes are in `data/ucla/subjects.json` (code -> name, e.g. "EE BIOL": "Ecology and Evolutionary Biology"). Use the code.

## Reading rules

1. "Complete three additional upper-division ecology and evolutionary biology courses (minimum 12 units)" -> `choose 3` of `any` upper EE BIOL (the count of courses is the rule; put the units in `notes`).
2. "seven elective courses from Computer Science 100 through CM187 except M148" -> `choose 7` of `range` COM SCI 100–187 with `"except": ["COM SCI M148"]` on the range item.
3. A list the catalog keeps elsewhere ("from an approved list available in the Office of Academic and Student Affairs", "from the life sciences course list") -> a `text` node with the rule's words. Don't guess the list.
4. Honors programs, departmental scholar programs, study-abroad notes, advising notes and anything optional -> `{"type": "text", "text": "…", "optional": true}` (the program shows it but doesn't count it).
5. A language or proficiency rule ("the equivalent to the sixth level of one foreign language") -> `text`.
6. "at least one course from at least four of the following areas" and other rules that constrain how courses spread across areas: count what can be counted (`choose 8` of `any` upper ASIAN), and put the spread rule in `notes`.
7. Each node may carry `"label"` (use the rule's `title`) and `"notes"` (a short quote of conditions).

## Output

One JSON object, keyed by `rule_id`: `{"<rule_id>": {"major": "...", "title": "...", "node": {...}}, ...}`, written to the file you're told. Valid JSON, ASCII hyphens. Report: how many rules you translated as structure vs text, and the 5 hardest calls (rule id + one line).
