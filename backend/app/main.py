import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth as auth_api
from app.api import provider as provider_api
from app.api import recipient as recipient_api
from app.api import voice as voice_api
from app.skills import load_skills

# Configure app-level logging. The default is INFO so user-turn / response
# logs are visible; set LOG_LEVEL=DEBUG for chunk-level detail, or WARNING
# to quiet it down. Uvicorn's own loggers are separate (see README).
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    load_skills()
    yield


app = FastAPI(title="McCauley v0.1", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_api.router)
app.include_router(provider_api.router)
app.include_router(recipient_api.router)
app.include_router(voice_api.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
