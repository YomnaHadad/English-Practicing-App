"""Text-to-speech with edge-tts (free Microsoft neural voices, no API key)."""
import edge_tts

from .errors import ExternalServiceError

VOICES = {"us": "en-US-AriaNeural", "gb": "en-GB-SoniaNeural"}


async def synthesize(text: str, accent: str = "us") -> bytes:
    audio = bytearray()
    try:
        async for chunk in edge_tts.Communicate(text, VOICES.get(accent, VOICES["us"])).stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
    except Exception as e:
        raise ExternalServiceError(f"Text-to-speech failed: {e}") from e
    if not audio:
        raise ExternalServiceError("Text-to-speech returned no audio.")
    return bytes(audio)
