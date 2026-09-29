from datetime import timedelta

from backend import learning
from backend.models import utcnow


def _summary(**overrides):
    base = {
        "cefr_level": "B1",
        "latest_assessment_at": utcnow(),
        "weakest_skill": "grammar",
        "latest_skill_scores": {"vocab": 80, "grammar": 80, "reading": 80, "listening": 80},
        "vocab": {"total": 0, "mastered": 0, "due": 0, "review_accuracy": None},
        "pronunciation": {"attempts": 0, "average_recent": None, "weak_words": []},
        "tutor": {"sessions": 1, "last_session": utcnow()},
    }
    base.update(overrides)
    return base


def test_new_user_is_sent_to_assessment():
    recs = learning.recommendations(_summary(cefr_level=None))
    assert [r["action"] for r in recs] == ["assessment"]


def test_old_assessment_triggers_retake():
    old = utcnow() - timedelta(days=45)
    recs = learning.recommendations(_summary(latest_assessment_at=old))
    assert recs[0]["action"] == "assessment"


def test_due_vocab_and_low_pronunciation():
    s = _summary(
        vocab={"total": 10, "mastered": 0, "due": 8, "review_accuracy": None},
        pronunciation={"attempts": 5, "average_recent": 55, "weak_words": ["thorough"]},
    )
    actions = [r["action"] for r in learning.recommendations(s)]
    assert actions[:2] == ["review", "shadowing"]


def test_stale_tutor_and_weak_skill():
    s = _summary(
        tutor={"sessions": 1, "last_session": utcnow() - timedelta(days=10)},
        weakest_skill="listening",
        latest_skill_scores={"vocab": 80, "grammar": 80, "reading": 80, "listening": 40},
    )
    actions = [r["action"] for r in learning.recommendations(s)]
    assert actions == ["tutor", "shadowing"]


def test_on_track_user_gets_fallback():
    assert learning.recommendations(_summary())[0]["action"] == "shadowing"


def test_review_flow(client, auth):
    words = [("ominous", "The sky looked ominous tonight."), ("reckless", "That was a reckless plan."),
             ("cunning", "The fox was cunning and quick."), ("humble", "He stayed humble after winning.")]
    for w, s in words:
        assert client.post("/api/vocab", headers=auth, json={"word": w, "sentence": s, "movie_title": "Test"}).status_code == 200
    # Saving twice does not duplicate
    client.post("/api/vocab", headers=auth, json={"word": "Ominous", "sentence": "x"})
    assert len(client.get("/api/vocab", headers=auth).json()) == 4

    exercises = client.get("/api/review/exercises?n=4", headers=auth).json()
    assert len(exercises) == 4
    ex = exercises[0]
    assert "_____" in ex["sentence"] and len(ex["options"]) == 4

    # Server grades: find the right word by trying options
    outcomes = [
        client.post("/api/review/answer", headers=auth, json={"vocab_id": ex["vocab_id"], "answer": o}).json()["correct"]
        for o in ex["options"]
    ]
    assert outcomes.count(True) == 1

    vocab = client.get("/api/progress", headers=auth).json()["vocab"]
    assert vocab["total"] == 4 and vocab["review_accuracy"] == 25


def test_users_cannot_touch_each_others_words(client, auth):
    word_id = client.post("/api/vocab", headers=auth, json={"word": "ominous", "sentence": "An ominous sky."}).json()["id"]
    client.post("/api/auth/register", json={"username": "bob", "email": "bob@example.com", "password": "password123"})
    token = client.post("/api/auth/token", data={"username": "bob", "password": "password123"}).json()["access_token"]
    r = client.post("/api/review/answer", headers={"Authorization": f"Bearer {token}"}, json={"vocab_id": word_id, "answer": "ominous"})
    assert r.status_code == 404


def test_weak_areas_in_progress(client, auth):
    client.post("/api/assessments/", headers=auth, json={"answers": {}})  # everything wrong
    areas = client.get("/api/progress", headers=auth).json()["weak_areas"]
    assert areas and "placement score" in areas[0]
