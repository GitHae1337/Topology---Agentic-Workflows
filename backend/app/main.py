from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from .api import workflows, execute, logs

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global session folder path (set on startup)
SESSION_LOG_PATH: str = ""

# Create FastAPI app
app = FastAPI(
    title="MAS Framework API",
    description="Multi-Agent System Framework - Backend API",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(execute.router, prefix="/api/execute", tags=["execute"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])


@app.get("/")
async def root():
    return {"message": "MAS Framework API", "version": "0.1.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.on_event("startup")
async def startup_event():
    global SESSION_LOG_PATH
    logger.info("MAS Framework API starting up...")

    # Create Log folder and session subfolder
    log_base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "Log")
    session_name = datetime.now().strftime("%Y-%m-%d-%H-%M")
    SESSION_LOG_PATH = os.path.join(log_base_path, session_name)

    logger.info(f"Creating session log folder: {SESSION_LOG_PATH}")
    os.makedirs(SESSION_LOG_PATH, exist_ok=True)  # Use existing folder if it exists
    logger.info(f"Session log folder created: {SESSION_LOG_PATH}")

    # Initialize database
    from .api.workflows import init_db
    await init_db()
    logger.info("Database initialized")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("MAS Framework API shutting down...")
