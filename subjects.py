"""
subjects.py: how the catalog writes department names, and the official code for each.

The catalog's prerequisite text is written by hand by many departments over
many years, so the same department shows up under several names:

    "Mathematics 3A", "Math 3A", "MATH 3A"      all mean  MATH 3A
    "Computer Science 16", "CS 16", "CMPSCI 16" all mean  CMPSC 16

SUBJECT_NAMES maps every written form we found in the 2026-27 catalog to the
official subject code. It was built by counting the words that appear right
before a course number and keeping the ones that aren't already codes.

If the parser misses a course because a department is written a new way,
add that spelling here. Matching ignores upper/lower case.
"""

SUBJECT_NAMES = {
    # Name as written           Official code
    "Anthropology": "ANTH",
    "Anth": "ANTH",
    "Art": "ART",
    "Asian American Studies": "AS AM",
    "ASAM": "AS AM",
    "Astronomy": "ASTRO",
    "Black Studies": "BL ST",
    "BLST": "BL ST",
    "Chemical Engineering": "CH E",
    "ChemicaEngineering": "CH E",       # typo in the catalog
    "ChE": "CH E",
    "Chemistry": "CHEM",
    "Chem": "CHEM",
    "Chicano Studies": "CH ST",
    "Chinese": "CHIN",
    "Chin": "CHIN",
    "Classics": "CLASS",
    "Communication": "COMM",
    "Comm": "COMM",
    "Comparative Literature": "C LIT",
    "Computer Science": "CMPSC",
    "CS": "CMPSC",
    "CMPSCI": "CMPSC",
    "CPMSCI": "CMPSC",                  # typo in the catalog
    "Dance": "DANCE",
    "Earth Science": "EARTH",
    "Earth Sciences": "EARTH",
    "Earth": "EARTH",
    "Geol": "EARTH",
    "Economics": "ECON",
    "Econ": "ECON",
    "Education": "ED",
    "Electrical Engineering": "ECE",
    "Engineering": "ENGR",
    "English": "ENGL",
    "Environmental Studies": "ENV S",
    "Env. St.": "ENV S",
    "ENVS": "ENV S",
    "Feminist Studies": "FEMST",
    "Film and Media Studies": "FAMST",
    "Film and Media": "FAMST",
    "Film Studies": "FAMST",
    "French": "FR",
    "Geography": "GEOG",
    "German": "GER",
    "Global Studies": "GLOBL",
    "Greek": "GREEK",
    "Hebrew": "HEB",
    "History": "HIST",
    "Hist": "HIST",
    "Italian": "ITAL",
    "Japanese": "JAPAN",
    "Korean": "KOR",
    "Latin": "LATIN",
    "Linguistics": "LING",
    "Ling": "LING",
    "Materials": "MATRL",
    "Mathematics": "MATH",
    "Math": "MATH",
    "Mechanical Engineering": "ME",
    "Military Science": "MS",
    "Music": "MUS",
    "Mus": "MUS",
    "Philosophy": "PHIL",
    "Physics CS": "PHYS CS",
    "Physics": "PHYS",
    "Phys": "PHYS",
    "Political Science": "POL S",
    "POLS": "POL S",
    "Portuguese": "PORT",
    "Psychology": "PSY",
    "Psy": "PSY",
    "Pstat": "PSTAT",
    "Statistics": "PSTAT",
    "Religious Studies": "RG ST",
    "Relgious Studies": "RG ST",        # typo in the catalog
    "RGST": "RG ST",
    "Russian": "RUSS",
    "Sociology": "SOC",
    "Spanish": "SPAN",
    "Theater": "THTR",
    "Theatre": "THTR",
    "Thtr": "THTR",
    "Writing": "WRIT",
    "Writ": "WRIT",
}
