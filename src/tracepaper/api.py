"""FastAPI application stub. Full implementation in Phase 5."""

from fastapi import FastAPI

from tracepaper.config import get_settings
from tracepaper.logging import get_logger, setup_logging

# Setup logging
settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)

app = FastAPI(
    title="Tracepaper",
    description="Agentic SOX control testing with enforced provenance",
    version="0.0.1",
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Tracepaper API", "version": "0.0.1"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/config")
async def config():
    """Return current configuration (non-sensitive)."""
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "cache_enabled": settings.cache_enabled,
        "log_level": settings.log_level,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
