"""
Subjects organized by Semester
"""

SUBJECTS_BY_SEMESTER = {
    1: [
        "AP",
        "Calculus",
        "Func Eng",
        "Func Eng Lab",
        "Ideology of Pak",
        "IICT Lab",
        "PF",
        "PF Lab",
    ],
    2: [
        "Civics",
        "DLD",
        "DLD Lab",
        "Islamic",
        "OOP",
        "OOP Lab",
    ],
    3: [
        "COAL",
        "COAL Lab",
        "Data St",
        "Data St Lab",
        "Discrete",
        "LA",
        "Automata",
    ],
    4: [
        "ML",
        "ML Lab",
        "DB",
        "DB Lab",
        "OS",
        "OS Lab",
        "Prob & Stats",
        "Fund of SE",
    ],
    5: [
        "Comp Net",
        "Comp Net Lab",
        "Algo",
        "TBW",
    ],
    6: [
        "PDC",
        "S/w Const",
        "S/w Const Lab",
    ],
    7: [
        "Engg",
        "Info Sec",
    ],
    8: [],
}


def get_subjects(semester: int) -> list:
    """Get subjects for a specific semester."""
    return SUBJECTS_BY_SEMESTER.get(semester, [])


def get_all_subjects() -> list:
    """Get all subjects across all semesters."""
    all_subjects = []
    for subjects in SUBJECTS_BY_SEMESTER.values():
        all_subjects.extend(subjects)
    return all_subjects
