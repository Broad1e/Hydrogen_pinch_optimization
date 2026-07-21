# Подключение к PostgreSQL
# Настройки из переменных окружения, функция загрузки потоков из БД

import os
import psycopg2
from dotenv import load_dotenv
from fastapi import HTTPException

from models import StreamData, StreamCollection

load_dotenv()


def get_connection():
    # Подключение к PostgreSQL по переменным окружения
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME", "hydrogen_pinch"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "1234"),
        )
    except psycopg2.OperationalError as e:
        raise HTTPException(status_code=503, detail=f"Нет подключения к БД: {e}")


def load_streams_from_db() -> list[StreamData]:
    """_summary_

    Raises:
        HTTPException: _description_
        HTTPException: _description_
        HTTPException: _description_

    Returns:
        list[StreamData]: _description_
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, type, flow_rate, purity, allowed_connections "
                "FROM streams ORDER BY id"
            )
            rows = cur.fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="Таблица streams пуста")

        raw_streams = []
        for row in rows:
            sid, name, stype, flow_rate, purity, conns = row
            # PostgreSQL возвращает integer[] как Python list или None
            allowed = conns if conns else []
            raw_streams.append({
                "id": sid,
                "name": name,
                "type": stype,
                "flow_rate": float(flow_rate),
                "purity": float(purity),
                "allowed_connections": allowed,
            })

        try:
            collection = StreamCollection(streams=raw_streams)
            return collection.streams
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения из БД: {e}")
    finally:
        conn.close()
