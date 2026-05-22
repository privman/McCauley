from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth as auth_api
from app.api import provider as provider_api
from app.api import recipient as recipient_api
from app.skills import load_skills

app = FastAPI(title="McCauley v0.1")


@app.on_event("startup")
async def _load_skills() -> None:
    load_skills()


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
