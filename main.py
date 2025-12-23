import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os   

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.core.config import settings
from typing import AsyncGenerator
from app.db.session import sessionmanager
from contextlib import asynccontextmanager
import bcrypt
from app.api.reports import router as reports_router

if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type("about", (object,), {"__version__": bcrypt.__version__})

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    if sessionmanager._engine is not None:
        await sessionmanager.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
)

DATA_ROOT = os.getenv("DATA_ROOT", "/data/reports")
os.makedirs(DATA_ROOT, exist_ok=True)   

app.mount(
    "/reports/files",
    StaticFiles(directory=DATA_ROOT),
    name="reports_files",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, tags=["system"])
app.include_router(auth_router, prefix="/auth", tags=["authentication"])
app.include_router(reports_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
