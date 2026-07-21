"""Схемы и модели SQLAlchemy для базы данных."""

from sqlalchemy import Column, Integer, String, Float, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class StreamModel(Base):
    """Модель SQLAlchemy для водородных потоков.

    Описывает структуру таблицы `streams`, где хранятся как источники (Source),
    так и стоки (Sink) для одного или нескольких датасетов.

    Attributes:
        id (int): Первичный ключ.
        dataset_id (int): Идентификатор датасета для фильтрации (по умолчанию 1).
        name (str): Название потока.
        type (str): Тип потока ('Source' или 'Sink').
        flow_rate (float): Расход водорода (Нм3/ч).
        purity (float): Уровень чистоты водорода (%).
        allowed_connections (list): Список ID допустимых подключений.
    """

    __tablename__ = "streams"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, default=1, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(10), nullable=False)  # 'Source' or 'Sink'
    flow_rate = Column(Float, nullable=False)
    purity = Column(Float, nullable=False)
    allowed_connections = Column(JSON, default=list)
