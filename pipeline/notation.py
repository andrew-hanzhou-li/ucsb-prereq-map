"""
notation.py: a short way to write a prerequisite tree by hand.

The parser produces trees made of nested dictionaries (see parser.py). Those
are easy for a program to use but hard for a person to read or type, so test
answers and hand corrections use this one-line notation instead:

    MATH 3A                one course
    MATH 3A*               may be taken concurrently
    MATH 3A[C-]            needs a C- or better
    MATH 4B*[C]            both
    A & B                  A and B
    A | B                  A or B
    (A | B) & C            parentheses group things; you may not mix & and |
                           at the same level without them
    @standing              a non-course condition; the kinds are
                           @standing, @consent, @restriction, @exam, @other
    @other{prior programming experience}
                           the same, with the catalog's own words, shown on
                           the site (hand corrections should always give them;
                           to_notation() leaves the words out, so answers
                           still compare by structure)
    -                      no prerequisite at all

to_notation() turns a tree into this text and from_notation() turns the text
back into a tree. Two trees count as equal when their notations are equal,
because to_notation() sorts the items inside every & and | first. That way
"A & B" and "B & A" compare as the same answer.
"""

import re


# ---------------------------------------------------------------------------
# Tree -> text
# ---------------------------------------------------------------------------

def to_notation(node):
    """Turn a prerequisite tree into one line of notation."""
    if node is None:
        return "-"
    return _write(node, top=True)


def _write(node, top=False):
    kind = node["type"]

    if kind == "course":
        text = node["code"]
        if node.get("concurrent"):
            text += "*"
        if node.get("min_grade"):
            text += "[" + node["min_grade"] + "]"
        return text

    if kind == "condition":
        return "@" + node["kind"]

    # "and" or "or": write each item, sort them so order doesn't matter,
    # and join them with the right symbol.
    symbol = " & " if kind == "and" else " | "
    parts = sorted(_write(item) for item in node["items"])
    text = symbol.join(parts)
    if top:
        return text
    return "(" + text + ")"


# ---------------------------------------------------------------------------
# Text -> tree
# ---------------------------------------------------------------------------

def from_notation(text):
    """Turn one line of notation back into a tree. Raises ValueError if malformed."""
    text = text.strip()
    if text == "-":
        return None
    tokens = re.findall(r"\(|\)|&|\||[^()&|]+", text)
    tokens = [t.strip() for t in tokens if t.strip()]
    node, position = _read_group(tokens, 0)
    if position != len(tokens):
        raise ValueError("Unexpected text after position %d in: %s" % (position, text))
    return node


def _read_group(tokens, position):
    """Read items separated by one kind of operator, until ')' or the end."""
    items = []
    operator = None
    while position < len(tokens):
        token = tokens[position]
        if token == ")":
            break
        if token in ("&", "|"):
            if operator is not None and operator != token:
                raise ValueError("Mixed & and | without parentheses")
            operator = token
            position += 1
            continue
        if token == "(":
            node, position = _read_group(tokens, position + 1)
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError("Missing )")
            position += 1
        else:
            node = _read_leaf(token)
            position += 1
        items.append(node)

    if len(items) == 1:
        return items[0], position
    group_type = "and" if operator == "&" else "or"
    return {"type": group_type, "items": items}, position


def _read_leaf(token):
    if token.startswith("@"):
        match = re.match(r"^@(\w+)(?:\{(.*)\})?$", token)
        if not match:
            raise ValueError("Malformed condition: %s" % token)
        return {"type": "condition", "kind": match.group(1), "text": (match.group(2) or "").strip()}
    match = re.match(r"^(.+?)(\*)?(?:\[([A-F][+-]?)\])?$", token)
    return {
        "type": "course",
        "code": match.group(1).strip(),
        "concurrent": bool(match.group(2)),
        "min_grade": match.group(3),
    }
