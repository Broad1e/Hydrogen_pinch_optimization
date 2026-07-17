# Загрузка данных из PostgreSQL
# Единая точка доступа к потокам водородной сети

from models import StreamData
from database import load_streams_from_db


def load_streams() -> list[StreamData]:
    # Загрузка потоков из PostgreSQL
    return load_streams_from_db()
