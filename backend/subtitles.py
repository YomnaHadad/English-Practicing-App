"""OpenSubtitles.com client (official REST API only) + chapter grouping."""
import os
import re

import requests
import srt

from .errors import ExternalServiceError

API_BASE = "https://api.opensubtitles.com/api/v1"


def _headers() -> dict:
    key = os.environ.get("OPENSUBTITLES_API_KEY")
    if not key:
        raise ExternalServiceError("OpenSubtitles is not configured on the server.")
    return {"Api-Key": key, "User-Agent": "MovieShadowingApp v1.0", "Content-Type": "application/json"}


def search_movies(query: str) -> list[dict]:
    """English subtitle matches: [{title, year, release_name, file_id}]."""
    try:
        resp = requests.get(
            f"{API_BASE}/subtitles",
            params={"query": query, "languages": "en", "type": "movie"},
            headers=_headers(),
            timeout=15,
        )
    except requests.RequestException as e:
        raise ExternalServiceError(f"Could not reach OpenSubtitles: {e}") from e
    if resp.status_code == 401:
        raise ExternalServiceError("Invalid OpenSubtitles API key.")
    if resp.status_code != 200:
        raise ExternalServiceError(f"Subtitle search failed ({resp.status_code}).")

    results = []
    for item in resp.json().get("data", []):
        attrs = item.get("attributes", {})
        files = attrs.get("files", [])
        if not files:
            continue
        feature = attrs.get("feature_details") or {}
        results.append(
            {
                "title": feature.get("title") or attrs.get("release") or query,
                "year": feature.get("year", "?"),
                "release_name": attrs.get("release", ""),
                "file_id": files[0]["file_id"],
            }
        )
    return results


def download_subtitle(file_id: int) -> list[dict]:
    """Download one subtitle file and parse it into [{start, end, text}] (seconds)."""
    try:
        resp = requests.post(f"{API_BASE}/download", json={"file_id": file_id}, headers=_headers(), timeout=15)
        if resp.status_code != 200:
            raise ExternalServiceError(f"Subtitle download request failed ({resp.status_code}).")
        payload = resp.json()
        link = payload.get("link")
        if not link:
            raise ExternalServiceError(f"OpenSubtitles: {payload.get('message', 'no download link returned')}")
        file_resp = requests.get(link, timeout=15)
    except requests.RequestException as e:
        raise ExternalServiceError(f"Could not reach OpenSubtitles: {e}") from e
    if file_resp.status_code != 200:
        raise ExternalServiceError("Failed to fetch the subtitle file.")
    file_resp.encoding = file_resp.encoding or "utf-8"
    return parse_srt(file_resp.text)


def parse_srt(content: str) -> list[dict]:
    lines = []
    for sub in srt.parse(content):
        text = re.sub(r"<[^>]+>", "", " ".join(sub.content.split())).strip()  # drop <i>, <b> ...
        if text:
            lines.append({"start": sub.start.total_seconds(), "end": sub.end.total_seconds(), "text": text})
    return lines


def group_into_chapters(lines: list[dict], min_gap_seconds: int = 30) -> list[dict]:
    """Start a new chapter wherever the dialogue pauses for at least `min_gap_seconds`."""
    chapters: list[list[dict]] = []
    for line in lines:
        if chapters and line["start"] - chapters[-1][-1]["end"] < min_gap_seconds:
            chapters[-1].append(line)
        else:
            chapters.append([line])
    return [
        {"title": f"Chapter {i + 1}", "start": c[0]["start"], "end": c[-1]["end"], "lines": c}
        for i, c in enumerate(chapters)
    ]
