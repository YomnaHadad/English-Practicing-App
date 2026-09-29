"""Pronunciation score = how closely a speech-to-text transcript matches the target line.

This is a proxy, not phoneme-level assessment: words the recognizer could not
match are treated as unclear. Speech recognizers also "auto-correct" toward
likely words, so scores can be generous.
"""
import difflib
import re


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower().replace("\u2019", "'"))


def score_pronunciation(target: str, transcript: str) -> dict:
    target_words, said_words = _words(target), _words(transcript)
    if not said_words:
        return {
            "score": 0,
            "transcript": "",
            "feedback": "Couldn't make out any speech. Try again, a bit closer to the microphone.",
            "unclear_words": [],
        }

    matcher = difflib.SequenceMatcher(None, target_words, said_words)
    score = round(matcher.ratio() * 100)
    matched = {i for b in matcher.get_matching_blocks() for i in range(b.a, b.a + b.size)}
    unclear = list(dict.fromkeys(w for i, w in enumerate(target_words) if i not in matched))

    if score >= 90:
        feedback = "Excellent! That was very close to the target line."
    elif score >= 70:
        feedback = "Good effort - most words were clear, a few need more practice."
    elif score >= 40:
        feedback = "Some words came through, but several were unclear. Try speaking a bit slower."
    else:
        feedback = "Hard to match to the target line. Try again, speaking clearly at a natural pace."
    return {"score": score, "transcript": transcript, "feedback": feedback, "unclear_words": unclear}
