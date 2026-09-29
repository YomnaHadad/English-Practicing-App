from backend import assessment


def _answers(correct_levels):
    """Answer correctly only for questions whose level is in `correct_levels`."""
    return {
        q["id"]: (q["answer"] if q["level"] in correct_levels else (q["answer"] + 1) % len(q["options"]))
        for q in assessment.QUESTIONS
    }


def test_question_bank_is_valid():
    assert len(assessment.QUESTIONS) == 24
    for q in assessment.QUESTIONS:
        assert q["level"] in assessment.LEVELS and q["skill"] in assessment.SKILLS
        assert 0 <= q["answer"] < len(q["options"])


def test_public_questions_hide_answers():
    assert all("answer" not in q for q in assessment.public_questions())


def test_all_correct_is_c2():
    result = assessment.score(_answers(assessment.LEVELS))
    assert result["cefr_level"] == "C2"
    assert result["vocab_score"] == 100


def test_all_wrong_is_a1():
    result = assessment.score(_answers([]))
    assert result["cefr_level"] == "A1"
    assert result["grammar_score"] == 0


def test_stops_at_first_failed_level():
    # Passes A1-B1, fails B2, gets C1/C2 right by "luck" -> still B1
    result = assessment.score(_answers(["A1", "A2", "B1", "C1", "C2"]))
    assert result["cefr_level"] == "B1"


def test_submit_and_history(client, auth):
    qs = client.get("/api/assessments/questions", headers=auth).json()
    assert len(qs) == 24
    r = client.post("/api/assessments/", headers=auth, json={"answers": _answers(["A1", "A2"])})
    assert r.status_code == 201
    assert r.json()["cefr_level"] == "A2"
    history = client.get("/api/assessments/me", headers=auth).json()
    assert [a["cefr_level"] for a in history] == ["A2"]
