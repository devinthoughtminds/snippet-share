from fastapi import FastAPI

# Docs live under /api so the nginx gateway routes them to the backend.
app = FastAPI(title="snippet-share", docs_url="/api/docs", openapi_url="/api/openapi.json")
