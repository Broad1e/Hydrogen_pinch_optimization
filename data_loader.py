# Загрузка данных из CSV
# Парсинг файла data.csv с валидацией через Pydantic

import csv
import os

from fastapi import HTTPException

from models import StreamData, StreamCollection


def load_streams_from_csv(file_path: str = "data.csv") -> list[StreamData]:
    # Парсинг CSV с перехватом ошибок:
    # при отсутствии колонки или неверном значении выдается HTTP 422
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Файл {file_path} не найден на сервере")

    raw_streams: list[dict] = []
    try:
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):
                try:
                    conns_str = row.get("allowed_connections", "").strip()
                    conns = (
                        [int(c.strip()) for c in conns_str.split(",") if c.strip()]
                        if conns_str
                        else []
                    )
                    raw_streams.append(
                        {
                            "id": int(row["id"]),
                            "name": row["name"],
                            "type": row["type"],
                            "flow_rate": float(row["flow_rate"]),
                            "purity": float(row["purity"]),
                            "allowed_connections": conns,
                        }
                    )
                except (KeyError, ValueError) as e:
                    raise HTTPException(status_code=422, detail=f"Ошибка в строке {row_num} CSV: {e}. Данные: {row}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения файла: {e}")

    try:
        collection = StreamCollection(streams=raw_streams)
        return collection.streams
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
