"""FastAPI application main file."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.database import init_db
from app.routers import appletv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Deep Link Apple TV API", version="1.0.0")

# CORS — для локального проекта разрешаем любые origins (в т.ч. по IP с другого устройства)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https?://.*",  # на случай если "*" не срабатывает в части окружений
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(appletv.router)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Deep Link Apple TV API", "version": "1.0.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
