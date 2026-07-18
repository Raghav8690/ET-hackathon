"""
PS8 – FastAPI Application Entry Point

Starts the API server, initialises the database, and registers all routers.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db.session import init_db
from backend.routes.documents import router as documents_router


# ---------------------------------------------------------------------------
# Lifespan: run setup / teardown around the application lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup (no-op if they already exist)."""
    init_db()
    print("✅  Database tables initialised.")
    yield
    # Shutdown logic (if needed) goes here
    print("🛑  Application shutting down.")


# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PS8 AI for Industrial Knowledge Intelligence",
    description=(
        "A unified AI-powered knowledge companion that instantly answers "
        "equipment-related questions by searching across all uploaded "
        "documents simultaneously."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routers
app.include_router(documents_router)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/", tags=["Health"])
def read_root():
    return {"message": "Hello World from PS8 Backend!", "status": "ok"}


@app.get("/health", tags=["Health"])
def health_check():
    """Lightweight health probe for monitoring."""
    return {"status": "healthy"}
