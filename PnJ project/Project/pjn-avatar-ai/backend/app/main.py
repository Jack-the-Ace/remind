import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .accounts import router as accounts
from .travel import router as travel

from .llm import LLM_ERRORS, generate_recommendation
from .models import RecommendationRequest, RecommendationResponse
from .seed_data import SEED_USERS

app = FastAPI(title="PnJ Avatar AI Validation API", version="0.1.0")
app.include_router(accounts)
app.include_router(travel)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    return JSONResponse(status_code=422, content={"detail": "INVALID_INPUT"})
app.add_middleware(CORSMiddleware, allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")], allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "llmConfigured": bool(os.getenv("OPENAI_API_KEY")), "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini")}


@app.get("/api/seed-users")
async def seed_users():
    return SEED_USERS


@app.post("/api/recommendations", response_model=RecommendationResponse)
async def recommendations(request: RecommendationRequest):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail={"code": "LLM_NOT_CONFIGURED", "message": "Server API key is not configured. Add OPENAI_API_KEY to backend/.env and restart the API."})
    try:
        recommendation, model = await generate_recommendation(request)
        return RecommendationResponse(recommendation=recommendation, model=model)
    except LLM_ERRORS as error:
        raise HTTPException(status_code=502, detail={"code": "LLM_API_ERROR", "message": "Check server key, model access, network, and usage limits."}) from None
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=502, detail={"code": "LLM_RESPONSE_ERROR", "message": "Invalid response from the model."}) from None
