from enum import Enum
from fastapi import FastAPI
from pydantic import BaseModel, Field

#Типы данных (контракт)
class StreamType(str, Enum): #тип (источник или потребитель), строка с ограниченными вариантами
    SOURCE = "Source"
    SINK = "Sink"

class GraphPoint(BaseModel): #построение исходного графика (ОХ - расход, ОУ - чистота/концентрация)
    x: float = Field(..., description="Расход (Flow)")
    y: float = Field(..., description="Чистота водорода (Purity)")

class StreamData(BaseModel): #
    id: int = Field(..., description="Идентификатор потока")
    name: str = Field(..., description="Название потока")
    type: StreamType = Field(..., description="Тип потока: Source или Sink")
    flow_rate: float = Field(..., gt=0, description="Расход водорода")
    purity: float = Field(..., ge=0, le=100, description="Чистота водорода в %")
    allowed_connections: list[int] = Field(default=[], description="ID разрешенных стоков")
    
#Можно добавить field_validator, чтобы получать ошибку в случае одинаковых id

#Ответ для начальной страницы
class BaselineResponse(BaseModel):
    status: str = Field(default="success")
    current_fresh_h2: float = Field(..., description="Текущее потребление свежего водорода")
    sources_curve: list[GraphPoint] = Field(..., description="Точки для кривой источников")
    sinks_curve: list[GraphPoint] = Field(..., description="Точки для кривой стоков")

class TopologyLink(BaseModel):
    source_id: int
    sink_id: int
    source_name: str
    sink_name: str
    flow_amount: float = Field(..., description="Объем переданного водорода")

#Ответ после оптимизации
class OptimizeResponse(BaseModel):
    status: str = Field(..., description="optimized или impossible")
    color_code: str = Field(..., description="green или red")
    message: str = Field(..., description="Текстовое сообщение")
    target_fresh_h2: float = Field(..., description="Новое потребление свежего водорода")
    saved_h2: float = Field(..., description="Сэкономленный объем")
    pinch_point_purity: float = Field(..., description="Чистота в Пинч-точке")
    optimized_sources_curve: list[GraphPoint] = Field(..., description="Новая кривая")
    new_topology: list[TopologyLink] = Field(..., description="План переключений")


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