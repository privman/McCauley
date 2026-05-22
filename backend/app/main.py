from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth as auth_api
from app.api import provider as provider_api
from app.api import recipient as recipient_api
from app.api import voice as voice_api
from app.skills import load_skills


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
