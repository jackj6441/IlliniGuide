from app.ingestion.career_tags import seed_core_career_tags


class FakeSession:
    def __init__(self, courses):
        self.courses = courses
        self.current_course_id = None
        self.committed = False

    def scalar(self, statement):
        return self.courses.get(self.current_course_id)

    def commit(self):
        self.committed = True


def make_course(course_id, title="Course Title", prerequisites="Credit in ECE 120"):
    return type(
        "Course",
        (),
        {
            "course_id": course_id,
            "title": title,
            "prerequisites": prerequisites,
            "source_url": "https://example.com",
            "career_tags": None,
        },
    )()


def test_seed_core_career_tags_updates_existing_courses(monkeypatch):
    course = make_course("ECE 408")
    session = FakeSession({"ECE 408": course})
    monkeypatch.setattr(
        "app.ingestion.career_tags.select",
        lambda model: SelectStub(session),
    )

    result = seed_core_career_tags(
        session,
        tag_map={"ECE 408": ["systems", "ai_infra", "systems"]},
    )

    assert result.rows_seen == 1
    assert result.rows_updated == 1
    assert result.rows_missing == 0
    assert course.career_tags == ["ai_infra", "systems"]
    assert course.title == "Course Title"
    assert course.prerequisites == "Credit in ECE 120"
    assert session.committed is True


def test_seed_core_career_tags_tracks_missing_courses(monkeypatch):
    session = FakeSession({})
    monkeypatch.setattr(
        "app.ingestion.career_tags.select",
        lambda model: SelectStub(session),
    )

    result = seed_core_career_tags(
        session,
        tag_map={"ECE 408": ["ai_infra"], "ECE 391": ["systems"]},
    )

    assert result.rows_seen == 2
    assert result.rows_updated == 0
    assert result.rows_missing == 2
    assert result.missing_course_ids == ["ECE 408", "ECE 391"]
    assert session.committed is True


class SelectStub:
    def __init__(self, session):
        self.session = session

    def where(self, condition):
        course_id = condition.right.value
        self.session.current_course_id = course_id
        return self
