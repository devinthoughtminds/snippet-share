from fastapi import FastAPI

# ... router imports ...
from app.core.config import settings
from app.routes.pastes import router as pastes_router

# ... create app ...
app = FastAPI(
    title=settings.APP_NAME,   # uses APP_NAME from env
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

app.include_router(paste)
