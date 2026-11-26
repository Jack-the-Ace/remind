from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import accounts, plans_api
from .sources import availability


@asynccontextmanager
async def lifespan(app):
    accounts.init_db()
    plans_api.init_plans()
    yield


app = FastAPI(title="PnJ Seoul Planner", version="1.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.include_router(accounts.router)
app.include_router(plans_api.router)


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    fields = [".".join(str(part) for part in issue["loc"][1:]) for issue in exc.errors()]
    return JSONResponse({"detail": "INVALID_FIELDS", "fields": fields}, status_code=422)


@app.get("/api/health")
def health():
    return {"service": "pnj-planner", "status": "ok", "providers": availability()}


dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
