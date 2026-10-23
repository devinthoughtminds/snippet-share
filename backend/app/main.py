from fastapi import FastAPI

from app.core.config import settings
from app.routes.paste import router as paste_router

# Docs live under /api so the nginx gateway routes them to the backend.
app = FastAPI(title=settings.APP_NAME, docs_url="/api/docs", openapi_url="/api/openapi.json")

app.include_router(paste_router)
