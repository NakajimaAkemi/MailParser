import logging
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from llm_client import LLMClient
from structured_output import ParsedEmailList, EmailRequest

# ------------------------
# Logging Configuration
# ------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("email-parser-api")

# ------------------------
# FastAPI App
# ------------------------

app = FastAPI(title="Email Parser API")

llm: Optional[LLMClient] = None

@app.on_event("startup")
async def startup_event():
    global llm
    logger.info("Starting Email Parser API...")

    try:
        # Initialize LLMClient with proper paths
        oci_config_path = Path("app/config/config")
        app_config_path = Path("app/config.yaml")
        
        llm = LLMClient(OciPath=oci_config_path, configPath=app_config_path)
        logger.info("LLMClient initialized successfully")
    except Exception as e:
        logger.exception("LLM initialization failed – service in maintenance mode")
        llm = None


# ------------------------
# Middleware (optional but very useful)
# ------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code} for {request.url.path}")
    return response


# ------------------------
# Routes
# ------------------------

@app.get("/")
async def root():
    return {"message": "Email Parser API is running", "docs": "/docs"}


@app.get("/health")
async def health_check():
    if llm is None:
        raise HTTPException(status_code=503, detail="Service unavailable - LLM not initialized")
    return {"status": "healthy"}


@app.post("/parse-email", response_model=ParsedEmailList)
async def parse_email(request: EmailRequest):
    logger.info("Received /parse-email request")

    if not request.email_body.strip():
        logger.warning("Empty email_body received")
        raise HTTPException(status_code=400, detail="email_body cannot be empty")

    if llm is None:
        logger.error("LLM unavailable – under maintenance")
        raise HTTPException(status_code=503, detail="Service under maintenance")

    try:
        logger.info("Calling LLMClient.complete()")
        response = llm.complete(request)

        if response is None:
            logger.error("LLM returned None – treating as maintenance")
            raise HTTPException(status_code=500, detail="Service under maintenance")

        logger.info("Email parsed successfully")
        return response

    except HTTPException:
        # Re-raise FastAPI exceptions as-is
        raise

    except Exception as e:
        # Log full stack trace
        logger.exception("Unexpected error while parsing email")
        raise HTTPException(status_code=500, detail="Internal server error")


