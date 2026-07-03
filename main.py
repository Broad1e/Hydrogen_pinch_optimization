from enum import Enum
from fastapi import FastAPI
from pydantic import BaseModel, Field, PositiveInt, field_validator

#Типы данных (контракт)
class StreamType(str, Enum): #тип (источник или потребитель), строка с ограниченными вариантами
    SOURCE = "Source"
    SINK = "Sink"

class GraphPoint(BaseModel): #построение исходного графика (ОХ - расход, ОУ - чистота/концентрация)
    x: float = Field(..., description="Расход (Flow)")
    y: float = Field(..., description="Чистота водорода (Purity)")

class StreamData(BaseModel): #
    id: PositiveInt = Field(..., description="Идентификатор потока")
    name: str = Field(..., description="Название потока")
    type: StreamType = Field(..., description="Тип потока: Source или Sink")
    flow_rate: float = Field(..., gt=0, description="Расход водорода")
    purity: float = Field(..., ge=0, le=100, description="Чистота водорода в %")
    allowed_connections: list[PositiveInt] = Field(default=[], description="ID разрешенных стоков")
    
#Можно добавить field_validator, чтобы получать ошибку в случае одинаковых id
class StreamCollection(BaseModel):
    streams: list[StreamData] = Field(..., description="Список всех потоков")
    @field_validator('streams')
    @classmethod
    def check_unique_ids(cls, list_of_streams):
        all_ids = [stream.id for stream in list_of_streams]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("Ошибка. В данных есть потоки с одинаковыми ID")
        return list_of_streams

#Ответ для начальной страницы
class BaselineResponse(BaseModel):
    status: str = Field(default="success")
    current_fresh_h2: float = Field(..., description="Текущее потребление свежего водорода")
    target_fresh_h2: float | None = Field(default=None, description="Оптимизированное потребление (Стало) — пока пустое")
    saved_h2: float | None = Field(default=None, description="Сэкономленный объем — пока пустой") #пустые поля для отрисковки
    initial_curve: list[GraphPoint] = Field(..., description="Точки для исходной кривой")
    @field_validator('initial_curve')
    @classmethod
    def sort_curve(cls, curve):
        # Автоматически сортируем список точек по оси Y (чистота) от большего к меньшему
        return sorted(curve, key=lambda point: point.y, reverse=True)

class TopologyLink(BaseModel):
    source_name: str
    sink_name: str
    flow_amount: float = Field(..., description="Объем переданного водорода")#

#Ответ после оптимизации
class OptimizeResponse(BaseModel):
    status: str = Field(..., description="optimized или impossible")
    is_optimized: bool = Field(..., description="True, если экономия составила больше статистической погрешности") #замена цвета на булеву переменную
    message: str = Field(..., description="Текстовое сообщение")
    target_fresh_h2: float = Field(..., description="Новое потребление свежего водорода")
    saved_h2: float = Field(..., description="Сэкономленный объем")
    pinch_point_purity: float = Field(..., description="Чистота в Пинч-точке")
    current_fresh_h2: float = Field(..., description="Текущее потребление свежего водорода") #добавлено для таблицы
    initial_curve: list[GraphPoint] = Field(..., description="Исходная кривая") #передача обоих графиков, независимость от .csv
    optimized_curve: list[GraphPoint] = Field(..., description="Новая кривая")
    new_topology: list[TopologyLink] = Field(..., description="План переключений")
    @field_validator('initial_curve', 'optimized_curve')
    @classmethod
    def sort_curves(cls, curve):
        return sorted(curve, key=lambda point: point.y, reverse=True)


#Маршруты
app = FastAPI(title="Оптимизация методом водородного пинча")

@app.get("/")
def read_root():
    return {"message": "Сервис успешно запущен"}

@app.get("/api/v1/pinch/baseline", response_model=BaselineResponse)
def get_baseline_data():
    #вписать чтение csv и построение исходного графика
    pass

@app.get("/api/v1/pinch/optimize", response_model=OptimizeResponse)
def run_optimization():
    #вписать алгоритм оптимизациии
    pass