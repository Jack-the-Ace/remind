"""Loopback-only origin for the temporary team demo. Run in its own process."""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

SHARE = Path(__file__).resolve().parents[2] / ".runtime" / "share"
SITE = SHARE / "site"
os.environ["PNJ_SHARE_DEMO"] = "1"
os.environ["PNJ_DB"] = str(SHARE / "demo.sqlite3")
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.pop("OPENAI_API_KEY", None)

from .accounts import router as accounts
from .travel import router as travel

app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1"])
app.include_router(accounts)
app.include_router(travel)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse({"detail": "INVALID_INPUT"}, status_code=422)


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "shared-demo", "llmConfigured": False,
            "instance": os.environ["PNJ_SHARE_INSTANCE"]}


@app.post("/api/recommendations")
def legacy_ai():
    raise HTTPException(403, "DEMO_ONLY")


@app.get("/")
def index():
    return FileResponse(SITE / "index.html", headers={"Cache-Control": "no-store"})


app.mount("/assets", StaticFiles(directory=SITE / "assets"), name="assets")
app.mount("/images", StaticFiles(directory=SITE / "images"), name="images")
