import csv
import os
from enum import Enum
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, PositiveInt, field_validator

#Типы данных (контракт)
class StreamType(str, Enum): #тип (источник или потребитель), строка с ограниченными вариантами
    SOURCE = "Source"
    SINK = "Sink"

class GraphPoint(BaseModel): #построение исходного графика (ОХ - расход, ОУ - чистота/концентрация)
    x: float = Field(..., description="Расход (Flow)")
    y: float = Field(..., description="Чистота водорода (Purity)")

class StreamData(BaseModel): #переменные 
    id: PositiveInt = Field(..., description="Идентификатор потока")
    name: str = Field(..., description="Название потока")
    type: StreamType = Field(..., description="Тип потока: Source или Sink")
    flow_rate: float = Field(..., gt=0, description="Расход водорода")
    purity: float = Field(..., ge=0, le=100, description="Чистота водорода в %")
    allowed_connections: list[PositiveInt] = Field(default=[], description="ID разрешенных стоков")
    
#field_validator, чтобы получать ошибку в случае одинаковых id
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
    target_fresh_h2: float | None = Field(default=None, description="Оптимизированное потребление — пока пустое")
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
    current_fresh_h2: float = Field(..., description="Текущее потребление свежего водорода") #добавлено для таблицы
    initial_curve: list[GraphPoint] = Field(..., description="Исходная кривая") #передача обоих графиков, независимость от .csv
    optimized_curve: list[GraphPoint] = Field(..., description="Новая кривая")
    new_topology: list[TopologyLink] = Field(..., description="План переключений")
    @field_validator('initial_curve', 'optimized_curve')
    @classmethod
    def sort_curves(cls, curve):
        return sorted(curve, key=lambda point: point.y, reverse=True)

#функция чтения CSV-файла
def load_streams_from_csv(file_path: str = "data.csv") -> list[StreamData]:
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Файл {file_path} не найден на сервере")

    raw_streams = []
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Превращаем строку в список 
            conns_str = row.get("allowed_connections", "").strip()
            if conns_str:
                conns = [int(c.strip()) for c in conns_str.split(",")]
            else:
                conns = []

            raw_streams.append({
                "id": int(row["id"]),
                "name": row["name"],
                "type": row["type"],
                "flow_rate": float(row["flow_rate"]),
                "purity": float(row["purity"]),
                "allowed_connections": conns
            })
    
    #проверка уникальности  id
    try:
        collection = StreamCollection(streams=raw_streams)
        return collection.streams
    except ValueError as e:
        #если валидатор нашел ошибку - 422 ошибка
        raise HTTPException(status_code=422, detail=str(e))

#Маршруты
app = FastAPI(title="Оптимизация методом водородного пинча")

@app.get("/")
def read_root():
    return {"message": "Сервис успешно запущен"}

@app.get("/api/v1/pinch/baseline", response_model=BaselineResponse)
def get_baseline_data():
#считать данные из .csv файла
    streams = load_streams_from_csv("data.csv")
    
    #расчет текущего потребления (сумма расходов всех потоков типа Source)
    current_fresh = sum(s.flow_rate for s in streams if s.type == StreamType.SOURCE)
    
    #построение графика
    #отбор источников и сортировка по чистоте (от высшей к низшей)
    sources = [s for s in streams if s.type == StreamType.SOURCE]
    sources_sorted = sorted(sources, key=lambda s: s.purity, reverse=True)
    
    actual_curve = []
    current_x = 0.0
    
    for stream in sources_sorted:
        #точка начала ступеньки (текущий накопленный расход, чистота этой трубы)
        actual_curve.append(GraphPoint(x=current_x, y=stream.purity))
        
        #суммирование расхода этой трубы к общему (вправо по оси X)
        current_x += stream.flow_rate
        
        #точка конца горизонтальной ступеньки
        actual_curve.append(GraphPoint(x=current_x, y=stream.purity))
    
    #формирование ответа
    return BaselineResponse(
        status="success",
        current_fresh_h2=current_fresh,
        initial_curve=actual_curve
    )

@app.get("/api/v1/pinch/optimize", response_model=OptimizeResponse)
def run_optimization():
    #чтение данных и сортировка по убыванию чистоты
    streams = load_streams_from_csv("data.csv")
    sources = sorted([s for s in streams if s.type == StreamType.SOURCE], key=lambda s: s.purity, reverse=True)
    sinks = sorted([s for s in streams if s.type == StreamType.SINK], key=lambda s: s.purity, reverse=True)

    current_fresh_h2 = sum(s.flow_rate for s in sources)

    #каскадный алгоритм переключения
    #создание копий расходов, чтобы вычитать из них объемы в процессе распределения
    source_flows = {s.id: s.flow_rate for s in sources}
    target_fresh_h2 = 0.0
    new_topology = []

    for sink in sinks:
        demand = sink.flow_rate
        for source in sources:
            #условие 1: источник чище или равен стоку, условие 2: в трубах еще есть объем
            if source.purity >= sink.purity and source_flows[source.id] > 0 and demand > 0:
                #условие 3: физическая возможность (если список связей не пуст, проверить его)
                if source.allowed_connections and sink.id not in source.allowed_connections:
                    continue

                #передать максимально возможный объем
                transfer = min(source_flows[source.id], demand)
                source_flows[source.id] -= transfer
                demand -= transfer

                new_topology.append(TopologyLink(
                    source_name=source.name,
                    sink_name=sink.name,
                    flow_amount=transfer
                ))
        
        #если после всех внутренних переключений стоку всё еще нужен водород, этот дефицит придется брать свежим водородом
        target_fresh_h2 += demand

        #расчет экономии и порога ччувствительности
    saved_h2 = current_fresh_h2 - target_fresh_h2
    DEADBAND_PERCENT = 0.01 #порог отсечения (1% от текущего потребления)
    
    #считаем оптимизацию успешной только если экономия реальна
    is_optimized = saved_h2 > (current_fresh_h2 * DEADBAND_PERCENT)
    
    #построение графиков
    actual_curve = []
    current_x = 0.0
    for stream in sources:
        actual_curve.append(GraphPoint(x=current_x, y=stream.purity))
        current_x += stream.flow_rate
        actual_curve.append(GraphPoint(x=current_x, y=stream.purity))

    optimized_curve = []
    #если экономия не прошла порог, графики совпадут
    effective_savings = saved_h2 if is_optimized else 0.0
    
    for point in actual_curve:
        # Уменьшение координаты X на величину экономии (не уходит ниже нуля)
        optimized_curve.append(GraphPoint(x=max(0.0, point.x - effective_savings), y=point.y))

    #формирование ответа
    #определение сообщения для фронтенда в зависимости от успешности оптимизации
    if is_optimized:
        msg = f"Оптимизация успешна. Найдена новая схема переключений. Сэкономлено {round(saved_h2, 2)} ед."
    else:
        msg = "Оптимизация нецелесообразна."


    return OptimizeResponse(
        status="optimized" if is_optimized else "impossible",
        is_optimized=is_optimized,
        message=msg,
        current_fresh_h2=current_fresh_h2,
        target_fresh_h2=target_fresh_h2,
        saved_h2=saved_h2, 
        initial_curve=actual_curve,
        optimized_curve=optimized_curve,
        new_topology=new_topology
    )