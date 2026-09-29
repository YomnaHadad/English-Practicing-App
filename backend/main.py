"""Movie Shadowing: one FastAPI app that serves the JSON API (/api) and the web UI (static/)."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import Base, engine
from .errors import ExternalServiceError
from .routes import assessments, auth, movies, progress, tutor, vocab
from .security import DEFAULT_SECRET, SECRET_KEY

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("ENVIRONMENT") == "production" and SECRET_KEY == DEFAULT_SECRET:
        raise RuntimeError("Set SECRET_KEY before running in production.")
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Movie Shadowing", lifespan=lifespan)


@app.exception_handler(ExternalServiceError)
async def external_service_error(request: Request, exc: ExternalServiceError):
    return JSONResponse({"detail": str(exc)}, status_code=502)


@app.get("/health")
def health():
    return {"status": "ok"}


for module in (auth, assessments, vocab, movies, tutor, progress):
    app.include_router(module.router, prefix="/api")

# Must come last: it catches every path the API did not match.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
