"""Тесты для Pydantic-схем валидации."""

import pytest
from pydantic import ValidationError

from src.schemas.pinch import StreamCollection, StreamData, StreamType


def test_stream_data_valid():
    """Проверка создания валидного потока."""
    stream = StreamData(
        id=1,
        name="Test Source",
        type=StreamType.SOURCE,
        flow_rate=100.5,
        purity=95.0,
        allowed_connections=[2, 3]
    )
    assert stream.id == 1
    assert stream.type == "Source"
    assert stream.flow_rate == 100.5
    assert stream.purity == 95.0

def test_stream_data_invalid_purity():
    """Проверка валидации чистоты (должна быть от 0 до 100)."""
    with pytest.raises(ValidationError):
        StreamData(
            id=1,
            name="Test",
            type=StreamType.SINK,
            flow_rate=100.0,
            purity=105.0  # Ошибка: больше 100
        )

def test_stream_data_invalid_flow_rate():
    """Проверка валидации расхода (должен быть > 0)."""
    with pytest.raises(ValidationError):
        StreamData(
            id=1,
            name="Test",
            type=StreamType.SOURCE,
            flow_rate=-10.0,  # Ошибка: меньше 0
            purity=90.0
        )

def test_stream_collection_unique_ids():
    """Проверка уникальности ID в коллекции потоков."""
    with pytest.raises(ValueError, match="одинаковыми ID"):
        StreamCollection.model_validate({
            "streams": [
                {"id": 1, "name": "S1", "type": "Source", "flow_rate": 100, "purity": 90},
                {"id": 1, "name": "S2", "type": "Sink", "flow_rate": 50, "purity": 80},  # Дубликат ID
            ]
        })
