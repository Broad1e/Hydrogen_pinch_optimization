"""Фикстуры Pytest для тестирования Hydrogen Pinch API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.models import Base, StreamModel
from src.db.init_db import INITIAL_STREAMS
from src.db.session import get_db
from src.main import app

# Использование базы данных SQLite в памяти для тестирования
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def db_engine():
    """Создает тестовый движок базы данных и таблицы.

    Yields:
        Engine: Экземпляр SQLAlchemy Engine для тестовой базы данных.
    """
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Предоставляет контекст транзакции для серии операций базы данных.

    Args:
        db_engine (Engine): Экземпляр SQLAlchemy Engine для тестовой базы данных.

    Yields:
        Session: Сессия базы данных SQLAlchemy для тестирования.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    # Заполнение начальными данными для тестирования
    for stream_data in INITIAL_STREAMS:
        stream = StreamModel(**stream_data)
        session.add(stream)
    session.commit()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Предоставляет тестовый клиент FastAPI со сфабрикованной сессией БД.

    Args:
        db_session (Session): Сессия базы данных SQLAlchemy для тестирования.

    Yields:
        TestClient: Клиент для тестирования API FastAPI.
    """
    def override_get_db():
        """Переопределяет генератор сессий базы данных для проведения тестов.

        Yields:
            Session: Сессия тестовой базы данных SQLAlchemy.
        """
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

