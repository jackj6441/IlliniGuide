import re


COURSE_ID_PATTERN = re.compile(r"\b([A-Za-z]{2,4})\s*-?\s*(\d{3})\b")


def normalize_course_id(value: str) -> str:
    compact = value.strip()
    match = COURSE_ID_PATTERN.fullmatch(compact)
    if not match:
        raise ValueError(f"Invalid course id: {value!r}")
    department, number = match.groups()
    return f"{department.upper()} {number}"


def extract_course_ids(text: str) -> list[str]:
    seen: set[str] = set()
    course_ids: list[str] = []
    for department, number in COURSE_ID_PATTERN.findall(text):
        course_id = f"{department.upper()} {number}"
        if course_id not in seen:
            seen.add(course_id)
            course_ids.append(course_id)
    return course_ids
