from fastapi import HTTPException, UploadFile

MAX_AUDIO_BYTES = 10 * 1024 * 1024


def read_audio(upload: UploadFile) -> bytes:
    data = upload.file.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise HTTPException(400, "Empty audio upload")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio is too large (10 MB max)")
    return data
