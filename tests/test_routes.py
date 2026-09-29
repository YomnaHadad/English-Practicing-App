"""API tests for routes that call outside services; those calls are replaced with fakes."""
import io
import json

import pytest

from backend import ai, subtitles, tts

SRT = """1
00:00:01,000 --> 00:00:03,000
<i>Hello there.</i>

2
00:00:04,000 --> 00:00:06,000
General Kenobi!

3
00:02:00,000 --> 00:02:02,000
A new scene begins.
"""


def test_parse_and_group_subtitles():
    lines = subtitles.parse_srt(SRT)
    assert [l["text"] for l in lines] == ["Hello there.", "General Kenobi!", "A new scene begins."]
    chapters = subtitles.group_into_chapters(lines)
    assert [len(c["lines"]) for c in chapters] == [2, 1]  # 30s+ pause splits the chapters


def test_movie_search_and_subtitle_cache(client, auth, monkeypatch):
    monkeypatch.setattr(subtitles, "search_movies", lambda q: [{"title": "Test", "year": 2000, "release_name": "", "file_id": 7}])
    assert client.get("/api/movies/search?q=test", headers=auth).json()[0]["file_id"] == 7

    calls = []
    monkeypatch.setattr(subtitles, "download_subtitle", lambda fid: calls.append(fid) or subtitles.parse_srt(SRT))
    for _ in range(2):
        r = client.get("/api/movies/7", headers=auth)
        assert len(r.json()["chapters"]) == 2
    assert calls == [7]  # second request served from the DB cache


def test_missing_api_key_gives_clear_error(client, auth, monkeypatch):
    monkeypatch.delenv("OPENSUBTITLES_API_KEY", raising=False)
    r = client.get("/api/movies/search?q=test", headers=auth)
    assert r.status_code == 502 and "not configured" in r.json()["detail"]


def test_chapter_completion(client, auth):
    body = {"movie_title": "M", "chapter_idx": 3}
    client.post("/api/chapters/complete", headers=auth, json=body)
    client.post("/api/chapters/complete", headers=auth, json=body)
    assert client.get("/api/movies/completed?movie_title=M", headers=auth).json() == [3]


def test_explain_saves_word_for_review(client, auth, monkeypatch):
    monkeypatch.setattr(ai, "explain_word", lambda w, s: {"easy_word": "scary", "meaning_in_sentence": "threatening"})
    r = client.post("/api/vocab/explain", headers=auth, json={"word": "Ominous", "sentence": "An ominous sky.", "movie_title": "M"})
    assert r.json()["easy_word"] == "scary"
    saved = client.get("/api/vocab", headers=auth).json()
    assert saved[0]["word"] == "ominous" and "scary" in saved[0]["meaning"]


def test_pronunciation_is_scored_and_stored(client, auth, monkeypatch):
    monkeypatch.setattr(ai, "transcribe", lambda audio, name="": "hello there")
    r = client.post(
        "/api/pronunciation",
        headers=auth,
        data={"target": "Hello there general Kenobi", "movie_title": "M"},
        files={"audio": ("speech.webm", io.BytesIO(b"fake"), "audio/webm")},
    )
    result = r.json()
    assert 0 < result["score"] < 100
    assert result["unclear_words"] == ["general", "kenobi"]
    p = client.get("/api/progress", headers=auth).json()["pronunciation"]
    assert p["attempts"] == 1 and p["weak_words"] == ["general", "kenobi"]


def test_pronunciation_rejects_empty_upload(client, auth):
    r = client.post("/api/pronunciation", headers=auth, data={"target": "Hi"},
                    files={"audio": ("speech.webm", io.BytesIO(b""), "audio/webm")})
    assert r.status_code == 400


def test_tts_endpoint(client, auth, monkeypatch):
    async def fake(text, accent):
        return b"mp3-bytes"
    monkeypatch.setattr(tts, "synthesize", fake)
    r = client.post("/api/tts", headers=auth, json={"text": "Hello"})
    assert r.content == b"mp3-bytes" and r.headers["content-type"] == "audio/mpeg"


# ---------- tutor ----------

@pytest.fixture
def fake_tutor(monkeypatch):
    seen = {}

    def reply(level, topic, history, words, weak):
        seen.update(level=level, history=history, words=words)
        return "Nice! What did you do today?"

    monkeypatch.setattr(ai, "tutor_reply", reply)
    monkeypatch.setattr(ai, "transcribe", lambda audio, name="": "I goed to school")
    monkeypatch.setattr(
        ai, "tutor_feedback",
        lambda level, topic, history: {"summary": "Good job.", "mistakes": [{"said": "I goed", "correction": "I went", "explanation": "Irregular verb."}]},
    )
    return seen


def test_tutor_session_end_to_end(client, auth, fake_tutor):
    opening = client.post("/api/tutor/turn", headers=auth, data={"topic": "Daily life"}).json()
    assert opening["reply"] and opening["level"] == "A2"  # default until assessed

    history = [{"role": "assistant", "text": opening["reply"]}]
    turn = client.post(
        "/api/tutor/turn", headers=auth,
        data={"transcript": json.dumps(history)},
        files={"audio": ("speech.webm", io.BytesIO(b"fake"), "audio/webm")},
    ).json()
    assert turn["user_text"] == "I goed to school"
    assert fake_tutor["history"][-1] == {"role": "user", "text": "I goed to school"}

    history += [{"role": "user", "text": turn["user_text"]}, {"role": "assistant", "text": turn["reply"]}]
    done = client.post("/api/tutor/finish", headers=auth, json={"topic": "Daily life", "transcript": history}).json()
    assert done["session"]["mistakes"][0]["correction"] == "I went"
    assert done["next_steps"][0]["action"] == "assessment"  # no placement test yet

    progress = client.get("/api/progress", headers=auth).json()
    assert progress["tutor"]["sessions"] == 1
    assert progress["tutor"]["recent_mistakes"][0]["said"] == "I goed"
    assert len(client.get("/api/tutor/sessions", headers=auth).json()) == 1


def test_tutor_uses_assessed_level_and_study_words(client, auth, fake_tutor):
    qs = client.get("/api/assessments/questions", headers=auth).json()
    # answer nothing correctly -> A1
    client.post("/api/assessments/", headers=auth, json={"answers": {}})
    client.post("/api/vocab", headers=auth, json={"word": "ominous", "sentence": "An ominous sky."})
    client.post("/api/tutor/turn", headers=auth, data={})
    assert fake_tutor["level"] == "A1" and fake_tutor["words"] == ["ominous"]


def test_tutor_validation(client, auth, fake_tutor):
    assert client.post("/api/tutor/finish", headers=auth, json={"transcript": [{"role": "assistant", "text": "Hi"}]}).status_code == 400
    assert client.post("/api/tutor/turn", headers=auth, data={"transcript": "not json"}).status_code == 400
    history = json.dumps([{"role": "assistant", "text": "Hi"}])
    assert client.post("/api/tutor/turn", headers=auth, data={"transcript": history}).status_code == 400  # nothing sent
    full = json.dumps([{"role": "user", "text": "x"}] * 15)
    assert client.post("/api/tutor/turn", headers=auth, data={"transcript": full, "text": "more"}).status_code == 400


# ---------- web UI ----------

def test_ui_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert client.get("/health").json() == {"status": "ok"}
