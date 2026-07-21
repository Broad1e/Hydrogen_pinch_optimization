"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.core.logger import setup_logging
from src.api.router import router
from src.db.session import SessionLocal
from src.db.init_db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Событие жизненного цикла FastAPI (Lifespan).

    Выполняется при запуске и остановке приложения.
    При запуске: настраивает систему логирования (Loguru) и инициализирует 
    базу данных (создаёт таблицы и заливает начальные датасеты).
    При остановке: корректно завершает работу приложения.

    Args:
        app (FastAPI): Экземпляр приложения FastAPI.
    """
    # Setup Loguru logger
    setup_logging()
    logger.info("Starting up Hydrogen Pinch Optimizer API...")
    
    # Initialize Database on startup
    try:
        db = SessionLocal()
        init_db(db)
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    finally:
        db.close()
        
    yield
    
    logger.info("Shutting down API...")


# Initialize FastAPI
app = FastAPI(
    title="Hydrogen Pinch Optimizer",
    description=(
        "Оптимизация потребления водорода на НПЗ методом водородного пинча. "
        "Поддерживает методы: LP, Cascade, MCMF, NLP."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Router
app.include_router(router)


@app.get("/")
def read_root():
    """Root endpoint for basic verification."""
    return {
        "message": "Hydrogen Pinch Optimizer API is running",
        "version": "2.0.0",
        "docs_url": "/docs"
    }