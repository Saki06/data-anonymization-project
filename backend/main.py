"""
FastAPI Backend for Anonymization System
Main entry point that integrates all components
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sys
import os
from pathlib import Path

# Load .env file from project root if present
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import components
from components.anonymization.routes import router as anonymization_router, set_sessions as set_anon_sessions, set_components as set_anon_components
from components.quasi_selection.routes import router as quasi_selection_router, set_sessions as set_quasi_sessions
from components.expert_system.routes import router as expert_system_router, set_knowledge_base
from components.synthetic_data.routes import router as synthetic_data_router, set_sessions as set_synth_sessions
from components.reidentification.routes import router as reidentification_router, set_sessions as set_reid_sessions
from components.upload.routes import router as upload_router, set_sessions as set_upload_sessions
from components.ai_agent.risk_analyzer import RiskAnalyzer
from components.expert_system.knowledge_base import AnonymizationKnowledgeBase
from components.optimization.nsga2 import NSGA2Optimizer

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared state on startup."""
    set_anon_sessions(sessions)
    set_quasi_sessions(sessions)
    set_synth_sessions(sessions)
    set_reid_sessions(sessions)
    set_upload_sessions(sessions)

    set_anon_components({
        'risk_analyzer': risk_analyzer,
        'knowledge_base': knowledge_base,
        'nsga2_optimizer': nsga2_optimizer
    })
    set_knowledge_base(knowledge_base)
    yield


app = FastAPI(title="Anonymization Automation System", version="1.0.0", lifespan=lifespan)

# CORS middleware - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Add CORS headers to all responses
@app.middleware("http")
async def add_cors_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# Global storage for sessions
sessions = {}

# Initialize components
risk_analyzer = RiskAnalyzer()
knowledge_base = AnonymizationKnowledgeBase()
nsga2_optimizer = NSGA2Optimizer(population_size=15, n_generations=8)


@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    """Handle CORS preflight requests"""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Anonymization Automation System API", "version": "1.0.0"}


# Include routers from components
app.include_router(upload_router)
app.include_router(quasi_selection_router)
app.include_router(anonymization_router)
app.include_router(expert_system_router)
app.include_router(synthetic_data_router)
app.include_router(reidentification_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

