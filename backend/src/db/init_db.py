"""Script to initialize the database with schema and default data."""

from loguru import logger
from sqlalchemy.orm import Session
from src.db.session import engine, SessionLocal
from src.db.models import Base, StreamModel

# Dataset 1: Original from init.sql
DATASET_1_STREAMS = [
    {"dataset_id": 1, "name": "Гидрокрекинг (ВГО)", "type": "Sink", "flow_rate": 380.0, "purity": 97.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "Гидрокрекинг (гудрон)", "type": "Sink", "flow_rate": 280.0, "purity": 96.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "ГО дизельного топлива", "type": "Sink", "flow_rate": 240.0, "purity": 93.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "ГО керосина (авиатопливо)", "type": "Sink", "flow_rate": 160.0, "purity": 92.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "ГО нафты (риформат)", "type": "Sink", "flow_rate": 180.0, "purity": 85.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "Гидродепарафинизация", "type": "Sink", "flow_rate": 140.0, "purity": 82.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "Изомеризация С5/С6", "type": "Sink", "flow_rate": 110.0, "purity": 80.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "ГО вакуумного газойля", "type": "Sink", "flow_rate": 100.0, "purity": 75.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "ГО мазута (HDS)", "type": "Sink", "flow_rate": 200.0, "purity": 65.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "Подпитка ЦВС-компрессора", "type": "Sink", "flow_rate": 170.0, "purity": 55.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "Аминовая очистка газов", "type": "Sink", "flow_rate": 150.0, "purity": 50.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "Гидрообессеривание СУГ", "type": "Sink", "flow_rate": 90.0, "purity": 45.0, "allowed_connections": []},
    {"dataset_id": 1, "name": "Регенерация катализатора", "type": "Sink", "flow_rate": 80.0, "purity": 40.0, "allowed_connections": []},
    
    {"dataset_id": 1, "name": "Рецикловый газ ГК (ВГО)", "type": "Source", "flow_rate": 160.0, "purity": 97.5, "allowed_connections": [1]},
    {"dataset_id": 1, "name": "Рецикловый газ ГК (гудрон)", "type": "Source", "flow_rate": 120.0, "purity": 96.5, "allowed_connections": [2]},
    {"dataset_id": 1, "name": "Рецикловый газ ГО ДТ", "type": "Source", "flow_rate": 140.0, "purity": 93.5, "allowed_connections": [3]},
    {"dataset_id": 1, "name": "Рецикловый газ ГО керосина", "type": "Source", "flow_rate": 80.0, "purity": 92.5, "allowed_connections": [4]},
    {"dataset_id": 1, "name": "Сепаратор ВСГ (депараф.)", "type": "Source", "flow_rate": 70.0, "purity": 79.0, "allowed_connections": [7]},
    {"dataset_id": 1, "name": "Продувочный газ (НД)", "type": "Source", "flow_rate": 180.0, "purity": 56.0, "allowed_connections": [10]},
    {"dataset_id": 1, "name": "Сбросной газ НТС", "type": "Source", "flow_rate": 130.0, "purity": 42.0, "allowed_connections": [12, 13]},
    {"dataset_id": 1, "name": "Мембранный блок", "type": "Source", "flow_rate": 170.0, "purity": 94.0, "allowed_connections": [3, 4]},
    {"dataset_id": 1, "name": "Сепаратор ВСГ (ГК)", "type": "Source", "flow_rate": 150.0, "purity": 85.0, "allowed_connections": [5, 6]},
    {"dataset_id": 1, "name": "Сепаратор ВСГ (ГО ДТ)", "type": "Source", "flow_rate": 110.0, "purity": 76.0, "allowed_connections": [8, 9]},
    {"dataset_id": 1, "name": "Коксовый газ (УЗК)", "type": "Source", "flow_rate": 200.0, "purity": 56.0, "allowed_connections": [10, 11]},
    {"dataset_id": 1, "name": "PSA-установка", "type": "Source", "flow_rate": 130.0, "purity": 99.5, "allowed_connections": [1, 2, 3]},
    {"dataset_id": 1, "name": "Отходящий газ FCC", "type": "Source", "flow_rate": 260.0, "purity": 66.0, "allowed_connections": [9, 10, 11]},
    {"dataset_id": 1, "name": "Кат. риформинг CCR", "type": "Source", "flow_rate": 300.0, "purity": 88.0, "allowed_connections": [5, 6, 8, 9]},
]

# Dataset 2: Variation for testing
DATASET_2_STREAMS = [
    {"dataset_id": 2, "name": "Гидрокрекинг (ВГО) V2", "type": "Sink", "flow_rate": 400.0, "purity": 98.0, "allowed_connections": []},
    {"dataset_id": 2, "name": "ГО дизельного топлива V2", "type": "Sink", "flow_rate": 200.0, "purity": 90.0, "allowed_connections": []},
    {"dataset_id": 2, "name": "Гидродепарафинизация V2", "type": "Sink", "flow_rate": 150.0, "purity": 85.0, "allowed_connections": []},
    
    {"dataset_id": 2, "name": "Рецикловый газ ГК V2", "type": "Source", "flow_rate": 200.0, "purity": 98.5, "allowed_connections": []}, # no limits
    {"dataset_id": 2, "name": "Мембранный блок V2", "type": "Source", "flow_rate": 100.0, "purity": 95.0, "allowed_connections": []},
    {"dataset_id": 2, "name": "PSA-установка V2", "type": "Source", "flow_rate": 250.0, "purity": 99.9, "allowed_connections": []},
]

INITIAL_STREAMS = DATASET_1_STREAMS + DATASET_2_STREAMS


def init_db(db: Session) -> None:
    """Инициализация базы данных и загрузка начальных данных.

    Удаляет старые таблицы (если они были), создаёт новую схему и 
    заполняет её двумя датасетами для тестирования алгоритмов пинч-анализа.

    Args:
        db (Session): Открытая сессия для выполнения транзакций.
    """
    logger.info("Dropping and recreating database tables to apply schema changes...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    logger.info("Seeding initial streams data (Datasets 1 and 2)...")
    for stream_data in INITIAL_STREAMS:
        stream = StreamModel(**stream_data)
        db.add(stream)
    
    db.commit()
    logger.info("Database seeded successfully.")


if __name__ == "__main__":
    db_session = SessionLocal()
    init_db(db_session)
    db_session.close()
