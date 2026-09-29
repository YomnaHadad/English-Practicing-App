"""All LLM / speech-to-text calls (Groq). Routes call these as `ai.<function>`
so tests can replace them with fakes.

Note: with reasoning models, hidden reasoning tokens count toward
`max_completion_tokens`, so the limits below are deliberately generous.
"""
import json
import os

from groq import Groq

from .errors import ExternalServiceError

CHAT_MODEL = os.environ.get("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")
STT_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")

LEVEL_GUIDE = {
    "A1": "Use very short, simple sentences and only basic everyday words. Speak slowly and clearly.",
    "A2": "Use short, simple sentences and common vocabulary. Avoid idioms.",
    "B1": "Use clear everyday English. You may use a few common phrasal verbs, explained by context.",
    "B2": "Use natural English with some less common vocabulary and varied sentence structure.",
    "C1": "Use fluent, natural English including idioms and nuanced vocabulary.",
    "C2": "Use sophisticated, native-like English, including idiom, irony and abstract topics.",
}


def _client() -> Groq:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise ExternalServiceError("The AI service is not configured on the server.")
    return Groq(api_key=key)


def _schema(name: str, schema: dict) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}


def _chat(messages: list[dict], max_tokens: int, temperature: float, response_format: dict | None = None) -> str:
    kwargs = {"response_format": response_format} if response_format else {}
    try:
        response = _client().chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            reasoning_format="hidden",
            **kwargs,
        )
    except ExternalServiceError:
        raise
    except Exception as e:
        raise ExternalServiceError(f"AI request failed: {e}") from e
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise ExternalServiceError("The AI returned an empty response.")
    return content


def _chat_json(messages: list[dict], max_tokens: int, name: str, schema: dict) -> dict:
    content = _chat(messages, max_tokens, 0, _schema(name, schema))
    try:
        return json.loads(content)
    except ValueError as e:
        raise ExternalServiceError("The AI returned malformed JSON.") from e


# ---------- vocabulary ----------

def explain_word(word: str, sentence: str) -> dict:
    """{'easy_word': ..., 'meaning_in_sentence': ...}"""
    prompt = f"""You are an English teacher helping a learner understand vocabulary.

Target word: {word}

Sentence:
{sentence}

Explain ONLY the meaning of the target word as it is used in this sentence.
Give:
1. easy_word: one simple synonym or short equivalent phrase.
2. meaning_in_sentence: a short, clear explanation of what the word means in this exact context.
Do not explain other meanings. Do not give examples or grammar information."""
    schema = {
        "type": "object",
        "properties": {"easy_word": {"type": "string"}, "meaning_in_sentence": {"type": "string"}},
        "required": ["easy_word", "meaning_in_sentence"],
        "additionalProperties": False,
    }
    data = _chat_json([{"role": "user", "content": prompt}], 800, "word_explanation", schema)
    if not data.get("easy_word", "").strip() or not data.get("meaning_in_sentence", "").strip():
        raise ExternalServiceError("The AI returned an incomplete explanation.")
    return {"easy_word": data["easy_word"].strip(), "meaning_in_sentence": data["meaning_in_sentence"].strip()}


# ---------- speech ----------

def transcribe(audio: bytes, filename: str = "speech.webm") -> str:
    try:
        result = _client().audio.transcriptions.create(
            file=(filename, audio), model=STT_MODEL, language="en", temperature=0
        )
    except ExternalServiceError:
        raise
    except Exception as e:
        raise ExternalServiceError(f"Speech recognition failed: {e}") from e
    return (result.text or "").strip()


# ---------- speaking tutor ----------

def tutor_reply(level: str, topic: str, history: list[dict], study_words: list[str], weak_skill: str | None) -> str:
    """Next tutor message. Empty `history` means: open the conversation."""
    system = (
        f"You are a friendly English speaking tutor talking with a learner at CEFR level {level}. "
        f"{LEVEL_GUIDE.get(level, LEVEL_GUIDE['B1'])}\n"
        f"Conversation topic: {topic or 'anything the learner enjoys (movies, daily life, hobbies)'}.\n"
        "Rules: reply in 1-3 short sentences, then ask ONE follow-up question. Always stay in English. "
        "Do not lecture. If the learner makes a clear mistake, naturally use the correct form in your reply "
        "without pointing it out. If the learner seems to struggle, simplify."
    )
    if study_words:
        system += f"\nWhen it fits naturally, use or ask about these words the learner is studying: {', '.join(study_words)}."
    if weak_skill:
        system += f"\nThe learner's weakest skill on the placement test was {weak_skill}."

    messages = [{"role": "system", "content": system}]
    messages += [{"role": m["role"], "content": m["text"]} for m in history]
    if not history:
        messages.append({"role": "user", "content": "(Start the conversation with a short greeting and a first question.)"})
    return _chat(messages, 1000, 0.7)


def tutor_feedback(level: str, topic: str, history: list[dict]) -> dict:
    """{'summary': str, 'mistakes': [{'said','correction','explanation'}]} for a finished session."""
    conversation = "\n".join(f"{'Learner' if m['role'] == 'user' else 'Tutor'}: {m['text']}" for m in history)
    prompt = f"""You are an English teacher reviewing a speaking practice session.
Learner level: CEFR {level}. Topic: {topic or 'free conversation'}.

Conversation (transcribed speech, so ignore punctuation and capitalisation):
{conversation}

Find the learner's most important language mistakes (grammar, word choice, unnatural phrasing), at most 5.
For each give: said (the learner's exact words), correction (a corrected version), explanation (one short sentence suited to the level).
If there were no real mistakes, return an empty list.
Also write a summary: 2 encouraging sentences that name one specific thing to practise next."""
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "mistakes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "said": {"type": "string"},
                        "correction": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["said", "correction", "explanation"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["summary", "mistakes"],
        "additionalProperties": False,
    }
    data = _chat_json([{"role": "user", "content": prompt}], 2000, "session_feedback", schema)
    return {"summary": str(data.get("summary", "")).strip(), "mistakes": data.get("mistakes", [])[:5]}
