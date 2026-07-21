"""Database connection and session management."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "hydrogen_pinch")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "1234")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Генератор для получения сессии базы данных.

    Используется как зависимость (Dependency) в FastAPI.
    Гарантирует, что после завершения обработки запроса соединение с БД 
    будет безопасно закрыто и возвращено в пул.

    Yields:
        Session: Активная сессия подключения к базе данных.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
