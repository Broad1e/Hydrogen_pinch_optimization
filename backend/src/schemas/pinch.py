"""Схемы Pydantic для валидации данных API.

Определяет форматы входящих запросов, исходящих ответов, а также типы
водородных потоков и доступные методы математической оптимизации.
"""

from enum import Enum

from pydantic import BaseModel, Field, PositiveInt, field_validator


# Типы данных
class StreamType(str, Enum):
    """Тип водородного потока."""
    SOURCE = "Source"
    SINK = "Sink"

# Методы оптимизации
class OptMethod(str, Enum):
    """Методы математической оптимизации."""
    LP = "lp"
    CASCADE = "cascade"
    MCMF = "mcmf"
    NLP = "nlp"


class GraphPoint(BaseModel):
    """Точка графика для каскадной кривой."""
    x: float = Field(..., description="Кумулятивный расход (Flow)")
    y: float = Field(..., description="Чистота водорода (Purity), %")


class StreamData(BaseModel):
    """Модель данных водородного потока."""
    id: PositiveInt = Field(..., description="Идентификатор потока")
    name: str = Field(..., description="Название потока")
    type: StreamType = Field(..., description="Тип потока: Source или Sink")
    flow_rate: float = Field(..., gt=0, description="Расход водорода, Нм3/ч")
    purity: float = Field(..., ge=0, le=100, description="Чистота водорода, %")
    allowed_connections: list[PositiveInt] = Field(
        default=[],
        description="ID стоков, в которые разрешена подача (пусто = без ограничений)",
    )


class StreamCollection(BaseModel):
    """Коллекция водородных потоков."""
    streams: list[StreamData] = Field(..., description="Список всех потоков")

    # Проверка уникальности ID потоков
    @field_validator("streams")
    @classmethod
    def check_unique_ids(cls, list_of_streams: list[StreamData]) -> list[StreamData]:
        """Проверяет уникальность идентификаторов потоков.

        Args:
            list_of_streams (list[StreamData]): Список потоков для проверки.

        Returns:
            list[StreamData]: Проверенный список потоков.

        Raises:
            ValueError: Если найдены дубликаты ID потоков.
        """
        all_ids = [s.id for s in list_of_streams]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("Ошибка: в данных есть потоки с одинаковыми ID")
        return list_of_streams


class TopologyLink(BaseModel):
    """Связь между источником и стоком в топологии сети."""
    source_name: str
    sink_name: str
    flow_amount: float = Field(..., description="Объём переданного водорода, Нм3/ч")


# Форматы ответов API
class BaselineResponse(BaseModel):
    """Модель ответа для базового сценария."""
    status: str = Field(default="success")
    baseline_fresh_h2: float = Field(..., description="Расход свежего H2 при жадном назначении, Нм3/ч")
    baseline_curve: list[GraphPoint] = Field(..., description="Каскадная кривая избытка (baseline)")
    baseline_topology: list[TopologyLink] = Field(..., description="Топология при жадном назначении")


class OptimizeResponse(BaseModel):
    """Модель ответа с результатами оптимизации."""
    status: str = Field(..., description="optimized или no_improvement")
    method: str = Field(..., description="Использованный метод: lp, cascade, mcmf")
    is_optimized: bool = Field(..., description="Найдена ли экономия")
    message: str = Field(..., description="Текстовое сообщение с результатом")
    baseline_fresh_h2: float = Field(..., description="Расход свежего H2 при жадном назначении, Нм3/ч")
    optimized_fresh_h2: float = Field(..., description="Оптимальный расход свежего H2, Нм3/ч")
    saved_h2: float = Field(..., description="Абсолютная экономия, Нм3/ч")
    savings_percent: float = Field(..., description="Экономия, %")
    pinch_point: float | None = Field(default=None, description="Пинч-точка: уровень чистоты с нулевым избытком (только cascade)")
    baseline_curve: list[GraphPoint] = Field(..., description="Каскадная кривая до оптимизации")
    optimized_curve: list[GraphPoint] = Field(..., description="Каскадная кривая после оптимизации")
    baseline_topology: list[TopologyLink] = Field(..., description="Топология при жадном назначении")
    new_topology: list[TopologyLink] = Field(..., description="Оптимальный план переключений потоков")

class DatasetInfo(BaseModel):
    """Информация о датасете."""
    id: int
    name: str
    stream_count: int

class DatasetsResponse(BaseModel):
    """Модель ответа со списком датасетов."""
    datasets: list[DatasetInfo]

