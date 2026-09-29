class ExternalServiceError(Exception):
    """An outside service (OpenSubtitles, Groq, TTS) failed or is not configured.
    The API turns this into a 502 with the message as `detail`."""
